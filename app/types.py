"""Tipos próprios do canal. O resto do código nunca vê o formato da Evolution API."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

MessageType = Literal["text", "audio", "image", "other"]


@dataclass(frozen=True, slots=True)
class Media:
    mimetype: str
    data_b64: str | None  # None quando o webhook não trouxe o arquivo
    seconds: int | None = None  # duração do áudio
    # Referência opaca para o canal baixar o arquivo de novo, se data_b64 faltar.
    ref: dict[str, Any] = field(default_factory=dict, repr=False)


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
    media: Media | None = None


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    to: str
    text: str
