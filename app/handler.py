"""Processamento em background de uma mensagem já aceita. Fase 1: eco."""

import logging
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repo import log_outgoing
from app.types import IncomingMessage, OutgoingMessage

log = logging.getLogger(__name__)

# No SELF_CHAT_MODE as respostas do bot voltam pelo webhook como fromMe; a marca as identifica.
BOT_MARK = "🤖 "


class Sender(Protocol):
    async def send_text(self, out: OutgoingMessage) -> str | None: ...


async def handle_incoming(
    msg: IncomingMessage,
    *,
    owner_phone: str,
    sender: Sender,
    sessions: async_sessionmaker[AsyncSession],
    self_chat_mode: bool = False,
) -> None:
    if not msg.text:
        return
    prefix = BOT_MARK if self_chat_mode else ""
    reply = OutgoingMessage(to=owner_phone, text=f"{prefix}{msg.text}")
    try:
        wa_id = await sender.send_text(reply)
    except Exception:
        log.exception("falha ao enviar resposta para %s", msg.wa_message_id)
        return
    async with sessions.begin() as session:
        await log_outgoing(session, wa_id, reply.text)
    log.info("resposta enviada para %s", msg.wa_message_id)
