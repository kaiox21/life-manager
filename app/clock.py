"""Fonte única de "agora". Os testes injetam um relógio fixo."""

from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(TZ)


def fixed_clock(at: datetime) -> Clock:
    if at.tzinfo is None:
        at = at.replace(tzinfo=TZ)
    return lambda: at


def today(clock: Clock) -> date:
    return clock().astimezone(TZ).date()
