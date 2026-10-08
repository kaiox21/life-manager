"""Entrega idempotente: reserva em sent_reminders, envia e registra em messages."""

import logging
from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import SentReminder
from app.db.repo import log_outgoing
from app.reminders.jobs import Notice
from app.types import OutgoingMessage

log = logging.getLogger(__name__)


class SendsText(Protocol):
    async def send_text(self, out: OutgoingMessage) -> str | None: ...


async def deliver(
    notices: Sequence[Notice],
    *,
    sessions: async_sessionmaker[AsyncSession],
    sender: SendsText,
    owner_phone: str,
    prefix: str = "",
) -> int:
    """Envia o que ainda não foi enviado. Devolve quantos avisos saíram."""
    sent = 0
    for notice in notices:
        async with sessions.begin() as session:
            reserved = await session.scalar(
                insert(SentReminder)
                .values(
                    kind=notice.kind,
                    ref_id=notice.ref_id,
                    occurrence_at=notice.occurrence_at,
                    minutes_before=notice.minutes_before,
                )
                .on_conflict_do_nothing(constraint="sent_reminders_once")
                .returning(SentReminder.id)
            )
        if reserved is None:
            continue  # já enviado (ou outro ciclo está enviando)
        out = OutgoingMessage(to=owner_phone, text=f"{prefix}{notice.text}")
        try:
            wa_id = await sender.send_text(out)
        except Exception:
            log.exception("falha ao enviar aviso %s; tento de novo no próximo ciclo", notice.kind)
            async with sessions.begin() as session:
                await session.execute(delete(SentReminder).where(SentReminder.id == reserved))
            continue
        async with sessions.begin() as session:
            await log_outgoing(session, wa_id, out.text)
        sent += 1
    return sent
