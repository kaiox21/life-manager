"""Processamento em background de uma mensagem já aceita."""

import logging
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.llm import LLM
from app.agent.service import Models, answer
from app.clock import Clock, system_clock
from app.db.repo import log_outgoing
from app.integrations.gcal import CalendarClient, sync_pending
from app.types import IncomingMessage, OutgoingMessage

log = logging.getLogger(__name__)

# No SELF_CHAT_MODE as respostas do bot voltam pelo webhook como fromMe; a marca as identifica.
BOT_MARK = "🤖 "


class Sender(Protocol):
    async def send_text(self, out: OutgoingMessage) -> str | None: ...


@dataclass
class Deps:
    owner_phone: str
    sender: Sender
    sessions: async_sessionmaker[AsyncSession]
    llm: LLM
    models: Models
    self_chat_mode: bool = False
    clock: Clock = system_clock
    calendar: CalendarClient | None = None


async def handle_incoming(msg: IncomingMessage, message_id: object, deps: Deps) -> None:
    if not msg.text:
        return
    prefix = BOT_MARK if deps.self_chat_mode else ""
    try:
        async with deps.sessions.begin() as session:
            reply = await answer(
                llm=deps.llm,
                models=deps.models,
                session=session,
                clock=deps.clock,
                text=msg.text,
                message_id=message_id,  # type: ignore[arg-type]
                strip_prefix=prefix,
            )
    except Exception:
        log.exception("falha ao processar %s", msg.wa_message_id)
        reply = "Tive um problema para responder agora. Tenta de novo em instantes?"

    out = OutgoingMessage(to=deps.owner_phone, text=f"{prefix}{reply}")
    try:
        wa_id = await deps.sender.send_text(out)
    except Exception:
        log.exception("falha ao enviar resposta para %s", msg.wa_message_id)
        return
    async with deps.sessions.begin() as session:
        await log_outgoing(session, wa_id, out.text)
    log.info("resposta enviada para %s", msg.wa_message_id)
    await sync_calendar(deps)


async def sync_calendar(deps: Deps) -> None:
    """Espelha no Google Calendar o que mudou na agenda. Falha aqui não afeta a conversa."""
    if deps.calendar is None:
        return
    try:
        report = await sync_pending(deps.sessions, deps.calendar)
    except Exception:
        log.exception("sync com o Google Calendar falhou")
        return
    if report.created or report.updated or report.deleted or report.failed:
        log.info(
            "calendar: %d criados, %d atualizados, %d removidos, %d falhas",
            report.created,
            report.updated,
            report.deleted,
            len(report.failed),
        )
