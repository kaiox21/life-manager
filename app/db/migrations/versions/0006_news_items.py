"""news_items: notícias do boletim diário e 'noticias' em sent_reminders

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("url", sa.Text(), nullable=False, unique=True),  # normalizada
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("resumo", sa.Text(), nullable=False, server_default=""),
        sa.Column("fonte", sa.Text(), nullable=False),
        sa.Column("tema", sa.Text(), nullable=False),
        sa.Column("futebol", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("posicao", sa.Integer(), nullable=False),
        sa.Column("edition", sa.Date(), nullable=False),  # dia do boletim, no fuso de Brasília
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id")),
        sa.Column("found_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
    )
    op.create_index("news_items_edition", "news_items", ["edition"])
    op.drop_constraint("sent_reminders_kind_check", "sent_reminders", type_="check")
    op.create_check_constraint(
        "sent_reminders_kind_check",
        "sent_reminders",
        "kind in ('evento','resumo','fatura','vagas','noticias')",
    )


def downgrade() -> None:
    op.drop_constraint("sent_reminders_kind_check", "sent_reminders", type_="check")
    op.create_check_constraint(
        "sent_reminders_kind_check",
        "sent_reminders",
        "kind in ('evento','resumo','fatura','vagas')",
    )
    op.drop_index("news_items_edition", "news_items")
    op.drop_table("news_items")
