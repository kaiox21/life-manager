"""gastos: meios de pagamento, categorias, despesas, pendências e agent_runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def _id() -> sa.Column:
    return sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now())


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.create_table(
        "payment_methods",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("closing_day", sa.Integer()),
        sa.Column("due_day", sa.Integer()),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'")),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.CheckConstraint(
            "kind in ('credito','debito','pix','dinheiro')", name="payment_methods_kind_check"
        ),
    )
    op.create_table(
        "categories",
        _id(),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("parent_id", UUID, sa.ForeignKey("categories.id")),
    )
    op.create_table(
        "expenses",
        _id(),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("merchant", sa.Text()),
        sa.Column("category_id", UUID, sa.ForeignKey("categories.id")),
        sa.Column("payment_method_id", UUID, sa.ForeignKey("payment_methods.id")),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column("statement_month", sa.Date()),
        sa.Column("installment_no", sa.Integer(), server_default=sa.text("1")),
        sa.Column("installment_total", sa.Integer(), server_default=sa.text("1")),
        sa.Column("purchase_group", UUID),
        sa.Column("source", sa.Text()),
        sa.Column("message_id", UUID, sa.ForeignKey("messages.id")),
        # clock_timestamp: ordem real mesmo dentro da mesma transação (desfazer_ultimo).
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("amount_cents > 0", name="expenses_amount_check"),
        sa.CheckConstraint("source in ('texto','audio','foto')", name="expenses_source_check"),
    )
    op.create_index("expenses_spent_on_idx", "expenses", ["spent_on"])
    op.create_index("expenses_statement_idx", "expenses", ["payment_method_id", "statement_month"])
    op.create_table(
        "pending_actions",
        _id(),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("args", postgresql.JSONB(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "status in ('pending','confirmed','cancelled','expired')",
            name="pending_actions_status_check",
        ),
    )
    op.create_table(
        "agent_runs",
        _id(),
        sa.Column("message_id", UUID, sa.ForeignKey("messages.id")),
        sa.Column("channel", sa.Text()),
        sa.Column("intent", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("escalated", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("tools_called", postgresql.JSONB()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error", sa.Text()),
        _created_at(),
    )


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_table("pending_actions")
    op.drop_table("expenses")
    op.drop_table("categories")
    op.drop_table("payment_methods")
