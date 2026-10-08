"""Ocorrências de eventos recorrentes (rrule do iCalendar, via python-dateutil)."""

from datetime import date, datetime, time

from dateutil.rrule import rrulestr

from app.clock import TZ


def normalize_rrule(raw: str | None) -> str | None:
    """Aceita 'FREQ=YEARLY' ou 'RRULE:FREQ=YEARLY'; valida e devolve sem o prefixo."""
    if raw is None or not raw.strip():
        return None
    rule = raw.strip().removeprefix("RRULE:").strip()
    rrulestr(f"RRULE:{rule}", dtstart=datetime(2026, 1, 1))  # levanta ValueError se inválida
    return rule


def occurrences_between(
    starts_at: datetime, rrule: str | None, start: datetime, end: datetime
) -> list[datetime]:
    """Ocorrências em [start, end], em horário local de São Paulo."""
    first = starts_at.astimezone(TZ)
    if not rrule:
        return [first] if start <= first <= end else []
    naive = first.replace(tzinfo=None)
    rule = rrulestr(f"RRULE:{rrule}", dtstart=naive)
    return [
        d.replace(tzinfo=TZ)
        for d in rule.between(
            start.astimezone(TZ).replace(tzinfo=None),
            end.astimezone(TZ).replace(tzinfo=None),
            inc=True,
        )
    ]


def next_occurrence(starts_at: datetime, rrule: str | None, after: datetime) -> datetime | None:
    """Próxima ocorrência a partir de `after` (inclusive); sem rrule, o início se for futuro."""
    first = starts_at.astimezone(TZ)
    if not rrule:
        return first if first >= after else None
    rule = rrulestr(f"RRULE:{rrule}", dtstart=first.replace(tzinfo=None))
    found = rule.after(after.astimezone(TZ).replace(tzinfo=None), inc=True)
    return found.replace(tzinfo=TZ) if found else None


def day_bounds(day_from: date, day_to: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(day_from, time.min, tzinfo=TZ),
        datetime.combine(day_to, time.max, tzinfo=TZ),
    )
