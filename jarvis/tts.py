"""Fala do Jarvis: voz da Fish Audio (opcional, `.env`) ou o AVSpeechSynthesizer do macOS.

O sintetizador avisa por delegate quando cada frase começa e termina; para isso o NSRunLoop
da thread principal é bombeado por uma tarefa do asyncio a cada 20 ms (testado: primeiro
áudio em ~0,02 s; numa thread de fundo o delegate não dispara).
"""

import asyncio
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


class PortAudioOut:
    """Saída pelo PortAudio (`sounddevice`), aberta uma vez e reaproveitada."""

    def __init__(self, rate: int) -> None:
        import sounddevice as sd

        self._sd, self._rate = sd, rate
        self._stream = self._open()

    def _open(self) -> Any:
        stream = self._sd.RawOutputStream(
            samplerate=self._rate, channels=1, dtype="int16", latency="low"
        )
        stream.start()
        return stream

    @property
    def latency(self) -> float:
        return float(self._stream.latency)

    def write(self, data: bytes) -> None:
        self._stream.write(data)

    def abort(self) -> None:
        self._stream.abort()
        self._stream.close()
        self._stream = self._open()


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
        speed: float = 1.0,
        chunks: Chunks | None = None,
        out: AudioOut | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        import time

        self._on_event = on_event
        self._fallback = fallback
        self._key, self._voice, self._model, self._speed = api_key, voice_id, model, speed
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
            await asyncio.to_thread(out.write, data)
        if pending[: len(pending) - len(pending) % 2]:
            if not started:
                self._current = text
                self._on_event("start", text)
                started = True
            await asyncio.to_thread(out.write, pending[: len(pending) - len(pending) % 2])
        if started:
            await asyncio.sleep(getattr(out, "latency", 0.0))  # o fim ainda está no buffer
            self._current = ""
            self._on_event("finish", text)
        return True

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
                "latency": "balanced",
                "prosody": {"speed": self._speed},
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
            return FishSynth(cb, local(cb), fish_key, fish_voice, speed=fish_speed)
        return local(cb)

    return Speaker(make, on_event)
