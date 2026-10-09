"""Áudio do Jarvis: VAD (houve fala?) e transcrição local com mlx-whisper.

Tudo roda no Mac; o áudio nunca sai da máquina nem é guardado. As bibliotecas pesadas
(mlx-whisper, pysilero-vad) são importadas sob demanda, para os testes e o núcleo não
dependerem delas.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

RATE = 16_000
DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo-q4"
MIN_SPEECH_S = 0.3
PAD_S = 0.25  # folga mantida em volta da fala ao cortar o silêncio
HINTS = ["Jarvis", "Spotify", "fatura", "reais", "agenda", "gasto"]


def pcm16_to_float(data: bytes, sample_rate: int) -> np.ndarray:
    """Int16 mono -> float32 em 16 kHz (reamostra por interpolação se preciso)."""
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if sample_rate != RATE and len(audio):
        n = int(len(audio) * RATE / sample_rate)
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(
            np.float32
        )
    return audio


@dataclass(frozen=True)
class Speech:
    audio: np.ndarray  # só o trecho com fala, com folga
    seconds: float


class Vad:
    """Silero VAD por blocos de 32 ms; devolve o trecho com fala ou None."""

    def __init__(self, threshold: float = 0.5) -> None:
        from pysilero_vad import SileroVoiceActivityDetector

        self._vad = SileroVoiceActivityDetector()
        self._chunk = self._vad.chunk_samples()
        self._threshold = threshold

    def trim(self, audio: np.ndarray) -> Speech | None:
        self._vad.reset()
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        first = last = None
        for i in range(0, len(pcm) - self._chunk + 1, self._chunk):
            prob = self._vad(pcm[i : i + self._chunk].tobytes())
            if prob >= self._threshold:
                first = i if first is None else first
                last = i + self._chunk
        if first is None or last is None:
            return None
        seconds = (last - first) / RATE
        if seconds < MIN_SPEECH_S:
            return None
        pad = int(PAD_S * RATE)
        start, end = max(0, first - pad), min(len(audio), last + pad)
        return Speech(audio=audio[start:end], seconds=seconds)


class Transcriber:
    """mlx-whisper carregado uma vez; transcreve em thread (um por vez)."""

    def __init__(self, model: str = DEFAULT_MODEL, hints: Callable[[], list[str]] | None = None):
        self._model = model
        self._hints = hints or (lambda: [])
        self._lock = asyncio.Lock()
        self._ready = False

    def _run(self, audio: np.ndarray) -> str:
        import mlx_whisper

        prompt = "Agenda e gastos: " + ", ".join(dict.fromkeys([*HINTS, *self._hints()])) + "."
        result: dict[str, Any] = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self._model,
            language="pt",
            initial_prompt=prompt,
            condition_on_previous_text=False,
        )
        self._ready = True
        return str(result.get("text", "")).strip()

    async def warmup(self) -> None:
        """Carrega (e baixa, na primeira vez) o modelo com 1 s de silêncio."""
        async with self._lock:
            await asyncio.to_thread(self._run, np.zeros(RATE, dtype=np.float32))
        log.info("whisper %s pronto", self._model)

    @property
    def ready(self) -> bool:
        return self._ready

    async def transcribe(self, audio: np.ndarray) -> tuple[str, int]:
        async with self._lock:
            t0 = time.monotonic()
            text = await asyncio.to_thread(self._run, audio)
            return text, int((time.monotonic() - t0) * 1000)
