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


_background: set[asyncio.Task[None]] = set()
WIRED_LIMIT = 2 * 1024**3  # cabe o whisper q4 (~0,64 GB) com folga


def _wire_memory() -> None:
    try:
        import mlx.core as mx

        mx.set_wired_limit(WIRED_LIMIT)
    except Exception:  # noqa: BLE001 — sem MLX (testes) ou macOS antigo: segue sem prender
        log.debug("sem wired limit do MLX", exc_info=True)


class Transcriber:
    """mlx-whisper carregado uma vez; transcreve em thread (um por vez)."""

    def __init__(self, model: str = DEFAULT_MODEL, hints: Callable[[], list[str]] | None = None):
        self._model = model
        self._hints = hints or (lambda: [])
        self._lock = asyncio.Lock()
        self._ready = False
        self._warming = False

    def _run(self, audio: np.ndarray, warm: bool = False) -> str:
        import mlx_whisper

        if warm:
            # Só acordar os pesos. Sem as dicas e sem novas tentativas: com silêncio, o
            # whisper repete o prompt e a temperatura sobe; levava 5–10 s (09/10/2026).
            options: dict[str, Any] = {"temperature": 0.0}
        else:
            hints = ", ".join(dict.fromkeys([*HINTS, *self._hints()]))
            options = {"initial_prompt": f"Agenda e gastos: {hints}."}
        result: dict[str, Any] = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self._model,
            language="pt",
            condition_on_previous_text=False,
            **options,
        )
        self._ready = True
        return str(result.get("text", "")).strip()

    async def warmup(self) -> None:
        """Carrega (e baixa, na primeira vez) o modelo com 1 s de silêncio.

        Também "prende" a memória do MLX (wired): sem isso, com o Mac sem RAM sobrando, o
        macOS manda os pesos para o swap quando o Jarvis fica parado e a próxima transcrição
        leva 6 s em vez de 0,9 s (medido em 09/10/2026).
        """
        _wire_memory()
        async with self._lock:
            await asyncio.to_thread(self._run, np.zeros(RATE, dtype=np.float32), True)
        log.info("whisper %s pronto", self._model)

    def prewarm(self) -> None:
        """Atalho apertado: acorda o modelo enquanto o Kaio fala (se não estiver ocupado)."""
        if self._lock.locked() or self._warming:
            return
        self._warming = True
        task = asyncio.get_running_loop().create_task(self._touch())
        _background.add(task)
        task.add_done_callback(_background.discard)

    async def _touch(self) -> None:
        async with self._lock:
            self._warming = False
            t0 = time.monotonic()
            await asyncio.to_thread(self._run, np.zeros(RATE // 4, dtype=np.float32), True)
            ms = int((time.monotonic() - t0) * 1000)
            if ms > 1500:
                log.info("whisper estava fora da memória: acordou em %dms", ms)

    @property
    def ready(self) -> bool:
        return self._ready

    async def transcribe(self, audio: np.ndarray) -> tuple[str, int]:
        async with self._lock:
            t0 = time.monotonic()
            text = await asyncio.to_thread(self._run, audio)
            return text, int((time.monotonic() - t0) * 1000)
