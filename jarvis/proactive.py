"""Jarvis proativo: fala os avisos do núcleo e dos terminais e pergunta pelos gastos às 21:30.

Nada aqui chama o modelo. Os avisos do núcleo vêm de `avisos_recentes` (MCP, só leitura) a cada
minuto; os de terminal chegam pelo `terminal(alert)`. Tudo passa por uma fila que só fala quando
pode: fora do silêncio (23:00 às 07:00), sem pausa, e com o Jarvis calado e sem pedido aberto.
A voz só informa: nenhum caminho daqui aprova ou nega um pedido de permissão.

Estado (pausa e "já perguntei hoje") em `proativo.json`, arquivo só do cérebro: o `config.json`
também é reescrito pelo app.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from typing import Any, Protocol

from jarvis import briefing
from jarvis.tts import split_sentences

log = logging.getLogger(__name__)

STATE_FILE = Path.home() / "Library/Application Support/Jarvis/proativo.json"
REMINDER_TEXT = "Senhor, nenhum gasto lançado hoje. Teve algum?"
STALE = 300.0  # aviso que esperou a vez por mais de 5 min perdeu o sentido
POLL_EVERY = 60.0
TERMINAL_GAP = 60.0  # um aviso falado por terminal por minuto
LONG_WORK = 120.0  # "terminou" só para trabalho de 2 min ou mais (o Stop vem a cada resposta)
MAX_PAUSE_MIN = 720


def parse_hhmm(text: str) -> dtime | None:
    try:
        h, m = text.strip().split(":")
        return dtime(int(h), int(m))
    except ValueError:
        return None


def parse_window(text: str) -> tuple[dtime, dtime] | None:
    """ "23:00-07:00" → (23:00, 07:00); vazio ou inválido desliga o silêncio."""
    try:
        start, end = (parse_hhmm(p) for p in text.split("-"))
    except ValueError:
        return None
    return (start, end) if start is not None and end is not None else None


def in_window(t: dtime, window: tuple[dtime, dtime] | None) -> bool:
    if window is None:
        return False
    start, end = window
    return start <= t < end if start <= end else t >= start or t < end


def terminal_speech(alert: dict[str, Any]) -> str | None:
    """O que falar de um aviso de terminal; None quando não vale a fala."""
    pasta = str(alert.get("pasta") or f"terminal {alert.get('numero', '')}").strip()
    if alert.get("tipo") == "permissao":
        tool = str(alert.get("ferramenta") or "uma ferramenta")
        return f"Senhor, o Claude Code do {pasta} está pedindo permissão para usar {tool}."
    if alert.get("tipo") == "terminou" and float(alert.get("duracao") or 0) >= LONG_WORK:
        return f"Senhor, o Claude Code do {pasta} terminou."
    return None  # "espera" e respostas curtas: ruído


class Brain(Protocol):
    speaker: Any
    clock: Callable[[], datetime]

    def wake_paused(self) -> bool: ...
    async def spending_reminder(self, rid: str, emit: Any, text: str) -> None: ...


class Core(Protocol):
    async def call(self, name: str, args: dict[str, Any]) -> Any: ...


class Wake(Protocol):
    def busy(self) -> bool: ...
    def expect_answer(self, rid: str) -> bool: ...


@dataclass
class _Item:
    text: str
    at: float
    kind: str  # aviso | lembrete


class Proactive:
    def __init__(
        self,
        brain: Brain,
        core: Core,
        broadcast_ui: Callable[[Any], Awaitable[None]],
        wake: Callable[[], Wake | None] = lambda: None,
        silence: str = "23:00-07:00",
        reminder: str = "21:30",
        state_file: Path = STATE_FILE,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._brain = brain
        self._core = core
        self._broadcast_ui = broadcast_ui
        self._wake = wake
        self._silence = parse_window(silence)
        self._reminder = parse_hhmm(reminder) if reminder.strip() else None
        self._state_file = state_file
        self._mono = monotonic
        self._queue: deque[_Item] = deque()
        self._by_terminal: dict[Any, float] = {}
        self._since = self._now()  # avisos de antes da subida não são falados
        self._last_poll = -POLL_EVERY
        self.on_change: Callable[[], None] = lambda: None  # o painel atualiza o botão Silenciar

    def _now(self) -> datetime:
        return self._brain.clock()

    # --- estado em disco

    def _state(self) -> dict[str, Any]:
        try:
            data = json.loads(self._state_file.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, **changes: Any) -> None:
        data = self._state() | changes
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(self._state_file)
        except OSError:
            log.exception("proativo: não consegui gravar o estado")

    # --- pausa (ferramenta silenciar_avisos e botão Silenciar)

    def paused_until(self) -> datetime | None:
        raw = self._state().get("pausa_ate")
        try:
            until = datetime.fromisoformat(raw) if raw else None
        except (TypeError, ValueError):
            return None
        return until if until is not None and until > self._now() else None

    def pause(self, minutes: int) -> dict[str, Any]:
        minutes = max(1, min(MAX_PAUSE_MIN, minutes))
        return self._pause_to(self._now() + timedelta(minutes=minutes))

    def pause_until_morning(self) -> dict[str, Any]:
        now = self._now()
        end = self._silence[1] if self._silence else dtime(7, 0)
        day = now.date() if now.time() < end else now.date() + timedelta(days=1)
        return self._pause_to(datetime.combine(day, end, tzinfo=now.tzinfo))

    def _pause_to(self, until: datetime) -> dict[str, Any]:
        self._save(pausa_ate=until.isoformat())
        self._queue.clear()
        log.info("proativo: avisos pausados até %s", f"{until:%d/%m %H:%M}")
        self.on_change()
        return {"status": "pausado", "ate": f"{until:%H:%M}", "dia": f"{until:%d/%m}"}

    def resume(self) -> dict[str, Any]:
        self._save(pausa_ate=None)
        log.info("proativo: avisos retomados")
        self.on_change()
        return {"status": "retomado"}

    def status(self) -> dict[str, Any]:
        until = self.paused_until()
        return {"pausa_ate": until.isoformat() if until else None}

    # --- entradas

    def terminal(self, alert: dict[str, Any]) -> None:
        text = terminal_speech(alert)
        if text is None:
            return
        key = alert.get("numero") or alert.get("pasta")
        now = self._mono()
        if now - self._by_terminal.get(key, -TERMINAL_GAP) < TERMINAL_GAP:
            return  # o mesmo terminal falou há pouco (ou o pedido chegou pelos dois caminhos)
        self._by_terminal[key] = now
        self._put(text, "aviso")

    def _put(self, text: str, kind: str) -> None:
        if self._quiet():
            return  # na madrugada ou pausado, o aviso não espera: fica só no WhatsApp/painel
        self._queue.append(_Item(text, self._mono(), kind))

    def _quiet(self) -> bool:
        return in_window(self._now().time(), self._silence) or self.paused_until() is not None

    async def poll_notices(self) -> None:
        try:
            result = await self._core.call("avisos_recentes", {"desde": self._since.isoformat()})
        except Exception:  # noqa: BLE001 (núcleo fora: tenta no próximo minuto)
            return
        data = getattr(result, "data", None)
        if not getattr(result, "ok", False) or not isinstance(data, list):
            return
        for notice in data:
            try:
                self._since = max(self._since, datetime.fromisoformat(str(notice["hora"])))
            except (KeyError, ValueError):
                continue
            text = briefing.spoken_notice(str(notice.get("tipo")), str(notice.get("texto", "")))
            if text:
                self._put(text, "aviso")

    async def check_reminder(self) -> None:
        """Às 21:30 (ou ao acordar depois disso, antes do silêncio), uma vez por dia, se não há
        gasto com data de hoje."""
        if self._reminder is None or self._quiet():
            return
        now = self._now()
        today = now.date().isoformat()
        if now.time() < self._reminder or self._state().get("lembrete_em") == today:
            return
        if any(i.kind == "lembrete" for i in self._queue):
            return
        try:
            result = await self._core.call("painel", {})
        except Exception:  # noqa: BLE001 (núcleo fora: sem dado, não pergunta)
            return
        data = getattr(result, "data", None)
        if not getattr(result, "ok", False) or not isinstance(data, dict) or "hoje" not in data:
            return
        if int((data.get("hoje") or {}).get("lancamentos") or 0) > 0:
            self._save(lembrete_em=today)  # o dia já tem gasto: nada a perguntar
            return
        self._put(REMINDER_TEXT, "lembrete")

    # --- fala

    def _can_speak(self) -> bool:
        if self._quiet() or self._brain.wake_paused():
            return False
        wake = self._wake()
        return not (wake is not None and wake.busy())

    async def tick(self) -> None:
        now = self._mono()
        while self._queue and now - self._queue[0].at > STALE:
            log.info("proativo: aviso descartado (esperou demais): %s", self._queue[0].text)
            self._queue.popleft()
        if self._quiet():
            self._queue.clear()
            return
        if not self._queue or not self._can_speak():
            return
        item = self._queue.popleft()
        log.info("proativo: falando %s", item.kind)
        speaker = self._brain.speaker
        if speaker is not None:
            for sentence in split_sentences(item.text):
                speaker.say(sentence)
        if item.kind == "lembrete":
            self._save(lembrete_em=self._now().date().isoformat())
            rid = "lembrete-" + secrets.token_hex(4)
            await self._brain.spending_reminder(rid, self._broadcast_ui, item.text)
            wake = self._wake()
            if wake is not None:
                wake.expect_answer(rid)

    async def step(self) -> None:
        """Um passo do laço (1 s): a cada minuto consulta o núcleo; sempre tenta falar."""
        if self._mono() - self._last_poll >= POLL_EVERY:
            self._last_poll = self._mono()
            await self.poll_notices()
            await self.check_reminder()
        await self.tick()

    async def run(self) -> None:
        while True:
            try:
                await self.step()
            except Exception:  # noqa: BLE001
                log.exception("proativo: falha no ciclo")
            await asyncio.sleep(1.0)
