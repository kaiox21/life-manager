"""Transcrição de áudio. Fase 4: faster-whisper local (o áudio não sai da máquina)."""

import asyncio
import io
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Transcription:
    text: str
    model: str
    elapsed_ms: int


BASE_VOCABULARY = ["Pix", "reais", "crédito", "débito", "fatura", "parcelas", "agenda"]


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes, hints: list[str] | None = None) -> Transcription: ...


class FasterWhisper:
    """Carrega o modelo na primeira chamada e reaproveita; um áudio por vez."""

    def __init__(self, model: str = "small", cache_dir: str | None = None) -> None:
        self._model_name = model
        self._cache_dir = cache_dir
        self._model: Any = None
        self._lock = asyncio.Lock()

    def _load(self) -> Any:
        from faster_whisper import WhisperModel

        log.info("carregando whisper %s", self._model_name)
        return WhisperModel(
            self._model_name, device="cpu", compute_type="int8", download_root=self._cache_dir
        )

    def _run(self, audio: bytes, hints: list[str]) -> str:
        if self._model is None:
            self._model = self._load()
        # Vocabulário do domínio (e nomes cadastrados) ajuda o modelo a não trocar "Pix" por "PICS".
        prompt = "Gastos e agenda: " + ", ".join(dict.fromkeys([*BASE_VOCABULARY, *hints])) + "."
        segments, _ = self._model.transcribe(
            io.BytesIO(audio), language="pt", vad_filter=True, beam_size=5, initial_prompt=prompt
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    async def warmup(self) -> None:
        """Carrega o modelo antes do primeiro áudio (~30 s na primeira vez, baixa ~0,5 GB)."""
        async with self._lock:
            if self._model is None:
                self._model = await asyncio.to_thread(self._load)
        log.info("whisper %s pronto", self._model_name)

    async def transcribe(self, audio: bytes, hints: list[str] | None = None) -> Transcription:
        async with self._lock:
            started = time.monotonic()
            text = await asyncio.to_thread(self._run, audio, hints or [])
        return Transcription(
            text=text,
            model=f"faster-whisper/{self._model_name}",
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
