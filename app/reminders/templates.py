"""Textos fixos dos avisos (sem LLM). Curtos, em português."""

from datetime import date, datetime

from app.agent.tools.base import br_date, brl
from app.clock import TZ

WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _day_label(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        return "hoje"
    if delta == 1:
        return "amanhã"
    return f"{WEEKDAYS[d.weekday()]} {d:%d/%m}"


def _lead(minutes: int) -> str:
    if minutes % 1440 == 0:
        days = minutes // 1440
        return "1 dia" if days == 1 else f"{days} dias"
    if minutes % 60 == 0:
        hours = minutes // 60
        return "1 h" if hours == 1 else f"{hours} h"
    return f"{minutes} min"


def event_reminder(
    title: str,
    occurrence: datetime,
    all_day: bool,
    kind: str,
    person: str | None,
    minutes_before: int,
    now: datetime,
) -> str:
    local = occurrence.astimezone(TZ)
    when = _day_label(local.date(), now.astimezone(TZ).date())
    if kind == "aniversario":
        who = person or title
        return f"🎂 {when.capitalize()} é aniversário: {who} ({local:%d/%m})."
    if all_day:
        return f"⏰ {title}: {when} ({br_date(local.date())}), dia inteiro."
    lead = f" — em {_lead(minutes_before)}" if minutes_before else ""
    return f"⏰ {title}: {when} às {local:%H:%M}{lead}."


def daily_summary(
    today: date,
    today_items: list[str],
    tomorrow_items: list[str],
    birthdays: list[tuple[date, str]],
) -> str:
    lines = [f"☀️ Bom dia! {WEEKDAYS[today.weekday()].capitalize()}, {today:%d/%m}."]
    if today_items:
        lines.append("Hoje:")
        lines += [f"• {item}" for item in today_items]
    if tomorrow_items:
        lines.append("Amanhã:")
        lines += [f"• {item}" for item in tomorrow_items]
    if birthdays:
        lines.append("Aniversários da semana:")
        lines += [f"• {_day_label(d, today)}: {name}" for d, name in birthdays]
    return "\n".join(lines)


def statement_alert(card: str, closing: date, due: date, total_cents: int, count: int) -> str:
    items = "1 lançamento" if count == 1 else f"{count} lançamentos"
    return (
        f"💳 A fatura do {card} fecha em 2 dias ({closing:%d/%m}). "
        f"Parcial: {brl(total_cents)} ({items}). Vence {br_date(due)}."
    )
