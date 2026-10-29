"""conselheiro financeiro: statement_imports, budget_items e gastos vindos da fatura

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Estorno da fatura é gasto negativo; fora da fatura o valor continua positivo.
    op.drop_constraint("expenses_amount_check", "expenses", type_="check")
    op.create_check_constraint(
        "expenses_amount_check",
        "expenses",
        "amount_cents <> 0 AND (amount_cents > 0 OR source = 'fatura')",
    )
    op.drop_constraint("expenses_source_check", "expenses", type_="check")
    op.create_check_constraint(
        "expenses_source_check", "expenses", "source in ('texto','audio','foto','fatura')"
    )

    op.create_table(
        "statement_imports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "payment_method_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payment_methods.id"),
            nullable=False,
        ),
        sa.Column("statement_month", sa.Date(), nullable=False),
        sa.Column("printed_total_cents", sa.BigInteger(), nullable=False),
        sa.Column("file_sha256", sa.Text(), nullable=False),
        sa.Column("items_count", sa.Integer(), nullable=False),
        sa.Column("created_cents", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("statement_imports_sha", "statement_imports", ["file_sha256"])
    op.create_index(
        "statement_imports_cycle", "statement_imports", ["payment_method_id", "statement_month"]
    )

    op.create_table(
        "budget_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column(
            "payment_method_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_methods.id")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind in ('renda','fixa')", name="budget_items_kind_check"),
        sa.CheckConstraint("amount_cents > 0", name="budget_items_amount_check"),
        sa.CheckConstraint("day between 1 and 31", name="budget_items_day_check"),
    )
    # Nome único entre os ativos fica no código (unaccent não é IMMUTABLE, não entra em índice).


def downgrade() -> None:
    op.drop_table("budget_items")
    op.drop_index("statement_imports_cycle", "statement_imports")
    op.drop_index("statement_imports_sha", "statement_imports")
    op.drop_table("statement_imports")
    # Só para desenvolvimento: os checks antigos não aceitam gastos vindos da fatura.
    op.execute("delete from expenses where source = 'fatura'")
    op.drop_constraint("expenses_source_check", "expenses", type_="check")
    op.create_check_constraint(
        "expenses_source_check", "expenses", "source in ('texto','audio','foto')"
    )
    op.drop_constraint("expenses_amount_check", "expenses", type_="check")
    op.create_check_constraint("expenses_amount_check", "expenses", "amount_cents > 0")
