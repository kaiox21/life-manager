"""Fala do Jarvis: voz da Fish Audio (opcional, `.env`) ou o AVSpeechSynthesizer do macOS.

O sintetizador avisa por delegate quando cada frase começa e termina; para isso o NSRunLoop
da thread principal é bombeado por uma tarefa do asyncio a cada 20 ms (testado: primeiro
áudio em ~0,02 s; numa thread de fundo o delegate não dispara).
"""

import asyncio
import contextlib
import logging
import re
import subprocess
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

log = logging.getLogger(__name__)

SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")

# ("start", frase) quando uma frase começa; ("idle", "") quando não há mais nada para falar
OnEvent = Callable[[str, str], None]


def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in SENTENCE_END.split(text.strip()) if p.strip()]


class Synth(Protocol):
    """Backend de fala. Chama `on_event("start"|"finish"|"cancel", texto)` a partir de `pump()`."""

    def speak(self, text: str) -> None: ...
    def stop(self) -> None: ...
    def pump(self) -> None: ...


MakeSynth = Callable[[OnEvent], Synth]


class AVSynth:
    def __init__(self, on_event: OnEvent, voice: str = "Luciana", rate: float = 0.52) -> None:
        import AVFoundation as AV
        import Foundation
        import objc
        from Foundation import NSObject

        class Delegate(NSObject, protocols=[objc.protocolNamed("AVSpeechSynthesizerDelegate")]):
            def speechSynthesizer_didStartSpeechUtterance_(self, _s: Any, u: Any) -> None:
                on_event("start", str(u.speechString()))

            def speechSynthesizer_didFinishSpeechUtterance_(self, _s: Any, u: Any) -> None:
                on_event("finish", str(u.speechString()))

            def speechSynthesizer_didCancelSpeechUtterance_(self, _s: Any, u: Any) -> None:
                on_event("cancel", str(u.speechString()))

        self._av, self._f = AV, Foundation
        self._synth = AV.AVSpeechSynthesizer.alloc().init()
        self._delegate = Delegate.alloc().init()  # referência forte: o synth só guarda weak
        self._synth.setDelegate_(self._delegate)
        self._voice = next(
            (v for v in AV.AVSpeechSynthesisVoice.speechVoices() if v.name() == voice),
            AV.AVSpeechSynthesisVoice.voiceWithLanguage_("pt-BR"),
        )
        self._rate = rate
        self._loop = Foundation.NSRunLoop.currentRunLoop()

    def speak(self, text: str) -> None:
        u = self._av.AVSpeechUtterance.speechUtteranceWithString_(text)
        u.setVoice_(self._voice)
        u.setRate_(self._rate)
        self._synth.speakUtterance_(u)

    def stop(self) -> None:
        self._synth.stopSpeakingAtBoundary_(0)  # imediato

    def pump(self) -> None:
        self._loop.runUntilDate_(self._f.NSDate.dateWithTimeIntervalSinceNow_(0.001))


class SayFallback:
    """Backend com o comando `say` (0,8 s para começar); só se o AVFoundation faltar."""

    def __init__(self, on_event: OnEvent, voice: str = "Luciana") -> None:
        self._on_event = on_event
        self._voice = voice
        self._queue: list[str] = []
        self._proc: subprocess.Popen[bytes] | None = None
        self._current = ""

    def speak(self, text: str) -> None:
        self._queue.append(text)

    def stop(self) -> None:
        self._queue.clear()
        if self._proc is not None and self._proc.poll() is None:
            self._proc.kill()

    def pump(self) -> None:
        if self._proc is not None:
            if self._proc.poll() is None:
                return
            self._proc = None
            self._on_event("finish", self._current)
        if self._queue:
            self._current = self._queue.pop(0)
            self._proc = subprocess.Popen(["say", "-v", self._voice, self._current])
            self._on_event("start", self._current)


FISH_URL = "https://api.fish.audio/v1/tts"
_background: set[asyncio.Task[None]] = set()
FISH_COOLDOWN_S = 300  # depois de uma falha, usa a voz local por 5 min (sem esperar timeout)


