import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("channel in ('whatsapp','desktop')", name="messages_channel_check"),
        CheckConstraint("direction in ('in','out')", name="messages_direction_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    wa_message_id: Mapped[str | None] = mapped_column(Text, unique=True)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    media_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
