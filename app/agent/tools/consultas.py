"""Ferramentas do grupo "consulta_gasto". Toda conta é feita em SQL."""

import re
from datetime import date
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from sqlalchemy import Select, func, or_, select

from app.agent.tools.base import Tool, ToolArgs, ToolContext, br_date, brl
from app.agent.tools.resolve import resolve_category, resolve_payment_method
from app.clock import today
from app.db.models import Category, Expense, PaymentMethod
from app.domain.billing import closing_date, due_date

TOP_ITEMS = 3


def _alive() -> Any:
    return Expense.deleted_at.is_(None)


def _check_range(de: date | None, ate: date | None) -> None:
    if de and ate and de > ate:
        raise ValueError("'de' precisa ser antes ou igual a 'ate'")


class BuscarGastosArgs(ToolArgs):
    de: date | None = Field(default=None, description="AAAA-MM-DD, inclusive")
    ate: date | None = Field(default=None, description="AAAA-MM-DD, inclusive")
    category: str | None = None
    payment_method: str | None = None
    query: str | None = Field(default=None, description="Texto na descrição/estabelecimento")
    limite: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def _range(self) -> "BuscarGastosArgs":
        _check_range(self.de, self.ate)
        return self


async def buscar_gastos(ctx: ToolContext, args: BuscarGastosArgs) -> dict[str, Any]:
    filters = [_alive()]
    if args.de:
        filters.append(Expense.spent_on >= args.de)
    if args.ate:
        filters.append(Expense.spent_on <= args.ate)
    if args.category:
        cat = await resolve_category(ctx.session, args.category)
        filters.append(Expense.category_id == cat.id)
    if args.payment_method:
        pm = await resolve_payment_method(ctx.session, args.payment_method)
        filters.append(Expense.payment_method_id == pm.id)
    if args.query:
        pattern = f"%{args.query}%"
        filters.append(
            or_(
                func.unaccent(Expense.description).ilike(func.unaccent(pattern)),
                func.unaccent(func.coalesce(Expense.merchant, "")).ilike(func.unaccent(pattern)),
            )
        )

    total, count = (
        await ctx.session.execute(
            select(func.coalesce(func.sum(Expense.amount_cents), 0), func.count()).where(*filters)
        )
    ).one()
    rows = (
        await ctx.session.execute(
            _listing().where(*filters).order_by(Expense.spent_on.desc()).limit(args.limite)
        )
    ).all()
    return {
        "total": brl(int(total)),
        "total_centavos": int(total),
        "lancamentos": count,
        "itens": [_item(r) for r in rows],
        "itens_omitidos": max(count - len(rows), 0),
    }


