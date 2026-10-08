"""O que enviar em cada job, a partir de um `now` injetado. Quem envia é delivery.py."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import TZ
from app.db.models import Event, Expense, PaymentMethod, Person
from app.domain.billing import closing_date, due_date, open_statement_month
from app.domain.recurrence import day_bounds, occurrences_between
from app.reminders import templates

ALL_DAY_ANCHOR = time(9, 0)  # dia inteiro: antecedência conta a partir das 09:00
LATE_LIMIT = timedelta(hours=6)  # lembrete atrasado ainda vale por até 6 h
START_TOLERANCE = timedelta(minutes=5)  # e só se o evento não começou há mais que isso
STATEMENT_LEAD = timedelta(days=2)
SUMMARY_REF = uuid.UUID(int=0)  # ref_id fixo do resumo do dia


@dataclass(frozen=True)
class Notice:
    kind: str  # evento | resumo | fatura
    ref_id: uuid.UUID
    occurrence_at: datetime
    minutes_before: int
    text: str


def _anchor(occurrence: datetime, all_day: bool) -> datetime:
    local = occurrence.astimezone(TZ)
    return datetime.combine(local.date(), ALL_DAY_ANCHOR, tzinfo=TZ) if all_day else local


async def _events_with_people(session: AsyncSession) -> list[tuple[Event, Person | None]]:
    rows = await session.execute(
        select(Event, Person)
        .outerjoin(Person, Person.id == Event.person_id)
        .where(Event.deleted_at.is_(None))
    )
    return [(ev, person) for ev, person in rows.all()]


async def event_reminders(session: AsyncSession, now: datetime) -> list[Notice]:
    notices = []
    for ev, person in await _events_with_people(session):
        for minutes in ev.remind_minutes or []:
            lead = timedelta(minutes=minutes)
            # ocorrências cujo aviso (âncora - antecedência) pode ter caído na janela
            start = now - LATE_LIMIT + lead - timedelta(days=1)
            end = now + lead + timedelta(days=1)
            for occ in occurrences_between(ev.starts_at, ev.rrule, start, end):
                anchor = _anchor(occ, ev.all_day)
                due = anchor - lead
                if not (due <= now and now - due <= LATE_LIMIT):
                    continue
                if now > anchor + START_TOLERANCE:
                    continue  # o evento já começou
                notices.append(
                    Notice(
                        "evento",
                        ev.id,
                        occ,
                        minutes,
                        templates.event_reminder(
                            ev.title,
                            occ,
                            ev.all_day,
                            ev.kind,
                            person.name if person else None,
                            minutes,
                            now,
                        ),
                    )
                )
    return notices


def _item(ev: Event, occ: datetime, person: Person | None) -> str:
    when = "dia inteiro" if ev.all_day else occ.astimezone(TZ).strftime("%H:%M")
    who = f" ({person.name})" if person and person.name.lower() not in ev.title.lower() else ""
    return f"{when} {ev.title}{who}"


async def daily_summary(session: AsyncSession, now: datetime) -> list[Notice]:
    today = now.astimezone(TZ).date()
    rows = await _events_with_people(session)

    def on(day: date) -> list[str]:
        start, end = day_bounds(day, day)
        found = [
            (occ, ev, person)
            for ev, person in rows
            if ev.kind != "aniversario"
            for occ in occurrences_between(ev.starts_at, ev.rrule, start, end)
        ]
        found.sort(key=lambda t: (not t[1].all_day, t[0]))
        return [_item(ev, occ, person) for occ, ev, person in found]

    start, end = day_bounds(today, today + timedelta(days=6))
    birthdays = sorted(
        (occ.astimezone(TZ).date(), person.name if person else ev.title)
        for ev, person in rows
        if ev.kind == "aniversario"
        for occ in occurrences_between(ev.starts_at, ev.rrule, start, end)
    )
    today_items, tomorrow_items = on(today), on(today + timedelta(days=1))
    if not (today_items or tomorrow_items or birthdays):
        return []  # dia sem nada: silêncio
    occurrence = datetime.combine(today, time.min, tzinfo=TZ)
    text = templates.daily_summary(today, today_items, tomorrow_items, birthdays)
    return [Notice("resumo", SUMMARY_REF, occurrence, 0, text)]


async def statement_alerts(session: AsyncSession, now: datetime) -> list[Notice]:
    today = now.astimezone(TZ).date()
    cards = (
        await session.scalars(
            select(PaymentMethod).where(
                PaymentMethod.active.is_(True),
                PaymentMethod.kind == "credito",
                PaymentMethod.closing_day.is_not(None),
                PaymentMethod.due_day.is_not(None),
            )
        )
    ).all()
    notices = []
    for pm in cards:
        assert pm.closing_day is not None and pm.due_day is not None
        closing = closing_date(today.replace(day=1), pm.closing_day)
        if today != closing - STATEMENT_LEAD:
            continue
        statement = open_statement_month(today, pm.closing_day, pm.due_day)
        total, count = (
            await session.execute(
                select(func.coalesce(func.sum(Expense.amount_cents), 0), func.count()).where(
                    Expense.deleted_at.is_(None),
                    Expense.payment_method_id == pm.id,
                    Expense.statement_month == statement,
                )
            )
        ).one()
        text = templates.statement_alert(
            pm.name, closing, due_date(statement, pm.due_day), int(total), count
        )
        occurrence = datetime.combine(closing, time.min, tzinfo=TZ)
        notices.append(Notice("fatura", pm.id, occurrence, 0, text))
    return notices
