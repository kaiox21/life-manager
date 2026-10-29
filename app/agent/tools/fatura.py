"""Executor de `gravar_fatura`: grava, depois do "sim", o que a importação da fatura planejou
(app/statements/service.py). Fica entre as ferramentas porque é chamado por confirmar_pendente."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select

from app.agent.tools.base import ToolContext
from app.db.models import Category, Expense, PaymentMethod, StatementImport
from app.domain.statement import brl

DEFAULT_CATEGORY = "Outros"


async def record_statement(ctx: ToolContext, raw: dict[str, Any]) -> dict[str, Any]:
    """Executor de `gravar_fatura` (depois do "sim"): uma transação, eco do que foi gravado."""
    pm = await ctx.session.get(PaymentMethod, uuid.UUID(raw["payment_method_id"]))
    if pm is None:
        return {"status": "sem_pendencia", "resumo": "O cartão dessa fatura não existe mais."}
    matched = [uuid.UUID(i) for i in raw["matched_ids"]]
    undone = 0
    if matched:
        active = set(
            (
                await ctx.session.scalars(
                    select(Expense.id).where(Expense.id.in_(matched), Expense.deleted_at.is_(None))
                )
            ).all()
        )
        undone = len(set(matched) - active)
    categories = {c.name: c for c in (await ctx.session.scalars(select(Category))).all()}
    fallback = categories.get(DEFAULT_CATEGORY)
    groups: dict[int, uuid.UUID] = {}
    for r in raw["rows"]:
        group = groups.setdefault(r["group"], uuid.uuid4())
        category = categories.get(r["category"] or "") or fallback
        ctx.session.add(
            Expense(
                amount_cents=r["amount_cents"],
                description=r["description"],
                merchant=r["description"],
                category_id=category.id if category else None,
                payment_method_id=pm.id,
                spent_on=date.fromisoformat(r["spent_on"]),
                statement_month=date.fromisoformat(r["statement_month"]),
                installment_no=r["installment_no"],
                installment_total=r["installment_total"],
                purchase_group=group,
                source="fatura",
                message_id=ctx.message_id,
            )
        )
    ctx.session.add(
        StatementImport(
            payment_method_id=pm.id,
            statement_month=date.fromisoformat(raw["statement_month"]),
            printed_total_cents=raw["printed_total_cents"],
            file_sha256=raw["file_sha256"],
            items_count=raw["items_count"],
            created_cents=raw["new_total_cents"],
        )
    )
    await ctx.session.flush()
    due = date.fromisoformat(raw["due"])
    future = len(raw["rows"]) - raw["new_count"]
    text = (
        f"Lancei {raw['new_count']} gasto{'s' if raw['new_count'] > 1 else ''} da fatura do "
        f"{pm.name} (venc. {due:%d/%m}), {brl(raw['new_total_cents'])}"
    )
    if future:
        text += (
            f", mais {future} parcela{'s' if future > 1 else ''} futura{'s' if future > 1 else ''}"
        )
    text += "."
    if undone:
        text += (
            f" Atenção: {undone} gasto(s) que casava(m) com a fatura foi(ram) desfeito(s) "
            "depois do resumo; confira."
        )
    return {"status": "fatura_gravada", "resumo": text}