class TotalFaturaArgs(ToolArgs):
    payment_method: str = Field(description="Cartão de crédito. Ex.: 'Nubank'")
    mes_vencimento: str = Field(description="Mês em que a fatura VENCE, AAAA-MM. Ex.: '2026-11'")

    @field_validator("mes_vencimento")
    @classmethod
    def _month(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", v):
            raise ValueError("use AAAA-MM")
        return v


async def total_fatura(ctx: ToolContext, args: TotalFaturaArgs) -> dict[str, Any]:
    pm = await resolve_payment_method(ctx.session, args.payment_method, kinds={"credito"})
    year, month = map(int, args.mes_vencimento.split("-"))
    statement = date(year, month, 1)
    filters = [_alive(), Expense.payment_method_id == pm.id, Expense.statement_month == statement]

    total, count = (
        await ctx.session.execute(
            select(func.coalesce(func.sum(Expense.amount_cents), 0), func.count()).where(*filters)
        )
    ).one()
    top = (
        await ctx.session.execute(
            _listing().where(*filters).order_by(Expense.amount_cents.desc()).limit(TOP_ITEMS)
        )
    ).all()

    assert pm.closing_day is not None and pm.due_day is not None
    vence = due_date(statement, pm.due_day)
    closes_in = statement if pm.due_day > pm.closing_day else _prev_month(statement)
    fecha = closing_date(closes_in, pm.closing_day)
    return {
        "cartao": pm.name,
        "vencimento": br_date(vence),
        "fechamento": br_date(fecha),
        "situacao": "aberta" if today(ctx.clock) < fecha else "fechada",
        "total": brl(int(total)),
        "total_centavos": int(total),
        "lancamentos": count,
        "maiores_itens": [_item(r) for r in top],
    }


class ResumoGastosArgs(ToolArgs):
    de: date = Field(description="AAAA-MM-DD, inclusive")
    ate: date = Field(description="AAAA-MM-DD, inclusive")
    agrupar_por: Literal["categoria", "meio", "dia"]

    @model_validator(mode="after")
    def _range(self) -> "ResumoGastosArgs":
        _check_range(self.de, self.ate)
        return self


async def resumo_gastos(ctx: ToolContext, args: ResumoGastosArgs) -> dict[str, Any]:
    key = {
        "categoria": func.coalesce(Category.name, "Sem categoria"),
        "meio": func.coalesce(PaymentMethod.name, "Sem meio"),
        "dia": func.to_char(Expense.spent_on, "DD/MM/YYYY"),
    }[args.agrupar_por]
    filters = [_alive(), Expense.spent_on >= args.de, Expense.spent_on <= args.ate]
    total_col = func.sum(Expense.amount_cents)
    stmt = (
        select(key.label("grupo"), total_col.label("total"), func.count().label("n"))
        .select_from(Expense)
        .outerjoin(Category, Category.id == Expense.category_id)
        .outerjoin(PaymentMethod, PaymentMethod.id == Expense.payment_method_id)
        .where(*filters)
        .group_by(key)
    )
    if args.agrupar_por == "dia":
        stmt = stmt.group_by(Expense.spent_on).order_by(Expense.spent_on)
    else:
        stmt = stmt.order_by(total_col.desc())
    rows = (await ctx.session.execute(stmt)).all()
    grand_total = (
        await ctx.session.scalar(
            select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(*filters)
        )
    ) or 0
    return {
        "periodo": f"{br_date(args.de)} a {br_date(args.ate)}",
        "total": brl(int(grand_total)),
        "total_centavos": int(grand_total),
        "grupos": [
            {"grupo": r.grupo, "total": brl(int(r.total)), "lancamentos": r.n} for r in rows
        ],
    }


def _listing() -> Select[Any]:
    return (
        select(
            Expense.spent_on,
            Expense.description,
            Expense.merchant,
            Expense.amount_cents,
            Expense.installment_no,
            Expense.installment_total,
            Category.name.label("categoria"),
            PaymentMethod.name.label("meio"),
        )
        .select_from(Expense)
        .outerjoin(Category, Category.id == Expense.category_id)
        .outerjoin(PaymentMethod, PaymentMethod.id == Expense.payment_method_id)
    )


def _item(row: Any) -> dict[str, Any]:
    item = {
        "data": br_date(row.spent_on),
        "descricao": row.description,
        "valor": brl(row.amount_cents),
        "categoria": row.categoria,
        "meio": row.meio,
    }
    if row.merchant:
        item["estabelecimento"] = row.merchant
    if row.installment_total > 1:
        item["parcela"] = f"{row.installment_no}/{row.installment_total}"
    return item


def _prev_month(d: date) -> date:
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


TOOLS = [
    Tool(
        "buscar_gastos",
        "consulta_gasto",
        "Lista gastos com filtros e devolve a soma (calculada no banco). Ex.: 'quanto gastei "
        "com mercado esse mês' -> de='2026-10-01', ate=hoje, category='Mercado'.",
        BuscarGastosArgs,
        buscar_gastos,
    ),
    Tool(
        "total_fatura",
        "consulta_gasto",
        "Total de uma fatura de cartão de crédito pelo mês de VENCIMENTO (AAAA-MM). "
        "Use a tabela de faturas abertas do prompt para 'fatura atual'.",
        TotalFaturaArgs,
        total_fatura,
    ),
    Tool(
        "resumo_gastos",
        "consulta_gasto",
        "Totais agrupados por categoria, meio ou dia num período. Ex.: 'quanto gastei em "
        "setembro por categoria' -> de='2026-09-01', ate='2026-09-30', agrupar_por='categoria'.",
        ResumoGastosArgs,
        resumo_gastos,
    ),
]
