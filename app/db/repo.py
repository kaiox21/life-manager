import uuid

from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message
from app.types import IncomingMessage


async def register_incoming(session: AsyncSession, msg: IncomingMessage) -> uuid.UUID | None:
    """Grava a mensagem recebida. Devolve None se o wa_message_id já existia (webhook repetido)."""
    stmt = (
        pg_insert(Message)
        .values(
            wa_message_id=msg.wa_message_id,
            channel="whatsapp",
            direction="in",
            type=msg.type,
            body=msg.text,  # áudio: preenchido depois com a transcrição
        )
        .on_conflict_do_nothing(index_elements=[Message.wa_message_id])
        .returning(Message.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def log_outgoing(session: AsyncSession, wa_message_id: str | None, text: str) -> None:
    await session.execute(
        insert(Message).values(
            wa_message_id=wa_message_id,
            channel="whatsapp",
            direction="out",
            type="text",
            body=text,
        )
    )
