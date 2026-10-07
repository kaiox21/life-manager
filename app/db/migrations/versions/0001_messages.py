"""tabela messages

Revision ID: 0001
Revises:
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("wa_message_id", sa.Text(), unique=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text()),
        sa.Column("type", sa.Text()),
        sa.Column("body", sa.Text()),
        sa.Column("media_path", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("channel in ('whatsapp','desktop')", name="messages_channel_check"),
        sa.CheckConstraint("direction in ('in','out')", name="messages_direction_check"),
    )


def downgrade() -> None:
    op.drop_table("messages")
