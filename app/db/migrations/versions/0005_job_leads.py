"""job_leads: vagas do radar (estágio, bolsa, monitoria, júnior) e 'vagas' em sent_reminders

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE job_leads_codigo_seq")
    op.create_table(
        "job_leads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # código curto e estável (V1, V2…) usado na mensagem, na lista, no painel e para dispensar
        sa.Column(
            "codigo",
            sa.Text(),
            nullable=False,
            unique=True,
            server_default=sa.text("'V' || nextval('job_leads_codigo_seq')"),
        ),
        sa.Column("url", sa.Text(), nullable=False, unique=True),  # normalizada
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("organizacao", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("local", sa.Text(), nullable=False),
        sa.Column("prazo", sa.Date()),
        sa.Column("resumo", sa.Text(), nullable=False, server_default=""),
        sa.Column("pontuacao", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id")),
        sa.Column("found_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "tipo in ('estagio','bolsa','monitoria','junior')", name="job_leads_tipo_check"
        ),
    )
    op.drop_constraint("sent_reminders_kind_check", "sent_reminders", type_="check")
    op.create_check_constraint(
        "sent_reminders_kind_check",
        "sent_reminders",
        "kind in ('evento','resumo','fatura','vagas')",
    )


def downgrade() -> None:
    op.drop_constraint("sent_reminders_kind_check", "sent_reminders", type_="check")
    op.create_check_constraint(
        "sent_reminders_kind_check", "sent_reminders", "kind in ('evento','resumo','fatura')"
    )
    op.drop_table("job_leads")
    op.execute("DROP SEQUENCE job_leads_codigo_seq")
