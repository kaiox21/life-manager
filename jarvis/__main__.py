"""Sobe o cérebro do Jarvis: uv run python -m jarvis

Lê o mesmo .env do núcleo (modelos, provedor, MCP_TOKEN). Variáveis próprias:
  JARVIS_CORE_URL        endereço do núcleo (padrão: Docker local; depois do VPS, o Tailscale)
  JARVIS_WHISPER_MODEL   repositório do mlx-whisper (padrão: whisper-large-v3-turbo-q4)
  JARVIS_VOICE / JARVIS_VOICE_RATE   voz e velocidade da fala (padrão: Luciana, 0.52)
  JARVIS_FILLER          "um instante, senhor" ao chamar ferramenta em modo voz (padrão: true)
  FISH_API_KEY / FISH_VOICE_ID / FISH_VOICE_SPEED   voz da Fish Audio (vazio = voz local)
  JARVIS_PASTAS          pastas onde o Jarvis abre terminais, separadas por ":" (padrão:
                         ~/Projetos pessoais:~/AmicusIA:~/Faculdade)
  JARVIS_WAKE_PALAVRAS / JARVIS_WAKE_LIMIAR / JARVIS_WAKE_PESO   variantes de "Jarvis" (vírgula),
                         limiar e peso do detector da palavra (padrão: JARVIS,JARVES,JAR VIS,JAVIS;
                         0.2; 1.5)
  JARVIS_TERMINAIS_MAX / JARVIS_TERMINAIS_MEM_MIN   Claude Code rodando nos terminais (4) e
                         memória livre mínima em % para abrir um terminal (20)
  JARVIS_SILENCIO        horário sem avisos falados (padrão: 23:00-07:00; vazio desliga)
  JARVIS_LEMBRETE_GASTOS hora da pergunta "nenhum gasto lançado hoje" (padrão: 21:30; vazio
                         desliga)
  JARVIS_FOCO_LIGAR / JARVIS_FOCO_DESLIGAR   nomes dos atalhos do app Atalhos que ligam e
                         desligam o Foco no modo estudo (padrão: "Jarvis Foco" e "Jarvis Foco Fim")
  JARVIS_PLAYLIST_ESTUDO / JARVIS_ESTUDO_MINUTOS / JARVIS_ESTUDO_PAUSA   playlist do Kaio e
                         padrões do modo estudo (estudo; 50; 10)
Valem as do ambiente e, na falta, as do .env.
"""

import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import Callable
from typing import Any

from dotenv import dotenv_values

from app.agent.llm import make_llm
from app.config import get_settings
from jarvis import events
from jarvis.agent import FILLERS, JarvisBrain, web_tools
from jarvis.audio import DEFAULT_MODEL, Transcriber, Vad
from jarvis.control import TerminalControl
from jarvis.local_tools import LocalTools, load_config
from jarvis.mcp_client import ResilientCore
from jarvis.panel_extras import PanelExtras
from jarvis.permissions import HookServer, Permissions
from jarvis.proactive import Proactive
from jarvis.server import JarvisServer
from jarvis.sessions import Folders
from jarvis.spotify import Ducker, Spotify
from jarvis.study import StudyMode
from jarvis.terminals import Terminals
from jarvis.tmux import Tmux
from jarvis.tts import make_speaker
from jarvis.wake import WORDS, SherpaSpotter, WakeService
from jarvis.wake_model import model_dir, present

log = logging.getLogger(__name__)
_DOTENV = {k: v for k, v in dotenv_values(".env").items() if v is not None}


def env(name: str, default: str = "") -> str:
    """Ambiente primeiro; depois o .env (o pydantic lê o .env, mas não o exporta)."""
    return os.environ.get(name) or _DOTENV.get(name) or default


def env_raw(name: str, default: str) -> str:
    """Como `env`, mas um valor vazio vale (vazio desliga)."""
    return os.environ.get(name, _DOTENV.get(name, default))


