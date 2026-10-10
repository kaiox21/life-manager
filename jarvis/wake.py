"""Palavra de ativação: "Jarvis, [pedido]" sem segurar o atalho.

O app (Rust) captura o microfone enquanto a escuta está ligada e manda blocos PCM de 16 kHz ao
cérebro. Aqui: o VAD é o porteiro, um buffer circular guarda o começo da frase, o detector de
palavras-chave (sherpa-onnx, modelo inglês com vocabulário aberto) procura "Jarvis" e, ao achar,
o pedido é juntado até uma pausa e segue pelo caminho da voz de hoje
(openspec/changes/jarvis-wake-word, design, decisões 1 a 4).

Privacidade: o áudio só vive no buffer circular (1,5 s) e no pedido em andamento; nada vai para
disco nem para a rede. O log registra só a hora e a confiança de cada ativação.
"""

import asyncio
import logging
import re
import secrets
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)

RATE = 16_000
BLOCK_S = 0.1
BLOCK = int(RATE * BLOCK_S)
WORDS = ("JARVIS", "JARVES", "JAR VIS", "JAVIS")
# nome no começo da transcrição (o whisper às vezes escreve o nome de outro jeito)
_NAME = re.compile(
    r"^\s*(?:(?:ô|ó|oi|ei|ok|hey)\s*,?\s*)?(?:jarvis|jarves|jarbas|javis|jarvi)\b[\s,.!?:;…-]*",
    re.IGNORECASE,
)


def strip_name(text: str) -> str | None:
    """O pedido sem o nome do começo; None se a transcrição não começa com o nome
    (alarme falso: o detector achou "Jarvis" onde não tinha)."""
    m = _NAME.match(text)
    if m is None:
        return None
    rest = text[m.end() :].strip()
    return rest[:1].upper() + rest[1:] if rest else ""


class Spotter(Protocol):
    def accept(self, block: np.ndarray) -> bool: ...
    def reset(self) -> None: ...


class Gate(Protocol):
    def is_speech(self, block: np.ndarray) -> bool: ...


class SherpaSpotter:
    """Detector de palavras-chave do sherpa-onnx com as variantes de "Jarvis"."""

    def __init__(
        self,
        model_dir: Path,
        words: tuple[str, ...] = WORDS,
        threshold: float = 0.2,
        score: float = 1.5,
    ) -> None:
        import sentencepiece as spm
        import sherpa_onnx

        sp = spm.SentencePieceProcessor(model_file=str(model_dir / "bpe.model"))
        keywords = model_dir.parent / "jarvis-keywords.txt"
        keywords.write_text(
            "".join(
                " ".join(sp.encode(w.upper(), out_type=str)) + f" @{w.replace(' ', '_')}\n"
                for w in words
            )
        )
        name = "epoch-12-avg-2-chunk-16-left-64.int8.onnx"
        self._kws = sherpa_onnx.KeywordSpotter(
            tokens=str(model_dir / "tokens.txt"),
            encoder=str(model_dir / f"encoder-{name}"),
            decoder=str(model_dir / f"decoder-{name}"),
            joiner=str(model_dir / f"joiner-{name}"),
            keywords_file=str(keywords),
            num_threads=1,
            keywords_score=score,
            keywords_threshold=threshold,
            provider="cpu",
        )
        self._stream = self._kws.create_stream()

    def accept(self, block: np.ndarray) -> bool:
        self._stream.accept_waveform(RATE, block)
        hit = False
        while self._kws.is_ready(self._stream):
            self._kws.decode_stream(self._stream)
            if self._kws.get_result(self._stream):
                hit = True
                self._kws.reset_stream(self._stream)
        return hit

    def reset(self) -> None:
        self._stream = self._kws.create_stream()


IDLE, COLLECT, WAIT, BUSY = "ouvindo", "pedido", "esperando o pedido", "ocupado"