class AudioOut(Protocol):
    """Saída de áudio contínua (PCM Int16 mono)."""

    def write(self, data: bytes) -> None: ...  # bloqueia até caber no buffer
    def abort(self) -> None: ...  # descarta o que está no buffer e reabre


_coreaudio: Any = None


def default_output_id() -> int | None:
    """Id da saída de áudio padrão do macOS, direto do CoreAudio (microssegundos depois da 1ª
    chamada). None fora do macOS ou se a consulta falhar."""
    global _coreaudio
    import ctypes
    import ctypes.util

    class _Address(ctypes.Structure):
        _fields_ = [  # noqa: RUF012 (estrutura do ctypes)
            ("selector", ctypes.c_uint32),
            ("scope", ctypes.c_uint32),
            ("element", ctypes.c_uint32),
        ]

    try:
        if _coreaudio is None:
            _coreaudio = ctypes.CDLL(ctypes.util.find_library("CoreAudio"))
        addr = _Address(
            int.from_bytes(b"dOut", "big"), int.from_bytes(b"glob", "big"), 0
        )  # kAudioHardwarePropertyDefaultOutputDevice, escopo global
        device, size = ctypes.c_uint32(0), ctypes.c_uint32(4)
        err = _coreaudio.AudioObjectGetPropertyData(
            1, ctypes.byref(addr), 0, None, ctypes.byref(size), ctypes.byref(device)
        )  # 1 = kAudioObjectSystemObject
        return int(device.value) if err == 0 else None
    except (OSError, AttributeError, TypeError):
        return None


class PortAudioOut:
    """Saída pelo PortAudio (`sounddevice`), reaproveitada enquanto a saída padrão do macOS for a
    mesma. Antes, aberta uma vez na subida, ficava presa ao dispositivo daquele momento: ligar ou
    tirar o fone (ou conectar AirPods) mandava a voz para o lugar errado ou para lugar nenhum
    (12/10/2026). O PortAudio guarda a lista de dispositivos de quando foi iniciado, então trocar
    de saída exige reiniciá-lo antes de reabrir."""

    def __init__(self, rate: int, current: Callable[[], int | None] = default_output_id) -> None:
        import sounddevice as sd

        self._sd, self._rate, self._current = sd, rate, current
        self._device = current()
        self._stream = self._open()

    def _open(self) -> Any:
        stream = self._sd.RawOutputStream(
            samplerate=self._rate, channels=1, dtype="int16", latency="low"
        )
        stream.start()
        return stream

    def follow_default(self) -> bool:
        """Antes de cada frase: se a saída padrão mudou, reabre nela. True se reabriu."""
        now = self._current()
        if now is None or now == self._device:
            return False
        log.info("saída de áudio mudou (%s → %s): reabrindo", self._device, now)
        self.reopen()
        self._device = now
        return True

    def reopen(self) -> None:
        with contextlib.suppress(Exception):
            self._stream.abort()
            self._stream.close()
        self._sd._terminate()  # a lista de dispositivos do PortAudio é a da inicialização
        self._sd._initialize()
        self._stream = self._open()

    @property
    def latency(self) -> float:
        return float(self._stream.latency)

    def write(self, data: bytes) -> None:
        try:
            self._stream.write(data)
        except Exception:  # noqa: BLE001 (o dispositivo sumiu no meio da frase)
            log.warning("saída de áudio falhou no meio da frase: reabrindo", exc_info=True)
            self._device = self._current()
            self.reopen()
            self._stream.write(data)

    def abort(self) -> None:
        self._stream.abort()
        self._stream.close()
        self._stream = self._open()


LEVEL_HZ = 15  # nível da voz para o orbe: ~15 por segundo (change jarvis-painel-hud)
LEVEL_FLOOR = 800.0  # RMS mínimo de referência (silêncio não vira "voz alta")

