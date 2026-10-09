"""Sobe o cérebro do Jarvis: uv run python -m jarvis

Lê o mesmo .env do núcleo (modelos, provedor, MCP_TOKEN). Variáveis próprias:
  JARVIS_CORE_URL        endereço do núcleo (padrão: Docker local; depois do VPS, o Tailscale)
  JARVIS_WHISPER_MODEL   repositório do mlx-whisper (padrão: whisper-large-v3-turbo-q4)
  JARVIS_VOICE / JARVIS_VOICE_RATE   voz e velocidade da fala (padrão: Luciana, 0.52)
  JARVIS_FILLER          "deixa eu ver…" ao chamar ferramenta em modo voz (padrão: true)
"""

import asyncio
import logging
import os

from app.agent.llm import make_llm
from app.config import get_settings
from jarvis.agent import JarvisBrain
from jarvis.audio import DEFAULT_MODEL, Transcriber, Vad
from jarvis.local_tools import LocalTools, load_config
from jarvis.mcp_client import CoreClient
from jarvis.server import JarvisServer
from jarvis.tts import make_speaker

log = logging.getLogger(__name__)


def _log_task_error(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and task.exception():
        log.error("tarefa em segundo plano falhou: %r", task.exception())


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    s = get_settings()
    config = load_config()
    llm = make_llm(s)
    url = os.environ.get("JARVIS_CORE_URL", "http://localhost:8000/mcp/")

    vad = None
    try:
        vad = Vad()
    except Exception:  # noqa: BLE001
        log.warning("VAD indisponível (pysilero-vad); a voz não vai cortar o silêncio")
    transcriber = Transcriber(
        os.environ.get("JARVIS_WHISPER_MODEL", DEFAULT_MODEL),
        hints=lambda: list(config.get("vocabulario") or []),
    )
    warmup = asyncio.create_task(transcriber.warmup())
    warmup.add_done_callback(_log_task_error)

    async with CoreClient.connect(url, s.mcp_token.get_secret_value()) as core:
        brain = JarvisBrain(
            llm,
            core,
            LocalTools(config=config),
            primary=os.environ.get("JARVIS_MODEL_PRIMARY", s.model_primary),
            escalation=os.environ.get("JARVIS_MODEL_ESCALATION", s.model_escalation),
            transcriber=transcriber,
            vad=vad,
            filler=os.environ.get("JARVIS_FILLER", "true").lower() != "false",
        )
        brain.speaker = make_speaker(
            brain.on_speech_event,
            voice=os.environ.get("JARVIS_VOICE", "Luciana"),
            rate=float(os.environ.get("JARVIS_VOICE_RATE", "0.52")),
        )
        async with JarvisServer(brain).run(port=int(os.environ.get("JARVIS_PORT", "0"))):
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
