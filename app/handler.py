"""Processamento em background de uma mensagem já aceita."""

import base64
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.llm import LLM
from app.agent.service import Models, answer
from app.clock import Clock, system_clock
from app.db.models import Message, PaymentMethod, Person
from app.db.repo import log_outgoing
from app.integrations.gcal import CalendarClient, sync_pending
from app.integrations.transcribe import Transcriber
from app.types import IncomingMessage, Media, OutgoingMessage

log = logging.getLogger(__name__)

# No SELF_CHAT_MODE as respostas do bot voltam pelo webhook como fromMe; a marca as identifica.
BOT_MARK = "🤖 "
MAX_AUDIO_SECONDS = 180
MAX_IMAGE_BYTES = 10 * 1024 * 1024
FAILED = "Tive um problema para responder agora. Tenta de novo em instantes?"


class Sender(Protocol):
    async def send_text(self, out: OutgoingMessage) -> str | None: ...
    async def fetch_media(self, media: Media) -> str | None: ...


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
    transcriber: Transcriber | None = None


class _Refuse(Exception):
    """Mídia que não dá para processar: a mensagem vira a resposta."""


async def handle_incoming(msg: IncomingMessage, message_id: uuid.UUID, deps: Deps) -> None:
    prefix = BOT_MARK if deps.self_chat_mode else ""
    try:
        reply = await _process(msg, message_id, deps, prefix)
    except _Refuse as exc:
        reply = str(exc)
    except Exception:
        log.exception("falha ao processar %s", msg.wa_message_id)
        reply = FAILED
    if reply is None:
        return

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


async def _process(
    msg: IncomingMessage, message_id: uuid.UUID, deps: Deps, prefix: str
) -> str | None:
    common: dict[str, Any] = {
        "llm": deps.llm,
        "models": deps.models,
        "clock": deps.clock,
        "message_id": message_id,
        "strip_prefix": prefix,
    }
    if msg.type == "text":
        if not msg.text:
            return None
        async with deps.sessions.begin() as session:
            return await answer(session=session, text=msg.text, **common)

    if msg.media is None:
        return None
    data_b64 = msg.media.data_b64 or await deps.sender.fetch_media(msg.media)
    if not data_b64:
        raise _Refuse("Não consegui baixar o arquivo. Pode mandar de novo?")

    if msg.type == "audio":
        return await _audio(msg.media, data_b64, message_id, deps, common)

    # foto: só o tamanho é limitado; o arquivo não é guardado
    if len(data_b64) * 3 // 4 > MAX_IMAGE_BYTES:
        raise _Refuse("Imagem grande demais (máx. 10 MB). Pode mandar uma menor?")
    async with deps.sessions.begin() as session:
        return await answer(
            session=session,
            text=msg.text or "",
            source="foto",
            image=(msg.media.mimetype, data_b64),
            **common,
        )


async def _audio(
    media: Media, data_b64: str, message_id: uuid.UUID, deps: Deps, common: dict[str, Any]
) -> str:
    if media.seconds and media.seconds > MAX_AUDIO_SECONDS:
        raise _Refuse("Áudio longo demais (máx. 3 min). Pode resumir ou escrever?")
    if deps.transcriber is None:
        raise _Refuse("Não consigo ouvir áudio agora. Pode escrever?")
    async with deps.sessions() as session:
        hints = [
            *(await session.scalars(select(PaymentMethod.name))),
            *(await session.scalars(select(Person.name))),
        ]
    heard = await deps.transcriber.transcribe(base64.b64decode(data_b64), hints)
    if not heard.text:
        raise _Refuse("Não entendi o áudio. Pode repetir ou escrever?")
    step = {"name": "transcricao", "model": heard.model, "ms": heard.elapsed_ms, "ok": True}
    async with deps.sessions.begin() as session:
        # A transcrição vira o corpo da mensagem (histórico e auditoria); o áudio é descartado.
        await session.execute(
            update(Message).where(Message.id == message_id).values(body=heard.text)
        )
        reply = await answer(
            session=session, text=heard.text, source="audio", pre_steps=[step], **common
        )
    return f'🎙️ "{heard.text}"\n{reply}'


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