FISH_RATE = 24_000  # medido em 09/10/2026: em 44,1 kHz o 1º byte demora ~1,8 s; em 24 kHz, ~0,7 s
PREBUFFER = FISH_RATE * 2 // 10  # 0,1 s de áudio antes de começar a tocar (bytes Int16)
Chunks = Callable[[str], AsyncIterator[bytes]]


class FishSynth:
    """Voz da Fish Audio tocada enquanto chega (PCM em streaming), frase a frase.

    Cada frase começa a baixar assim que chega (a próxima baixa enquanto a anterior toca);
    um único tocador escreve as frases em ordem na saída de áudio, sem esperar a frase
    inteira (1º som em ~0,7 s em vez de ~1,8 s com MP3 inteiro). Falhou a rede ou a API
    antes de tocar: a frase e o resto vão para a voz local (`fallback`) e a Fish fica de
    lado por alguns minutos.
    """

    def __init__(
        self,
        on_event: OnEvent,
        fallback: Synth,
        api_key: str,
        voice_id: str,
        model: str = "s2.1-pro-free",
        latency: str = "normal",
        quality_guard: bool = True,
        speed: float = 1.0,
        chunks: Chunks | None = None,
        out: AudioOut | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        import time

        self._on_event = on_event
        self._fallback = fallback
        self._key, self._voice, self._model, self._speed = api_key, voice_id, model, speed
        # "normal" + quality-guard: a voz em "balanced" saía craquelada (A/B com o Kaio em
        # 12/10/2026); custa ~1,9 s a mais até a 1ª frase (0,7 s → 2,6 s), as seguintes baixam
        # enquanto a anterior toca
        self._latency, self._quality_guard = latency, quality_guard
        self._chunks = chunks or self._http_chunks
        self._out: AudioOut | None = out
        self._clock = clock or time.monotonic
        self._items: asyncio.Queue[tuple[str, asyncio.Queue[bytes | None]]] = asyncio.Queue()
        self._downloads: set[asyncio.Task[None]] = set()
        self._player: asyncio.Task[None] | None = None
        self._current = ""
        self._down_until = 0.0
        self._cache: dict[str, bytes] = {}
        self._http: Any = None
        # nível da voz tocada (0–1), entregue no instante em que o som sai (orbe do painel)
        self.on_level: Callable[[float], None] | None = None
        self._level_ref = LEVEL_FLOOR
        self._level_clock = 0.0
        self._level_calls: list[asyncio.TimerHandle] = []

    # --- interface do Synth

    def prefetch(self, texts: list[str]) -> None:
        """Frases fixas (enchimentos) baixadas uma vez: depois saem sem esperar a rede."""

        async def get(text: str) -> None:
            try:
                self._cache[text] = b"".join([c async for c in self._chunks(text)])
            except Exception:  # noqa: BLE001
                log.warning("não deu para guardar %r da Fish", text)

        for text in texts:
            _spawn(get(text))
        try:
            self._output()  # abrir a saída de áudio custa tempo: abre agora, não na 1ª fala
        except Exception:  # noqa: BLE001
            log.warning("saída de áudio indisponível", exc_info=True)

    def speak(self, text: str) -> None:
        if self._clock() < self._down_until:
            self._fallback.speak(text)
            return
        audio: asyncio.Queue[bytes | None] = asyncio.Queue()
        cached = self._cache.get(text)
        if cached is not None:
            audio.put_nowait(cached)
            audio.put_nowait(None)
        else:
            task = asyncio.get_running_loop().create_task(self._download(text, audio))
            self._downloads.add(task)
            task.add_done_callback(self._downloads.discard)
        self._items.put_nowait((text, audio))
        if self._player is None or self._player.done():
            self._player = asyncio.get_running_loop().create_task(self._play_all())

    def stop(self) -> None:
        for task in list(self._downloads):
            task.cancel()
        self._items = asyncio.Queue()
        if self._player is not None and not self._player.done():
            self._player.cancel()
            self._player = None
            if self._out is not None:
                self._out.abort()  # corta o que ainda estava no buffer
            self._levels_stop()
            if self._current:
                self._on_event("cancel", self._current)
                self._current = ""
        self._fallback.stop()

    def pump(self) -> None:
        self._fallback.pump()

    # --- internos

    async def _download(self, text: str, audio: asyncio.Queue[bytes | None]) -> None:
        try:
            async for chunk in self._chunks(text):
                audio.put_nowait(chunk)
            audio.put_nowait(None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            audio.put_nowait(exc)  # type: ignore[arg-type]

    async def _play_all(self) -> None:
        while not self._items.empty():
            text, audio = self._items.get_nowait()
            ok = await self._play(text, audio)
            if not ok:
                self._give_up(text)
                return

    async def _play(self, text: str, audio: asyncio.Queue[bytes | None]) -> bool:
        """Toca uma frase; False se a Fish falhou antes de sair qualquer som."""
        out = self._output()
        follow = getattr(out, "follow_default", None)
        if follow is not None:  # fone ligado ou tirado desde a última frase: segue a saída nova
            try:
                await asyncio.to_thread(follow)
            except Exception:  # noqa: BLE001
                log.warning("não consegui trocar de saída de áudio", exc_info=True)
        pending = b""
        started = False
        while True:
            chunk = await audio.get()
            if isinstance(chunk, Exception):
                if started:
                    log.warning("voz da Fish caiu no meio da frase", exc_info=chunk)
                    break
                log.warning("voz da Fish falhou", exc_info=chunk)
                return False
            if chunk is None:
                break
            pending += chunk
            if not started and len(pending) < PREBUFFER:
                continue
            cut = len(pending) - len(pending) % 2  # amostras Int16 inteiras
            if not cut:
                continue
            data, pending = pending[:cut], pending[cut:]
            if not started:
                started = True
                self._current = text
                self._on_event("start", text)
            self._levels(data, out)
            await asyncio.to_thread(out.write, data)
        if pending[: len(pending) - len(pending) % 2]:
            if not started:
                self._current = text
                self._on_event("start", text)
                started = True
            self._levels(pending[: len(pending) - len(pending) % 2], out)
            await asyncio.to_thread(out.write, pending[: len(pending) - len(pending) % 2])
        if started:
            self._level_at_end()
            await asyncio.sleep(getattr(out, "latency", 0.0))  # o fim ainda está no buffer
            self._current = ""
            self._on_event("finish", text)
        return True

    def _levels(self, data: bytes, out: Any) -> None:
        """RMS por janela de ~66 ms, agendado para quando o pedaço vai soar (no laço do asyncio,
        antes do `write` que roda numa thread): o pulso do orbe coincide com o som."""
        if self.on_level is None:
            return
        import numpy as np

        loop = asyncio.get_running_loop()
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        window = FISH_RATE // LEVEL_HZ
        at = max(loop.time() + float(getattr(out, "latency", 0.0)), self._level_clock)
        self._level_calls = [h for h in self._level_calls if not h.cancelled()][-64:]
        for i in range(0, len(samples), window):
            chunk = samples[i : i + window]
            rms = float(np.sqrt(np.mean(chunk * chunk))) if len(chunk) else 0.0
            self._level_ref = max(rms, self._level_ref * 0.98, LEVEL_FLOOR)
            self._level_calls.append(
                loop.call_at(at, self.on_level, min(1.0, rms / self._level_ref))
            )
            at += len(chunk) / FISH_RATE
        self._level_clock = at

    def _level_at_end(self) -> None:
        if self.on_level is not None:
            loop = asyncio.get_running_loop()
            at = max(loop.time(), self._level_clock)
            self._level_calls.append(loop.call_at(at, self.on_level, 0.0))

    def _levels_stop(self) -> None:
        for h in self._level_calls:
            h.cancel()
        self._level_calls = []
        self._level_clock = 0.0
        if self.on_level is not None:
            self.on_level(0.0)

    def _give_up(self, text: str) -> None:
        log.warning("usando a voz local por %ds", FISH_COOLDOWN_S)
        self._down_until = self._clock() + FISH_COOLDOWN_S
        for task in list(self._downloads):
            task.cancel()
        self._fallback.speak(text)
        while not self._items.empty():
            rest, _ = self._items.get_nowait()
            self._fallback.speak(rest)

    def _output(self) -> AudioOut:
        if self._out is None:
            self._out = PortAudioOut(FISH_RATE)
        return self._out

    async def _http_chunks(self, text: str) -> AsyncIterator[bytes]:
        import httpx

        if self._http is None:  # conexão aberta reaproveitada: poupa o TLS a cada frase
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0))
        async with self._http.stream(
            "POST",
            FISH_URL,
            headers={"Authorization": f"Bearer {self._key}", "model": self._model},
            json={
                "text": text,
                "reference_id": self._voice,
                "format": "pcm",
                "sample_rate": FISH_RATE,
                "latency": self._latency,
                "prosody": {"speed": self._speed},
                **({"features": ["quality-guard"]} if self._quality_guard else {}),
            },
        ) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes():
                yield chunk


