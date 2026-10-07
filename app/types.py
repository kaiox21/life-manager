"""Tipos próprios do canal. O resto do código nunca vê o formato da Evolution API."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

MessageType = Literal["text", "audio", "image", "other"]


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    wa_message_id: str
    sender: str  # só dígitos, ex.: 5561999998888
    chat_jid: str
    from_me: bool
    is_group: bool
    is_broadcast: bool
    type: MessageType
    text: str | None
    sent_at: datetime | None


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    to: str
    text: str
