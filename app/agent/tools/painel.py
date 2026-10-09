"""Dados do painel do Jarvis (`painel`, só no MCP, chamada sem o modelo).

Reusa as próprias ferramentas de consulta, então os números batem com os da conversa por
construção. Nada é calculado aqui além de escolher períodos: somas são SQL e a fatura
aberta vem de `app/domain/billing.py`.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import select

from app.agent.tools.agenda import WEEKDAYS, BuscarEventosArgs, buscar_eventos
from app.agent.tools.base import ToolContext, ToolError, br_date, brl
from app.agent.tools.consultas import ResumoGastosArgs, TotalFaturaArgs, resumo_gastos, total_fatura
from app.clock import TZ, today
from app.db.models import Event, Expense, Message, PaymentMethod
from app.domain.billing import open_statement_month

REGISTRO = 10
DIAS_A_FRENTE = 7


async def painel(ctx: ToolContext) -> dict[str, Any]:
    hoje = today(ctx.clock)
    return {
        "agora": ctx.clock().astimezone(TZ).isoformat(),
        "agenda": {
            "hoje": (await buscar_eventos(ctx, BuscarEventosArgs(de=hoje, ate=hoje)))["eventos"],
            "proximos": (
                await buscar_eventos(
                    ctx,
                    BuscarEventosArgs(
                        de=hoje + timedelta(days=1), ate=hoje + timedelta(days=DIAS_A_FRENTE)
                    ),
                )
            )["eventos"],
        },
        "mes": await resumo_gastos(
            ctx, ResumoGastosArgs(de=hoje.replace(day=1), ate=hoje, agrupar_por="categoria")
        ),
        "faturas": await _faturas(ctx),
        "registro": await _registro(ctx),
    }


async def _faturas(ctx: ToolContext) -> list[dict[str, Any]]:
    hoje = today(ctx.clock)
    cards = (
        await ctx.session.scalars(
            select(PaymentMethod)
            .where(PaymentMethod.kind == "credito", PaymentMethod.active.is_(True))
            .order_by(PaymentMethod.name)
        )
    ).all()
    out = []
    for pm in cards:
        if pm.closing_day is None or pm.due_day is None:
            continue
        month = open_statement_month(hoje, pm.closing_day, pm.due_day)
        try:
            fatura = await total_fatura(
                ctx, TotalFaturaArgs(payment_method=pm.name, mes_vencimento=f"{month:%Y-%m}")
            )
        except ToolError:
            continue
        fatura.pop("maiores_itens", None)
        out.append({**fatura, "mes_vencimento": f"{month:%Y-%m}"})
    return out


async def _registro(ctx: ToolContext) -> list[dict[str, Any]]:
    """Últimos gastos lançados e eventos criados, do mais novo para o mais antigo."""
    gastos = (
        await ctx.session.execute(
            select(Expense, PaymentMethod.name, Message.channel)
            .outerjoin(PaymentMethod, PaymentMethod.id == Expense.payment_method_id)
            .outerjoin(Message, Message.id == Expense.message_id)
            .where(Expense.deleted_at.is_(None), Expense.installment_no == 1)
            .order_by(Expense.created_at.desc())
            .limit(REGISTRO)
        )
    ).all()
    eventos = (
        await ctx.session.scalars(
            select(Event)
            .where(Event.deleted_at.is_(None))
            .order_by(Event.created_at.desc())
            .limit(REGISTRO)
        )
    ).all()

    itens: list[dict[str, Any]] = []
    for exp, meio, channel in gastos:
        partes = [exp.merchant or exp.description]
        if exp.installment_total > 1:
            partes.append(f"{exp.installment_total}× de {brl(exp.amount_cents)}")
        else:
            partes.append(brl(exp.amount_cents))
        if meio:
            partes.append(meio)
        itens.append(
            {
                "tipo": "gasto",
                "quando": exp.created_at.astimezone(TZ).isoformat(),
                "texto": " · ".join(partes),
                "origem": "whatsapp" if channel == "whatsapp" else "mac",
            }
        )
    for ev in eventos:
        at = ev.starts_at.astimezone(TZ)
        hora = "" if ev.all_day else f" {at:%H:%M}"
        itens.append(
            {
                "tipo": "evento",
                "quando": ev.created_at.astimezone(TZ).isoformat(),
                "texto": f"{ev.title} · {WEEKDAYS[at.weekday()]} {br_date(at.date())}{hora}",
                "origem": None,
            }
        )
    itens.sort(key=lambda i: i["quando"], reverse=True)
    return itens[:REGISTRO]
