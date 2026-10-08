"""agenda: pessoas e eventos

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "people",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("relation", sa.Text()),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "events",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("all_day", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("rrule", sa.Text()),
        sa.Column("location", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("person_id", UUID, sa.ForeignKey("people.id")),
        sa.Column(
            "remind_minutes", postgresql.ARRAY(sa.Integer()), server_default=sa.text("'{1440}'")
        ),
        sa.Column("gcal_event_id", sa.Text()),
        sa.Column("gcal_synced_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "kind in ('compromisso','prova','aniversario','prazo','lembrete')",
            name="events_kind_check",
        ),
    )
    op.create_index("events_starts_at_idx", "events", ["starts_at"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("people")
