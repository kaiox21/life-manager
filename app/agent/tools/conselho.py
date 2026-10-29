"""Ferramentas do grupo "conselho": gerenciar_renda, gerenciar_conta_fixa e avaliar_compra.

As contas são do código (app/domain/budget.py); o modelo só explica os números devolvidos.
"""

from typing import Any, Literal

from pydantic import Field, ValidationError, model_validator
from sqlalchemy import select

from app.agent.tools.base import Tool, ToolArgs, ToolContext, ToolError, brl
from app.agent.tools.resolve import normalize, resolve_payment_method
from app.clock import today
from app.config import get_settings
from app.db.models import BudgetItem, Expense
from app.domain.budget import PastExpense, advise, leftover_pct, purchase_months

Kind = Literal["renda", "fixa"]
VERDICT_TEXT = {"segura": "segura", "atencao": "atenção", "arriscada": "arriscada"}


def _folga_pct() -> int:
    try:
        return get_settings().conselho_folga_pct
    except ValidationError:  # sem .env completo (CI): o padrão da spec
        return 20


async def _active(ctx: ToolContext, kind: Kind) -> list[BudgetItem]:
    return list(
        (
            await ctx.session.scalars(
                select(BudgetItem)
                .where(BudgetItem.kind == kind, BudgetItem.deleted_at.is_(None))
                .order_by(BudgetItem.name)
            )
        ).all()
    )


async def _totals(ctx: ToolContext) -> dict[str, str]:
    renda = sum(i.amount_cents for i in await _active(ctx, "renda"))
    fixas = sum(i.amount_cents for i in await _active(ctx, "fixa"))
    return {"renda_mensal": brl(renda), "contas_fixas_mensal": brl(fixas)}


def _day_text(day: int) -> str:
    return "no último dia do mês" if day == 31 else f"todo dia {day}"


class _BudgetArgs(ToolArgs):
    amount_cents: int | None = Field(default=None, gt=0, description="Valor mensal em centavos")
    day: int | None = Field(default=None, ge=1, le=31, description="Dia do mês; 31 = último dia")
    remover: bool = Field(default=False, description="true para tirar da lista")

    @model_validator(mode="after")
    def _needs_value(self) -> "_BudgetArgs":
        if not self.remover and (self.amount_cents is None or self.day is None):
            raise ValueError("amount_cents e day são obrigatórios (exceto para remover)")
        return self


class GerenciarRendaArgs(_BudgetArgs):
    name: str = Field(default="Salário", min_length=1, description="Ex.: 'Salário', 'Estágio'")


class GerenciarContaFixaArgs(_BudgetArgs):
    name: str = Field(min_length=1, description="Ex.: 'Aluguel', 'Academia'")
    payment_method: str | None = Field(default=None, description="Meio em que é paga, se dito")


async def _manage(
    ctx: ToolContext, kind: Kind, args: _BudgetArgs, name: str, pm_text: str | None = None
) -> dict[str, Any]:
    label = "Renda" if kind == "renda" else "Conta fixa"
    items = await _active(ctx, kind)
    existing = next((i for i in items if normalize(i.name) == normalize(name)), None)
    if args.remover:
        if existing is None:
            raise ToolError(
                f"{label} '{name}' não está cadastrada.", opcoes=[i.name for i in items]
            )
        existing.deleted_at = ctx.clock()
        await ctx.session.flush()
        return {
            "status": "removido",
            "resumo": f"{label} {existing.name} removida",
            **await _totals(ctx),
        }

    assert args.amount_cents is not None and args.day is not None
    pm = await resolve_payment_method(ctx.session, pm_text) if pm_text else None
    if existing:
        existing.amount_cents = args.amount_cents
        existing.day = args.day
        existing.payment_method_id = pm.id if pm else existing.payment_method_id
        status, item = "atualizado", existing
    else:
        item = BudgetItem(
            kind=kind,
            name=name.strip(),
            amount_cents=args.amount_cents,
            day=args.day,
            payment_method_id=pm.id if pm else None,
        )
        ctx.session.add(item)
        status = "criado"
    await ctx.session.flush()
    text = f"{label}: {item.name}, {brl(item.amount_cents)} {_day_text(item.day)}"
    if pm:
        text += f", no {pm.name}"
    return {"status": status, "resumo": text, **await _totals(ctx)}


async def gerenciar_renda(ctx: ToolContext, args: GerenciarRendaArgs) -> dict[str, Any]:
    return await _manage(ctx, "renda", args, args.name)


async def gerenciar_conta_fixa(ctx: ToolContext, args: GerenciarContaFixaArgs) -> dict[str, Any]:
    return await _manage(ctx, "fixa", args, args.name, args.payment_method)


class AvaliarCompraArgs(ToolArgs):
    amount_cents: int = Field(gt=0, description="Valor TOTAL da compra em centavos")
    description: str | None = Field(default=None, description="O que quer comprar")
    payment_method: str | None = Field(default=None, description="Meio, se dito")
    installments: int = Field(default=1, ge=1, le=48, description="Nº de parcelas (crédito)")