def _log_task_error(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and task.exception():
        log.error("tarefa em segundo plano falhou: %r", task.exception())


async def watch_terminals(
    terminals: Terminals,
    server: JarvisServer,
    control: TerminalControl,
    notify: Callable[[dict[str, Any]], None] = lambda alert: None,
) -> None:
    """Lê os eventos dos hooks do Claude Code (a cada 300 ms) e o tmux (a cada 1 s)."""
    ticks = 0
    while True:
        try:
            changed, alerts = terminals.poll()
            if ticks % 3 == 0:
                tmux_changed, tmux_alerts = await control.refresh()
                changed = changed or tmux_changed
                alerts += tmux_alerts
            ticks += 1
            if changed:
                await server.broadcast(events.terminals(terminals.snapshot()))
            for alert in alerts:
                notify(alert)  # aviso falado (jarvis/proactive.py)
                await server.broadcast(events.terminal_alert(alert))
        except Exception:  # noqa: BLE001
            log.exception("terminais: falha ao ler os eventos")
        await asyncio.sleep(0.3)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    s = get_settings()
    config = load_config()
    llm = make_llm(s)
    url = env("JARVIS_CORE_URL", "http://localhost:8000/mcp/")

    vad = None
    try:
        vad = Vad()
    except Exception:  # noqa: BLE001
        log.warning("VAD indisponível (pysilero-vad); a voz não vai cortar o silêncio")
    transcriber = Transcriber(
        env("JARVIS_WHISPER_MODEL", DEFAULT_MODEL),
        hints=lambda: list(config.get("vocabulario") or []),
    )
    warmup = asyncio.create_task(transcriber.warmup())
    warmup.add_done_callback(_log_task_error)

    terminals = Terminals()
    terminals.load()
    permissions = Permissions()
    folders = Folders.from_env(env("JARVIS_PASTAS"))
    control = TerminalControl(
        Tmux(),
        terminals,
        permissions,
        folders,
        max_claude=int(env("JARVIS_TERMINAIS_MAX", "4")),
        min_memory=int(env("JARVIS_TERMINAIS_MEM_MIN", "20")),
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    from jarvis.local_tools import run_command

    ducker = Ducker(run_command)
    spotify_id = env("SPOTIFY_CLIENT_ID")
    spotify = Spotify(spotify_id, run_command) if spotify_id else None
    if spotify is None:
        log.info("Spotify sem SPOTIFY_CLIENT_ID: só tocar/pausar/próxima/anterior")

    # o núcleo pode estar fora (Docker parado): o cérebro sobe assim mesmo e reconecta sozinho
    core = ResilientCore(url, s.mcp_token.get_secret_value())
    core_task = asyncio.create_task(core.run())
    core_task.add_done_callback(_log_task_error)
    local = LocalTools(
        config=config,
        terminals=terminals.snapshot,
        control=control,
        spotify=spotify,
        ducker=ducker,
        editor=env("JARVIS_EDITOR", "Visual Studio Code"),
    )
    brain = JarvisBrain(
        llm,
        core,
        local,
        primary=env("JARVIS_MODEL_PRIMARY", s.model_primary),
        escalation=env("JARVIS_MODEL_ESCALATION", s.model_escalation),
        transcriber=transcriber,
        vad=vad,
        filler=env("JARVIS_FILLER", "true").lower() != "false",
    )
    brain.speaker = make_speaker(
        brain.on_speech_event,
        voice=env("JARVIS_VOICE", "Luciana"),
        rate=float(env("JARVIS_VOICE_RATE", "0.52")),
        fish_key=env("FISH_API_KEY", ""),
        fish_voice=env("FISH_VOICE_ID", ""),
        fish_speed=float(env("FISH_VOICE_SPEED", "1.0")),
        fish_latency=env("FISH_LATENCY", "normal"),
        fish_quality_guard=env("FISH_QUALITY_GUARD", "true").lower() != "false",
    )
    brain.speaker.prefetch(FILLERS)
    brain.weather_place = (
        float(env("JARVIS_CLIMA_LAT", "-15.79")),
        float(env("JARVIS_CLIMA_LON", "-47.88")),
        env("JARVIS_CLIMA_NOME", "Brasília"),
    )
    brain.pending_permissions = permissions.pending_count
    # internet (busca e leitura de páginas pela Anthropic): JARVIS_INTERNET=false desliga
    if s.llm_provider == "anthropic" and env("JARVIS_INTERNET", "true").lower() != "false":
        brain.web = web_tools(env("JARVIS_CLIMA_NOME", "Brasília"))
        log.info("internet ligada: busca e leitura de páginas")
    brain.ducker = ducker
    server = JarvisServer(brain)
    brain.panel_extras = PanelExtras(run_command, folders, load_config, lambda: brain.weather_place)
    level_tasks: set[asyncio.Task[None]] = set()

    def voice_level(n: float) -> None:  # orbe pulsando com a voz, em todas as interfaces
        task = asyncio.create_task(server.broadcast_ui(events.voice_level(n)))
        level_tasks.add(task)
        task.add_done_callback(level_tasks.discard)

    brain.speaker.set_on_level(voice_level)
    server.control = control
    proactive = Proactive(
        brain,
        core,
        server.broadcast_ui,
        wake=lambda: server.wake,
        silence=env_raw("JARVIS_SILENCIO", "23:00-07:00"),
        reminder=env_raw("JARVIS_LEMBRETE_GASTOS", "21:30"),
    )
    local.notices = proactive

    def avisos_mudaram() -> None:  # o botão Silenciar mostra até quando
        task = asyncio.create_task(brain.panel("avisos", server.broadcast_ui))
        level_tasks.add(task)
        task.add_done_callback(level_tasks.discard)

    proactive.on_change = avisos_mudaram
    study = StudyMode(
        brain=brain,
        proactive=proactive,
        broadcast_ui=server.broadcast_ui,
        run=run_command,
        spotify=spotify,
        focus_on=env("JARVIS_FOCO_LIGAR", "Jarvis Foco"),
        focus_off=env("JARVIS_FOCO_DESLIGAR", "Jarvis Foco Fim"),
        playlist=env("JARVIS_PLAYLIST_ESTUDO", "estudo"),
        minutes=int(env("JARVIS_ESTUDO_MINUTOS", "50")),
        pause=int(env("JARVIS_ESTUDO_PAUSA", "10")),
    )
    local.study = study
    proactive.study = study

    async def control_broadcast(ev: events.Event) -> None:
        if ev.type == "terminal_alert" and isinstance(ev.data, dict):
            proactive.terminal(ev.data)  # pedido de permissão de um terminal compartilhado
        await server.broadcast(ev)

    control.broadcast = control_broadcast
    server.greeting = lambda: [events.terminals(terminals.snapshot())]
    if present():
        words = tuple(w.strip() for w in env("JARVIS_WAKE_PALAVRAS").split(",") if w.strip())
        threshold = float(env("JARVIS_WAKE_LIMIAR", "0.05"))
        score = float(env("JARVIS_WAKE_PESO", "3.0"))
        server.wake = WakeService(
            brain,
            lambda: SherpaSpotter(model_dir(), words or WORDS, threshold, score),
            Vad,
            server.broadcast,
            server.broadcast_ui,
        )
    else:
        log.warning("sem o modelo da palavra 'Jarvis' (python3 jarvis/wake_model.py)")
    await control.refresh()
    watcher = asyncio.create_task(watch_terminals(terminals, server, control, proactive.terminal))
    watcher.add_done_callback(_log_task_error)
    proactive_task = asyncio.create_task(proactive.run())
    proactive_task.add_done_callback(_log_task_error)
    hooks = HookServer(server.check_token, control.on_hook)
    async with (
        hooks.run() as hook_port,
        server.run(port=int(env("JARVIS_PORT", "0")), extra={"hook_port": hook_port}),
    ):
        try:
            await stop.wait()
        finally:
            log.info("parando: encerrando as abas de terminal")
            with contextlib.suppress(Exception):
                await asyncio.wait_for(control.shutdown(), 5)


if __name__ == "__main__":
    asyncio.run(main())
    # threads de fundo (transcrição, áudio) podem segurar a saída: ao parar, sai de vez, para o
    # launchd não deixar um cérebro órfão rodando ao lado do novo
    os._exit(0)
