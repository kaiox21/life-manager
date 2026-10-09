"""Fala local do Jarvis com o AVSpeechSynthesizer do macOS, dirigido pelo asyncio.

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


def make_speaker(on_event: OnEvent | None, voice: str, rate: float) -> Speaker:
    def make(cb: OnEvent) -> Synth:
        try:
            return AVSynth(cb, voice, rate)
        except Exception:  # noqa: BLE001
            log.warning("AVFoundation indisponível; usando `say`")
            return SayFallback(cb, voice)

    return Speaker(make, on_event)
