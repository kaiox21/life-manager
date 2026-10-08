"""Ferramentas do grupo "gasto": lancar_gasto, desfazer_ultimo, gerenciar_meio_pagamento."""

import uuid
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import Field, model_validator
from sqlalchemy import select, update

from app.agent.tools.base import Tool, ToolArgs, ToolContext, ToolError, br_date, brl
from app.agent.tools.resolve import normalize, resolve_category, resolve_payment_method
from app.clock import today
from app.db.models import Category, Expense, PaymentMethod, PendingAction
from app.domain.billing import due_date, split_installments

CONFIRM_ABOVE_CENTS = 50_000  # R$ 500,00
PENDING_TTL = timedelta(minutes=30)
DEFAULT_CATEGORY = "Outros"


class LancarGastoArgs(ToolArgs):
    amount_cents: int = Field(gt=0, description="Valor TOTAL em centavos. R$ 47,90 -> 4790")
    description: str = Field(min_length=1, description="O que foi comprado. Ex.: 'almoço'")
    payment_method: str = Field(
        min_length=1, description="Meio de pagamento como o usuário disse. Ex.: 'Nubank'"
    )
    category: str | None = Field(default=None, description="Uma das categorias cadastradas")
    spent_on: date | None = Field(default=None, description="AAAA-MM-DD; omita se foi hoje")
    installments: int = Field(default=1, ge=1, le=48, description="Nº de parcelas (crédito)")
    merchant: str | None = Field(default=None, description="Estabelecimento, se dito")


async def lancar_gasto(ctx: ToolContext, args: LancarGastoArgs) -> dict[str, Any]:
    pm = await resolve_payment_method(ctx.session, args.payment_method)
    category = await resolve_category(ctx.session, args.category or DEFAULT_CATEGORY)
    spent_on = args.spent_on or today(ctx.clock)
    if spent_on > today(ctx.clock):
        raise ToolError("Data no futuro; confirme a data do gasto com o usuário.")
    if args.installments > 1 and pm.kind != "credito":
        raise ToolError(f"Parcelamento só no crédito; {pm.name} é {pm.kind}.")

    normalized = args.model_copy(
        update={"payment_method": pm.name, "category": category.name, "spent_on": spent_on}
    )
    summary = _summary(normalized)
    if args.amount_cents > CONFIRM_ABOVE_CENTS or ctx.source != "texto":
        pending = PendingAction(
            tool_name="lancar_gasto",
            args=normalized.model_dump(mode="json"),
            summary=summary,
            expires_at=ctx.clock() + PENDING_TTL,
        )
        ctx.session.add(pending)
        await ctx.session.flush()
        return {
            "status": "aguardando_confirmacao",
            "pending_id": str(pending.id),
            "resumo": f"{summary}. Confirma?",
        }
    return await record_expense(ctx, normalized, pm, category)


async def record_expense(
    ctx: ToolContext,
    args: LancarGastoArgs,
    pm: PaymentMethod | None = None,
    category: Category | None = None,
) -> dict[str, Any]:
    pm = pm or await resolve_payment_method(ctx.session, args.payment_method)
    category = category or await resolve_category(ctx.session, args.category or DEFAULT_CATEGORY)
    spent_on = args.spent_on or today(ctx.clock)
    credit = pm.kind == "credito" and pm.closing_day is not None and pm.due_day is not None
    parts = split_installments(
        args.amount_cents,
        args.installments,
        spent_on,
        pm.closing_day if credit else None,
        pm.due_day if credit else None,
    )
    group = uuid.uuid4()
    for part in parts:
        ctx.session.add(
            Expense(
                amount_cents=part.amount_cents,
                description=args.description,
                merchant=args.merchant,
                category_id=category.id,
                payment_method_id=pm.id,
                spent_on=spent_on,
                statement_month=part.statement_month,
                installment_no=part.number,
                installment_total=part.total,
                purchase_group=group,
                source=ctx.source,
                message_id=ctx.message_id,
            )
        )
    await ctx.session.flush()

    result: dict[str, Any] = {
        "status": "gravado",
        "resumo": _summary(args.model_copy(update={"spent_on": spent_on})),
        "valor": brl(args.amount_cents),
        "meio": pm.name,
        "categoria": category.name,
        "data": br_date(spent_on),
    }
    if args.installments > 1:
        result["parcelas"] = [
            {"n": p.number, "valor": brl(p.amount_cents), **_due(p.statement_month, pm)}
            for p in parts
        ]
    elif parts[0].statement_month:
        result.update(_due(parts[0].statement_month, pm))
    return result


