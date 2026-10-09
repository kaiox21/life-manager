"""Fala do Jarvis: voz da Fish Audio (opcional, `.env`) ou o AVSpeechSynthesizer do macOS.

O sintetizador avisa por delegate quando cada frase começa e termina; para isso o NSRunLoop
da thread principal é bombeado por uma tarefa do asyncio a cada 20 ms (testado: primeiro
áudio em ~0,02 s; numa thread de fundo o delegate não dispara).
"""

import asyncio
import logging
import re
import subprocess
from collections.abc import Callable
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


class FishSynth:
    """Voz da Fish Audio (`reference_id` do `.env`), frase a frase.

    Cada frase é pedida assim que chega (a próxima baixa enquanto a anterior toca) e tocada
    com o AVAudioPlayer na ordem. Falhou a rede ou a API: a frase vai para a voz local
    (`fallback`) e a Fish fica de lado por alguns minutos.
    """

    def __init__(
        self,
        on_event: OnEvent,
        fallback: Synth,
        api_key: str,
        voice_id: str,
        model: str = "s2.1-pro-free",
        speed: float = 1.0,
        fetch: Callable[[str], Any] | None = None,
        play: Callable[[bytes], Any] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        import time

        self._on_event = on_event
        self._fallback = fallback
        self._key, self._voice, self._model, self._speed = api_key, voice_id, model, speed
        self._fetch = fetch or self._http_fetch
        self._play = play or _av_play
        self._clock = clock or time.monotonic
        self._queue: list[tuple[str, asyncio.Future[bytes]]] = []
        self._player: Any = None
        self._current = ""
        self._down_until = 0.0
        self._cache: dict[str, bytes] = {}
        self._http: Any = None

    def prefetch(self, texts: list[str]) -> None:
        """Frases fixas (enchimentos) baixadas uma vez: depois saem sem esperar a rede."""

        async def get(text: str) -> None:
            try:
                self._cache[text] = await self._fetch(text)
            except Exception:  # noqa: BLE001
                log.warning("não deu para guardar %r da Fish", text)

        for text in texts:
            task = asyncio.get_running_loop().create_task(get(text))
            _background.add(task)
            task.add_done_callback(_background.discard)

    def speak(self, text: str) -> None:
        if self._clock() < self._down_until:
            self._fallback.speak(text)
            return
        cached = self._cache.get(text)
        loop = asyncio.get_running_loop()
        if cached is not None:
            done: asyncio.Future[bytes] = loop.create_future()
            done.set_result(cached)
            self._queue.append((text, done))
            return
        self._queue.append((text, loop.create_task(self._fetch(text))))

    def stop(self) -> None:
        for _, task in self._queue:
            task.cancel()
        self._queue.clear()
        if self._player is not None:
            self._player.stop()
            self._player = None
            self._on_event("cancel", self._current)
        self._fallback.stop()

    def pump(self) -> None:
        self._fallback.pump()
        if self._player is not None:
            if self._player.isPlaying():
                return
            self._player = None
            self._on_event("finish", self._current)
        if not self._queue or not self._queue[0][1].done():
            return
        text, task = self._queue.pop(0)
        try:
            audio = task.result()
            self._player = self._play(audio)
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            log.warning(
                "voz da Fish falhou; usando a voz local por %ds", FISH_COOLDOWN_S, exc_info=True
            )
            self._down_until = self._clock() + FISH_COOLDOWN_S
            self._fallback.speak(text)
            for rest, pending in self._queue:  # o resto da resposta também vai para a local
                pending.cancel()
                self._fallback.speak(rest)
            self._queue.clear()
            return
        self._current = text
        self._on_event("start", text)

    async def _http_fetch(self, text: str) -> bytes:
        import httpx

        if self._http is None:  # conexão aberta reaproveitada: poupa o TLS a cada frase
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0))
        resp = await self._http.post(
            FISH_URL,
            headers={"Authorization": f"Bearer {self._key}", "model": self._model},
            json={
                "text": text,
                "reference_id": self._voice,
                "format": "mp3",
                "latency": "balanced",
                "prosody": {"speed": self._speed},
            },
        )
        resp.raise_for_status()
        return resp.content


def _av_play(audio: bytes) -> Any:
    import AVFoundation as AV
    import Foundation

    data = Foundation.NSData.dataWithBytes_length_(audio, len(audio))
    player, err = AV.AVAudioPlayer.alloc().initWithData_error_(data, None)
    if player is None:
        raise RuntimeError(f"áudio inválido: {err}")
    player.play()
    return player


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