def _spawn(coro: Any) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


class Speaker:
    """Fila de frases do Jarvis: `say()` enfileira, `stop()` corta tudo; avisa início e fim."""

    def __init__(self, make_synth: MakeSynth, on_event: OnEvent | None = None) -> None:
        self._on_event = on_event or (lambda _k, _t: None)
        self._synth = make_synth(self._synth_event)
        self._outstanding = 0
        self._speaking = False
        self._task = asyncio.get_running_loop().create_task(self._pump())

    @property
    def speaking(self) -> bool:
        return self._speaking

    def say(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self._outstanding += 1
        self._synth.speak(text)

    def stop(self) -> None:
        self._synth.stop()
        self._outstanding = 0
        self._set_speaking(False)

    def close(self) -> None:
        self._task.cancel()

    def set_on_level(self, on_level: Callable[[float], None]) -> None:
        """Nível da voz tocada (0–1) para o orbe; só a Fish dá o áudio (a reserva local não)."""
        if hasattr(self._synth, "on_level"):
            self._synth.on_level = on_level

    def prefetch(self, texts: list[str]) -> None:
        prefetch = getattr(self._synth, "prefetch", None)
        if prefetch is not None:
            prefetch(texts)

    async def _pump(self) -> None:
        while True:
            try:
                self._synth.pump()
            except Exception:  # noqa: BLE001
                log.exception("fala falhou")
            await asyncio.sleep(0.02)

    def _synth_event(self, kind: str, text: str) -> None:
        log.debug("fala: %s %s", kind, text[:40])
        if kind == "start":
            self._speaking = True
            self._on_event("start", text)
        else:
            self._outstanding = max(0, self._outstanding - 1)
            if self._outstanding == 0:
                self._set_speaking(False)

    def _set_speaking(self, on: bool) -> None:
        if self._speaking and not on:
            self._speaking = False
            self._on_event("idle", "")


def make_speaker(
    on_event: OnEvent | None,
    voice: str,
    rate: float,
    fish_key: str = "",
    fish_voice: str = "",
    fish_speed: float = 1.0,
    fish_latency: str = "normal",
    fish_quality_guard: bool = True,
) -> Speaker:
    """Voz da Fish Audio se houver chave e voz no `.env`; senão (ou se ela falhar), a local."""

    def local(cb: OnEvent) -> Synth:
        try:
            return AVSynth(cb, voice, rate)
        except Exception:  # noqa: BLE001
            log.warning("AVFoundation indisponível; usando `say`")
            return SayFallback(cb, voice)

    def make(cb: OnEvent) -> Synth:
        if fish_key and fish_voice:
            log.info("voz: Fish Audio (local de reserva)")
            return FishSynth(
                cb,
                local(cb),
                fish_key,
                fish_voice,
                speed=fish_speed,
                latency=fish_latency,
                quality_guard=fish_quality_guard,
            )
        return local(cb)

    return Speaker(make, on_event)