def _due(statement_month: date | None, pm: PaymentMethod) -> dict[str, str]:
    if statement_month is None or pm.due_day is None:
        return {}
    return {"fatura_vence": br_date(due_date(statement_month, pm.due_day))}


def _summary(args: LancarGastoArgs) -> str:
    parts = [brl(args.amount_cents)]
    if args.installments > 1:
        parts.append(f"em {args.installments}x")
    parts.append(f"no {args.payment_method}")
    text = " ".join(parts) + f" — {args.description}"
    if args.merchant:
        text += f" ({args.merchant})"
    if args.category:
        text += f", {args.category}"
    if args.spent_on:
        text += f", {br_date(args.spent_on)}"
    return text


class SemArgs(ToolArgs):
    pass


async def desfazer_ultimo(ctx: ToolContext, args: SemArgs) -> dict[str, Any]:
    last = await ctx.session.scalar(
        select(Expense)
        .where(Expense.deleted_at.is_(None))
        .order_by(Expense.created_at.desc(), Expense.installment_no)
        .limit(1)
    )
    if last is None:
        return {"status": "nada_para_desfazer"}
    group_filter = (
        Expense.purchase_group == last.purchase_group
        if last.purchase_group
        else Expense.id == last.id
    )
    rows = (
        await ctx.session.execute(
            update(Expense)
            .where(group_filter, Expense.deleted_at.is_(None))
            .values(deleted_at=ctx.clock())
            .returning(Expense.amount_cents)
        )
    ).all()
    total = sum(r.amount_cents for r in rows)
    return {
        "status": "desfeito",
        "resumo": f"{brl(total)} — {last.description}, {br_date(last.spent_on)}",
    }


class GerenciarMeioPagamentoArgs(ToolArgs):
    name: str = Field(min_length=1, description="Nome do meio. Ex.: 'Inter'")
    kind: Literal["credito", "debito", "pix", "dinheiro"]
    closing_day: int | None = Field(
        default=None, ge=1, le=31, description="Dia de fechamento (crédito); 31 = último dia"
    )
    due_day: int | None = Field(default=None, ge=1, le=31, description="Dia de vencimento")

    @model_validator(mode="after")
    def _credit_needs_days(self) -> "GerenciarMeioPagamentoArgs":
        if self.kind == "credito" and (self.closing_day is None or self.due_day is None):
            raise ValueError("crédito precisa de closing_day e due_day")
        if self.kind != "credito" and (self.closing_day or self.due_day):
            raise ValueError("closing_day e due_day são só para crédito")
        return self


async def gerenciar_meio_pagamento(
    ctx: ToolContext, args: GerenciarMeioPagamentoArgs
) -> dict[str, Any]:
    methods = (await ctx.session.scalars(select(PaymentMethod))).all()
    existing = next((pm for pm in methods if normalize(pm.name) == normalize(args.name)), None)
    if existing:
        existing.kind = args.kind
        existing.closing_day = args.closing_day
        existing.due_day = args.due_day
        existing.active = True
        status = "atualizado"
    else:
        ctx.session.add(
            PaymentMethod(
                name=args.name,
                kind=args.kind,
                closing_day=args.closing_day,
                due_day=args.due_day,
            )
        )
        status = "criado"
    await ctx.session.flush()
    detail = f"{args.name} ({args.kind}"
    if args.kind == "credito":
        detail += f", fecha dia {args.closing_day}, vence dia {args.due_day}"
    return {"status": status, "resumo": detail + ")"}


TOOLS = [
    Tool(
        "lancar_gasto",
        ("gasto",),
        "Lança um gasto. Ex.: 'gastei 47,90 no almoço no nubank' -> amount_cents=4790, "
        "description='almoço', payment_method='Nubank', category='Alimentação'. "
        "Compra parcelada: amount_cents é o TOTAL e installments o nº de parcelas.",
        LancarGastoArgs,
        lancar_gasto,
    ),
    Tool(
        "desfazer_ultimo",
        ("gasto",),
        "Desfaz (apaga) o último gasto lançado, com todas as parcelas.",
        SemArgs,
        desfazer_ultimo,
    ),
    Tool(
        "gerenciar_meio_pagamento",
        ("gasto",),
        "Cadastra ou atualiza cartão/meio de pagamento. Ex.: 'cartão inter, crédito, fecha "
        "dia 15 e vence dia 22' -> name='Inter', kind='credito', closing_day=15, due_day=22.",
        GerenciarMeioPagamentoArgs,
        gerenciar_meio_pagamento,
    ),
]
