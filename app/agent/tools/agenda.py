"""Ferramentas do grupo "agenda": criar_evento, buscar_eventos, atualizar_evento, remover_evento.

As ferramentas só gravam no banco; o espelho no Google Calendar é feito depois do commit
(app/integrations/gcal.py), olhando gcal_synced_at x updated_at.
"""

import uuid
from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from sqlalchemy import func, or_, select

from app.agent.tools.base import Tool, ToolArgs, ToolContext, ToolError, br_date
from app.agent.tools.gastos import PENDING_TTL
from app.agent.tools.pessoas import resolve_person
from app.clock import TZ, today
from app.db.models import Event, PendingAction, Person
from app.domain.recurrence import day_bounds, next_occurrence, normalize_rrule, occurrences_between

Kind = Literal["compromisso", "prova", "aniversario", "prazo", "lembrete"]
MAX_RESULTS = 20
WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _local(dt: datetime | None) -> datetime | None:
    """Hora sem fuso vinda do modelo é horário de São Paulo."""
    if dt is None:
        return None
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def _midnight(dt: datetime) -> datetime:
    return datetime.combine(dt.astimezone(TZ).date(), time.min, tzinfo=TZ)


class EventFields(ToolArgs):
    """Campos editáveis de um evento (todos opcionais em atualizar_evento)."""

    title: str | None = Field(default=None, min_length=1)
    kind: Kind | None = None
    starts_at: datetime | None = Field(
        default=None, description="ISO 8601 com fuso. Ex.: '2026-10-09T14:00:00-03:00'"
    )
    ends_at: datetime | None = None
    all_day: bool | None = None
    rrule: str | None = Field(default=None, description="Ex.: 'FREQ=YEARLY' para aniversário")
    person: str | None = Field(default=None, description="Nome ou relação. Ex.: 'minha irmã'")
    remind_minutes: list[int] | None = Field(
        default=None, description="Antecedências do lembrete em minutos. Padrão [1440]"
    )
    location: str | None = None
    notes: str | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        return _local(v)

    @field_validator("rrule")
    @classmethod
    def _rrule(cls, v: str | None) -> str | None:
        try:
            return normalize_rrule(v)
        except ValueError as exc:
            raise ValueError(f"rrule inválida: {exc}") from exc

    @field_validator("remind_minutes")
    @classmethod
    def _reminders(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and any(m < 0 or m > 60 * 24 * 30 for m in v):
            raise ValueError("antecedências entre 0 e 43200 minutos")
        return v


class CriarEventoArgs(EventFields):
    title: str = Field(min_length=1, description="Título curto. Ex.: 'Dentista'")
    kind: Kind
    starts_at: datetime = Field(
        description=(
            "ISO 8601 com fuso. Dia inteiro: a data com 00:00. Ex.: '2026-10-09T14:00:00-03:00'"
        )
    )

    @model_validator(mode="after")
    def _defaults(self) -> "CriarEventoArgs":
        if self.kind == "aniversario":
            self.all_day = True
            self.rrule = self.rrule or "FREQ=YEARLY"
        if self.all_day:
            self.starts_at = _midnight(self.starts_at)
            self.ends_at = _midnight(self.ends_at) if self.ends_at else None
        if self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("ends_at antes de starts_at")
        return self


def _describe(ev: Event, person: Person | None, when: datetime | None = None) -> dict[str, Any]:
    at = (when or ev.starts_at).astimezone(TZ)
    item: dict[str, Any] = {
        "id": str(ev.id),
        "titulo": ev.title,
        "tipo": ev.kind,
        "data": f"{WEEKDAYS[at.weekday()]} {br_date(at.date())}",
        "hora": "dia inteiro" if ev.all_day else at.strftime("%H:%M"),
    }
    if ev.rrule:
        item["recorrencia"] = "todo ano" if ev.rrule == "FREQ=YEARLY" else ev.rrule
    if person:
        item["pessoa"] = person.name
    if ev.location:
        item["local"] = ev.location
    return item


def _summary(item: dict[str, Any]) -> str:
    text = f"{item['titulo']} — {item['data']}, {item['hora']}"
    if "recorrencia" in item:
        text += f" ({item['recorrencia']})"
    return text


async def _pending(
    ctx: ToolContext, tool: str, args: dict[str, Any], summary: str
) -> dict[str, Any]:
    pending = PendingAction(
        tool_name=tool, args=args, summary=summary, expires_at=ctx.clock() + PENDING_TTL
    )
    ctx.session.add(pending)
    await ctx.session.flush()
    return {
        "status": "aguardando_confirmacao",
        "pending_id": str(pending.id),
        "resumo": f"{summary}. Confirma?",
    }


async def criar_evento(ctx: ToolContext, args: CriarEventoArgs) -> dict[str, Any]:
    person = await resolve_person(ctx.session, args.person) if args.person else None
    if ctx.source != "texto":
        preview = Event(
            title=args.title,
            kind=args.kind,
            starts_at=args.starts_at,
            all_day=bool(args.all_day),
            rrule=args.rrule,
        )
        item = _describe(preview, person)
        item.pop("id")
        return await _pending(ctx, "criar_evento", args.model_dump(mode="json"), _summary(item))
    return await record_event(ctx, args, person)


async def record_event(
    ctx: ToolContext, args: CriarEventoArgs, person: Person | None = None
) -> dict[str, Any]:
    if person is None and args.person:
        person = await resolve_person(ctx.session, args.person)
    now = ctx.clock()
    ev = Event(
        title=args.title,
        kind=args.kind,
        starts_at=args.starts_at,
        ends_at=args.ends_at,
        all_day=bool(args.all_day),
        rrule=args.rrule,
        location=args.location,
        notes=args.notes,
        person_id=person.id if person else None,
        remind_minutes=args.remind_minutes or [1440],
        created_at=now,
        updated_at=now,
    )
    ctx.session.add(ev)
    await ctx.session.flush()
    item = _describe(ev, person)
    return {"status": "criado", "resumo": _summary(item), "evento": item}


class BuscarEventosArgs(ToolArgs):
    query: str | None = Field(default=None, description="Texto no título/notas. Ex.: 'dentista'")
    kind: Kind | None = None
    de: date | None = Field(default=None, description="AAAA-MM-DD, inclusive")
    ate: date | None = Field(default=None, description="AAAA-MM-DD, inclusive")
    person: str | None = Field(default=None, description="Nome ou relação. Ex.: 'minha irmã'")

    @model_validator(mode="after")
    def _range(self) -> "BuscarEventosArgs":
        if self.de and self.ate and self.de > self.ate:
            raise ValueError("'de' precisa ser antes ou igual a 'ate'")
        return self


async def buscar_eventos(ctx: ToolContext, args: BuscarEventosArgs) -> dict[str, Any]:
    filters = [Event.deleted_at.is_(None)]
    if args.kind:
        filters.append(Event.kind == args.kind)
    if args.person:
        person = await resolve_person(ctx.session, args.person)
        filters.append(Event.person_id == person.id)
    if args.query:
        pattern = f"%{args.query}%"
        filters.append(
            or_(
                func.unaccent(Event.title).ilike(func.unaccent(pattern)),
                func.unaccent(func.coalesce(Event.notes, "")).ilike(func.unaccent(pattern)),
            )
        )
    rows = (
        await ctx.session.execute(
            select(Event, Person).outerjoin(Person, Person.id == Event.person_id).where(*filters)
        )
    ).all()

    found: list[tuple[tuple[int, float], dict[str, Any]]] = []
    if args.de or args.ate:
        start, end = day_bounds(
            args.de or today(ctx.clock), args.ate or (args.de or today(ctx.clock))
        )
        for ev, person in rows:
            for when in occurrences_between(ev.starts_at, ev.rrule, start, end):
                found.append(((0, when.timestamp()), _describe(ev, person, when)))
    else:
        # Sem período: próxima ocorrência; eventos únicos já passados vêm depois dos futuros.
        start_of_today = day_bounds(today(ctx.clock), today(ctx.clock))[0]
        for ev, person in rows:
            when = next_occurrence(ev.starts_at, ev.rrule, start_of_today)
            past = when is None
            when = when or ev.starts_at
            item = _describe(ev, person, when)
            if past:
                item["ja_passou"] = True
            found.append(((1, -when.timestamp()) if past else (0, when.timestamp()), item))
    found.sort(key=lambda pair: pair[0])
    items = [item for _, item in found[:MAX_RESULTS]]
    return {"eventos": items, "total": len(found), "omitidos": max(len(found) - MAX_RESULTS, 0)}


class AtualizarEventoArgs(ToolArgs):
    event_id: uuid.UUID = Field(description="id devolvido por buscar_eventos")
    campos: EventFields = Field(description="Só os campos que mudam")


async def _load_event(ctx: ToolContext, event_id: uuid.UUID) -> Event:
    ev = await ctx.session.get(Event, event_id)
    if ev is None or ev.deleted_at is not None:
        raise ToolError("Evento não encontrado; use buscar_eventos para achar o id.")
    return ev


async def atualizar_evento(ctx: ToolContext, args: AtualizarEventoArgs) -> dict[str, Any]:
    ev = await _load_event(ctx, args.event_id)
    changes = args.campos.model_dump(exclude_unset=True)
    if not changes:
        raise ToolError("Nenhum campo para mudar.")
    if "person" in changes:
        person = (
            await resolve_person(ctx.session, changes.pop("person")) if args.campos.person else None
        )
        ev.person_id = person.id if person else None
    for key, value in changes.items():
        setattr(ev, key, value)
    if ev.all_day:
        ev.starts_at = _midnight(ev.starts_at)
    if ev.ends_at and ev.ends_at < ev.starts_at:
        raise ToolError("O fim ficaria antes do início.")
    ev.updated_at = ctx.clock()
    await ctx.session.flush()
    person = await ctx.session.get(Person, ev.person_id) if ev.person_id else None
    item = _describe(ev, person)
    return {"status": "atualizado", "resumo": _summary(item), "evento": item}


class RemoverEventoArgs(ToolArgs):
    event_id: uuid.UUID = Field(description="id devolvido por buscar_eventos")


async def remover_evento(ctx: ToolContext, args: RemoverEventoArgs) -> dict[str, Any]:
    """Nunca remove direto: sempre pede confirmação."""
    ev = await _load_event(ctx, args.event_id)
    person = await ctx.session.get(Person, ev.person_id) if ev.person_id else None
    summary = "Remover " + _summary(_describe(ev, person))
    return await _pending(ctx, "remover_evento", {"event_id": str(ev.id)}, summary)


async def delete_event(ctx: ToolContext, event_id: uuid.UUID) -> dict[str, Any]:
    ev = await _load_event(ctx, event_id)
    ev.deleted_at = ctx.clock()
    ev.updated_at = ctx.clock()
    await ctx.session.flush()
    return {
        "status": "removido",
        "resumo": f"{ev.title} ({br_date(ev.starts_at.astimezone(TZ).date())})",
    }


TOOLS = [
    Tool(
        "criar_evento",
        ("agenda",),
        "Cria evento na agenda. Ex.: 'dentista sexta às 14h' -> title='Dentista', "
        "kind='compromisso', starts_at='2026-10-09T14:00:00-03:00'. Aniversário: "
        "kind='aniversario', all_day=true, rrule='FREQ=YEARLY', person='Mariana'.",
        CriarEventoArgs,
        criar_evento,
    ),
    Tool(
        "buscar_eventos",
        ("agenda",),
        "Busca eventos por texto, tipo, pessoa e/ou período (de/ate). Devolve id, data e hora. "
        "Use antes de atualizar ou remover. Ex.: 'o que tenho amanhã' -> de=ate='2026-10-08'.",
        BuscarEventosArgs,
        buscar_eventos,
    ),
    Tool(
        "atualizar_evento",
        ("agenda",),
        "Altera um evento já encontrado com buscar_eventos. Ex.: event_id='<id>', "
        "campos={'starts_at': '2026-10-09T16:00:00-03:00'}.",
        AtualizarEventoArgs,
        atualizar_evento,
    ),
    Tool(
        "remover_evento",
        ("agenda",),
        "Pede para remover um evento já encontrado com buscar_eventos (o usuário confirma depois).",
        RemoverEventoArgs,
        remover_evento,
    ),
]