def _month(d: Any) -> str:
    return f"{d:%m/%Y}"


async def avaliar_compra(ctx: ToolContext, args: AvaliarCompraArgs) -> dict[str, Any]:
    rendas = await _active(ctx, "renda")
    if not rendas:
        raise ToolError(
            "Sem renda cadastrada: pergunte a renda mensal e o dia em que cai antes de opinar.",
            falta="renda",
        )
    pm = None
    if args.payment_method:
        pm = await resolve_payment_method(ctx.session, args.payment_method)
        if args.installments > 1 and pm.kind != "credito":
            raise ToolError(f"Parcelamento só no crédito; {pm.name} é {pm.kind}.")
    hoje = today(ctx.clock)
    credit = pm is not None and pm.kind == "credito"
    purchase = purchase_months(
        args.amount_cents,
        args.installments,
        hoje,
        pm.closing_day if credit and pm else None,
        pm.due_day if credit and pm else None,
    )
    fixas = await _active(ctx, "fixa")
    rows = (await ctx.session.scalars(select(Expense).where(Expense.deleted_at.is_(None)))).all()
    expenses = [
        PastExpense(
            e.spent_on, e.amount_cents, e.description, e.installment_total, e.statement_month
        )
        for e in rows
    ]
    pct = _folga_pct()
    advice = advise(
        purchase=purchase,
        income=sum(i.amount_cents for i in rendas),
        fixed=sum(i.amount_cents for i in fixas),
        fixed_names=[i.name for i in fixas],
        expenses=expenses,
        today=hoje,
        folga_pct=pct,
    )
    meses = [
        {
            "mes": _month(m.month),
            "renda": brl(m.income),
            "contas_fixas": brl(m.fixed),
            "parcelas_comprometidas": brl(m.committed),
            "media_avulsa": brl(m.average),
            "parcela_nova": brl(m.new_installment),
            "sobra": brl(m.leftover),
            "sobra_pct": leftover_pct(m),
        }
        for m in advice.months
    ]
    d = advice.decisive
    lines = [
        f"{x['mes']}: renda {x['renda']} − fixas {x['contas_fixas']} − parcelas "
        f"{x['parcelas_comprometidas']} − média {x['media_avulsa']} − nova {x['parcela_nova']} "
        f"= sobra {x['sobra']} ({x['sobra_pct']}%)"
        for x in meses
    ]
    result: dict[str, Any] = {
        "veredito": VERDICT_TEXT[advice.verdict],
        "mes_decisivo": _month(d.month),
        "sobra_no_mes_decisivo": brl(d.leftover),
        "sobra_pct_no_mes_decisivo": leftover_pct(d),
        "folga_minima_pct": pct,
        "compra": brl(args.amount_cents)
        + (f" em {args.installments}x" if args.installments > 1 else "")
        + (f" no {pm.name}" if pm else ""),
        "meses": meses,
        "contas_fixas": [f"{i.name} {brl(i.amount_cents)}" for i in fixas],
        "meses_de_historico": advice.history_months,
        "texto": "\n".join(lines),
        "regra": f"segura: sobra >= {pct}% da renda em todos os meses; atenção: entre 0 e "
        f"{pct}%; arriscada: algum mês negativo",
    }
    if advice.history_months < 3:
        result["aviso"] = (
            f"Média calculada com {advice.history_months} mês(es) de histórico."
            if advice.history_months
            else "Sem histórico de gastos: a média avulsa ficou zero."
        )
    if args.description:
        result["descricao"] = args.description
    return result


TOOLS = [
    Tool(
        "avaliar_compra",
        ("conselho",),
        "Diz se uma compra cabe no orçamento (veredito, mês decisivo e sobra calculados no "
        "sistema). Ex.: 'posso comprar um fone de 400 em 4x no nubank?' -> amount_cents=40000, "
        "description='fone', payment_method='Nubank', installments=4.",
        AvaliarCompraArgs,
        avaliar_compra,
    ),
    Tool(
        "gerenciar_renda",
        ("conselho",),
        "Cadastra, muda ou tira (remover=true) uma renda mensal. Ex.: 'minha renda é 3.500 "
        "todo dia 5' -> name='Salário', amount_cents=350000, day=5.",
        GerenciarRendaArgs,
        gerenciar_renda,
    ),
    Tool(
        "gerenciar_conta_fixa",
        ("conselho",),
        "Cadastra, muda ou tira (remover=true) uma conta fixa mensal. Ex.: 'aluguel 900 dia 10' "
        "-> name='Aluguel', amount_cents=90000, day=10; 'tira a academia' -> name='Academia', "
        "remover=true.",
        GerenciarContaFixaArgs,
        gerenciar_conta_fixa,
    ),
]
