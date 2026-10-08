"""Espelho unidirecional banco -> Google Calendar. Único módulo que conhece a API do Google.

Um evento precisa de sync quando gcal_synced_at é nulo ou anterior a updated_at. Falhas não
perdem nada: o evento continua pendente e é tentado de novo no próximo sync.
"""

import asyncio
import base64
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import TZ
from app.config import Settings
from app.db.models import Event

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
DEFAULT_DURATION = timedelta(hours=1)


class NotFoundError(Exception):
    """O evento não existe mais no Calendar (404/410)."""


class CalendarClient(Protocol):
    async def insert(self, body: dict[str, Any]) -> str: ...
    async def update(self, event_id: str, body: dict[str, Any]) -> None: ...
    async def delete(self, event_id: str) -> None: ...


def event_body(ev: Event) -> dict[str, Any]:
    start = ev.starts_at.astimezone(TZ)
    body: dict[str, Any] = {
        "summary": ev.title,
        "description": "\n".join(filter(None, [ev.notes, "Criado pelo assistente."])),
        "reminders": {"useDefault": False},
        "extendedProperties": {"private": {"life_manager_id": str(ev.id)}},
    }
    if ev.location:
        body["location"] = ev.location
    if ev.all_day:
        last_day = (ev.ends_at or ev.starts_at).astimezone(TZ).date()
        body["start"] = {"date": start.date().isoformat()}
        body["end"] = {"date": (last_day + timedelta(days=1)).isoformat()}  # fim exclusivo
    else:
        end = (ev.ends_at or ev.starts_at + DEFAULT_DURATION).astimezone(TZ)
        body["start"] = {"dateTime": start.isoformat(), "timeZone": "America/Sao_Paulo"}
        body["end"] = {"dateTime": end.isoformat(), "timeZone": "America/Sao_Paulo"}
    if ev.rrule:
        body["recurrence"] = [f"RRULE:{ev.rrule}"]
    return body


@dataclass
class SyncReport:
    created: int = 0
    updated: int = 0
    deleted: int = 0
    failed: list[str] = field(default_factory=list)


async def sync_pending(
    sessions: async_sessionmaker[AsyncSession], client: CalendarClient, limit: int = 50
) -> SyncReport:
    """Sincroniza eventos pendentes, um por transação (SKIP LOCKED evita sync duplo)."""
    report = SyncReport()
    skip: list[uuid.UUID] = []
    for _ in range(limit):
        async with sessions.begin() as session:
            filters = [
                or_(Event.gcal_synced_at.is_(None), Event.updated_at > Event.gcal_synced_at),
                # removido que nunca chegou ao Calendar: nada a fazer
                or_(Event.deleted_at.is_(None), Event.gcal_event_id.is_not(None)),
            ]
            if skip:
                filters.append(Event.id.not_in(skip))
            ev = await session.scalar(
                select(Event)
                .where(*filters)
                .order_by(Event.updated_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if ev is None:
                break
            try:
                await _sync_one(ev, client, report)
            except Exception as exc:  # noqa: BLE001 - falha do Calendar não derruba nada
                log.warning("sync do evento %s falhou: %s", ev.id, exc.__class__.__name__)
                report.failed.append(str(ev.id))
                skip.append(ev.id)
                continue
            ev.gcal_synced_at = ev.updated_at
    return report


async def _sync_one(ev: Event, client: CalendarClient, report: SyncReport) -> None:
    if ev.deleted_at is not None:
        with contextlib.suppress(NotFoundError):
            await client.delete(ev.gcal_event_id or "")
        report.deleted += 1
        return
    body = event_body(ev)
    if ev.gcal_event_id:
        try:
            await client.update(ev.gcal_event_id, body)
            report.updated += 1
            return
        except NotFoundError:
            log.info("evento %s sumiu do Calendar; recriando", ev.id)
    ev.gcal_event_id = await client.insert(body)
    report.created += 1


class GoogleCalendar:
    """Cliente real (google-api-python-client é síncrono: roda em thread)."""

    def __init__(self, credentials_info: dict[str, Any], calendar_id: str) -> None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_info(
            credentials_info, scopes=SCOPES
        )
        self._events = build("calendar", "v3", credentials=creds, cache_discovery=False).events()
        self._calendar_id = calendar_id

    async def _run(self, request: Any) -> Any:
        from googleapiclient.errors import HttpError

        try:
            return await asyncio.to_thread(request.execute)
        except HttpError as exc:
            if exc.resp.status in (404, 410):
                raise NotFoundError from exc
            raise

    async def insert(self, body: dict[str, Any]) -> str:
        created = await self._run(self._events.insert(calendarId=self._calendar_id, body=body))
        return str(created["id"])

    async def update(self, event_id: str, body: dict[str, Any]) -> None:
        await self._run(
            self._events.update(calendarId=self._calendar_id, eventId=event_id, body=body)
        )

    async def delete(self, event_id: str) -> None:
        await self._run(self._events.delete(calendarId=self._calendar_id, eventId=event_id))


def load_credentials(settings: Settings) -> dict[str, Any] | None:
    raw = settings.google_service_account_json.get_secret_value().strip()
    if raw:
        text = raw if raw.startswith("{") else base64.b64decode(raw).decode()
        return json.loads(text)
    if settings.google_service_account_file and Path(settings.google_service_account_file).exists():
        return json.loads(Path(settings.google_service_account_file).read_text())
    return None


def calendar_from_settings(settings: Settings) -> GoogleCalendar | None:
    """None quando o Calendar não está configurado: a agenda funciona só no banco."""
    info = load_credentials(settings)
    if not info or not settings.google_calendar_id:
        return None
    return GoogleCalendar(info, settings.google_calendar_id)
