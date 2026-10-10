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
Valem as do ambiente e, na falta, as do .env.
"""

import asyncio
import contextlib
import logging
import os
import signal

from dotenv import dotenv_values

from app.agent.llm import make_llm
from app.config import get_settings
from jarvis import events
from jarvis.agent import FILLERS, JarvisBrain
from jarvis.audio import DEFAULT_MODEL, Transcriber, Vad
from jarvis.control import TerminalControl
from jarvis.local_tools import LocalTools, load_config
from jarvis.mcp_client import CoreClient
from jarvis.permissions import HookServer, Permissions
from jarvis.server import JarvisServer
from jarvis.sessions import Folders
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


def _log_task_error(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and task.exception():
        log.error("tarefa em segundo plano falhou: %r", task.exception())


async def watch_terminals(
    terminals: Terminals, server: JarvisServer, control: TerminalControl
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
    control = TerminalControl(
        Tmux(),
        terminals,
        permissions,
        Folders.from_env(env("JARVIS_PASTAS")),
        max_claude=int(env("JARVIS_TERMINAIS_MAX", "4")),
        min_memory=int(env("JARVIS_TERMINAIS_MEM_MIN", "20")),
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    async with CoreClient.connect(url, s.mcp_token.get_secret_value()) as core:
        brain = JarvisBrain(
            llm,
            core,
            LocalTools(config=config, terminals=terminals.snapshot, control=control),
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
        )
        brain.speaker.prefetch(FILLERS)
        server = JarvisServer(brain)
        server.control = control
        control.broadcast = server.broadcast
        server.greeting = lambda: [events.terminals(terminals.snapshot())]
        if present():
            words = tuple(w.strip() for w in env("JARVIS_WAKE_PALAVRAS").split(",") if w.strip())
            threshold = float(env("JARVIS_WAKE_LIMIAR", "0.2"))
            score = float(env("JARVIS_WAKE_PESO", "1.5"))
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
        watcher = asyncio.create_task(watch_terminals(terminals, server, control))
        watcher.add_done_callback(_log_task_error)
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
                    await control.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