class WakeListener:
    """Máquina de estados da escuta, por blocos de 100 ms (tempo contado pelos blocos)."""

    def __init__(
        self,
        spotter: Spotter,
        gate: Gate,
        *,
        on_wake: Callable[[], None],
        on_request: Callable[[np.ndarray], None],
        on_nothing: Callable[[], None],
        paused: Callable[[], bool] = lambda: False,
        preroll_s: float = 1.5,
        lead_s: float = 0.5,
        silence_s: float = 0.8,
        max_request_s: float = 15.0,
        wait_s: float = 6.0,
    ) -> None:
        self._spotter = spotter
        self._gate = gate
        self._on_wake, self._on_request, self._on_nothing = on_wake, on_request, on_nothing
        self._paused = paused
        self._ring: deque[np.ndarray] = deque(maxlen=round(preroll_s / BLOCK_S))
        self._lead = round(lead_s / BLOCK_S)
        self._silence = round(silence_s / BLOCK_S)
        self._max = round(max_request_s / BLOCK_S)
        self._wait = round(wait_s / BLOCK_S)
        self._tail = np.zeros(0, np.float32)
        self.state = IDLE
        self._in_voice = False
        self._quiet = 0
        self._collected: list[np.ndarray] = []
        self._waited = 0
        self._spoke = False

    def feed(self, pcm16: bytes) -> None:
        audio = (
            np.frombuffer(pcm16[: len(pcm16) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768
        )
        audio = np.concatenate([self._tail, audio])
        n = len(audio) // BLOCK * BLOCK
        self._tail = audio[n:]
        for i in range(0, n, BLOCK):
            self._block(audio[i : i + BLOCK])

    def _block(self, b: np.ndarray) -> None:
        if self._paused():
            if self.state == WAIT:
                # o resumo está sendo falado: a espera do pedido começa quando ele termina
                self._collected, self._waited, self._spoke, self._quiet = [], 0, False, 0
            elif self.state in (IDLE, COLLECT):
                self._to_idle()
            self._ring.clear()
            return
        if self.state == BUSY:
            return
        speech = self._gate.is_speech(b)
        if self.state == IDLE:
            self._idle(b, speech)
        elif self.state == COLLECT:
            self._collect(b, speech, started=True)
        elif self.state == WAIT:
            self._collect(b, speech, started=False)

    def _idle(self, b: np.ndarray, speech: bool) -> None:
        if speech and not self._in_voice:
            self._in_voice = True
            for old in list(self._ring)[-self._lead :]:  # o começo da palavra, antes do VAD
                self._spotter.accept(old)
        self._ring.append(b)
        if not self._in_voice:
            return
        self._quiet = 0 if speech else self._quiet + 1
        if self._spotter.accept(b):
            self.state = COLLECT
            self._collected = list(self._ring)  # o pedido começa com o nome
            self._quiet = 0
            self._on_wake()
            return
        if self._quiet > self._lead:  # pausa: a próxima fala começa do zero
            self._in_voice = False
            self._spotter.reset()

    def _collect(self, b: np.ndarray, speech: bool, started: bool) -> None:
        if not started and not self._spoke:
            self._waited += 1
            if not speech:
                if self._waited >= self._wait:
                    self.state = BUSY
                    self._on_nothing()
                return
            self._spoke = True
        self._collected.append(b)
        self._quiet = 0 if speech else self._quiet + 1
        if self._quiet >= self._silence or len(self._collected) >= self._max:
            audio = np.concatenate(self._collected)
            self._collected = []
            self.state = BUSY
            self._on_request(audio)

    def wait_request(self) -> None:
        """Só o nome: espera o pedido (até `wait_s` sem fala)."""
        self.state = WAIT
        self._collected, self._waited, self._spoke, self._quiet = [], 0, False, 0

    def done(self) -> None:
        self._to_idle()

    def _to_idle(self) -> None:
        self.state = IDLE
        self._collected = []
        self._in_voice = False
        self._quiet = 0
        self._spotter.reset()


class WakeBrain(Protocol):
    def wake_paused(self) -> bool: ...
    async def wake_turn(self, rid: str, audio: np.ndarray, emit: Callable) -> str: ...
    async def briefing(self, rid: str, emit: Callable) -> None: ...
    def wake_idle(self) -> None: ...


Broadcast = Callable[..., Awaitable[None]]


class WakeService:
    """Liga a escuta ao cérebro e às interfaces. Criado só quando a escuta é ligada."""

    def __init__(
        self,
        brain: WakeBrain,
        make_spotter: Callable[[], Spotter],
        make_gate: Callable[[], Gate],
        broadcast: Broadcast,
        broadcast_ui: Broadcast,
    ) -> None:
        self._brain = brain
        self._make_spotter, self._make_gate = make_spotter, make_gate
        self._broadcast, self._broadcast_ui = broadcast, broadcast_ui
        self._listener: WakeListener | None = None
        self._rid = ""
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def on(self) -> bool:
        return self._listener is not None

    def set_listening(self, on: bool) -> None:
        if on and self._listener is None:
            self._listener = WakeListener(
                self._make_spotter(),
                self._make_gate(),
                on_wake=self._woke,
                on_request=self._request,
                on_nothing=self._nothing,
                paused=self._brain.wake_paused,
            )
            log.info("escuta da palavra 'Jarvis' ligada")
        elif not on and self._listener is not None:
            self._listener = None  # libera o detector (memória)
            log.info("escuta da palavra 'Jarvis' desligada")

    def feed(self, pcm16: bytes) -> None:
        if self._listener is not None:
            self._listener.feed(pcm16)

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _woke(self) -> None:
        from jarvis import events

        self._rid = "wake-" + secrets.token_hex(4)
        log.info("wake: palavra detectada")
        self._spawn(self._broadcast(events.wake(self._rid)))

    def _request(self, audio: np.ndarray) -> None:
        self._spawn(self._handle(audio))

    async def _handle(self, audio: np.ndarray) -> None:
        listener = self._listener
        try:
            result = await self._brain.wake_turn(self._rid, audio, self._broadcast_ui)
        except Exception:
            log.exception("wake: falha no pedido")
            result = "erro"
        if listener is None or listener is not self._listener:
            return
        if result == "so_nome":  # "Hey Jarvis" sozinho: resumo do dia e depois o pedido
            try:
                await self._brain.briefing(self._rid, self._broadcast_ui)
            except Exception:
                log.exception("wake: falha no resumo")
                listener.done()
                return
            listener.wait_request()
        else:
            listener.done()

    def _nothing(self) -> None:
        from jarvis import events

        listener = self._listener
        self._brain.wake_idle()
        self._spawn(self._broadcast_ui(events.no_speech(self._rid)))
        if listener is not None:
            listener.done()
