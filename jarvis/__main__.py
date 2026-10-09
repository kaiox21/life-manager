"""Sobe o cérebro do Jarvis: uv run python -m jarvis

Lê o mesmo .env do núcleo (modelos, provedor, MCP_TOKEN). Variáveis próprias:
  JARVIS_CORE_URL        endereço do núcleo (padrão: Docker local; depois do VPS, o Tailscale)
  JARVIS_WHISPER_MODEL   repositório do mlx-whisper (padrão: whisper-large-v3-turbo-q4)
  JARVIS_VOICE / JARVIS_VOICE_RATE   voz e velocidade da fala (padrão: Luciana, 0.52)
  JARVIS_FILLER          "um instante, senhor" ao chamar ferramenta em modo voz (padrão: true)
  FISH_API_KEY / FISH_VOICE_ID / FISH_VOICE_SPEED   voz da Fish Audio (vazio = voz local)
Valem as do ambiente e, na falta, as do .env.
"""

import asyncio
import logging
import os

from dotenv import dotenv_values

from app.agent.llm import make_llm
from app.config import get_settings
from jarvis import events
from jarvis.agent import FILLERS, JarvisBrain
from jarvis.audio import DEFAULT_MODEL, Transcriber, Vad
from jarvis.local_tools import LocalTools, load_config
from jarvis.mcp_client import CoreClient
from jarvis.server import JarvisServer
from jarvis.terminals import Terminals
from jarvis.tts import make_speaker

log = logging.getLogger(__name__)
_DOTENV = {k: v for k, v in dotenv_values(".env").items() if v is not None}


def env(name: str, default: str = "") -> str:
    """Ambiente primeiro; depois o .env (o pydantic lê o .env, mas não o exporta)."""
    return os.environ.get(name) or _DOTENV.get(name) or default


def _log_task_error(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and task.exception():
        log.error("tarefa em segundo plano falhou: %r", task.exception())


async def watch_terminals(terminals: Terminals, server: JarvisServer) -> None:
    """Lê os eventos dos hooks do Claude Code e avisa as interfaces (a cada 300 ms)."""
    while True:
        try:
            changed, alerts = terminals.poll()
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

    async with CoreClient.connect(url, s.mcp_token.get_secret_value()) as core:
        brain = JarvisBrain(
            llm,
            core,
            LocalTools(config=config, terminals=terminals.snapshot),
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
        server.greeting = lambda: [events.terminals(terminals.snapshot())]
        watcher = asyncio.create_task(watch_terminals(terminals, server))
        watcher.add_done_callback(_log_task_error)
        async with server.run(port=int(env("JARVIS_PORT", "0"))):
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
