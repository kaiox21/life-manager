"""Conselho de compra: projeção e veredito (app/domain/budget.py) e as ferramentas no banco."""

from datetime import date

import pytest

from app.agent.tools.base import ToolContext, ToolError
from app.agent.tools.conselho import (
    AvaliarCompraArgs,
    GerenciarContaFixaArgs,
    GerenciarRendaArgs,
    avaliar_compra,
    gerenciar_conta_fixa,
    gerenciar_renda,
)
from app.agent.tools.gastos import LancarGastoArgs, record_expense
from app.domain.budget import PastExpense, advise, average_variable, purchase_months

TODAY = date(2026, 10, 7)


def _past(day: date, cents: int, desc: str = "mercado", total: int = 1, month=None) -> PastExpense:  # noqa: ANN001
    return PastExpense(day, cents, desc, total, month)


def test_meses_da_compra_no_credito_e_a_vista() -> None:
    # Nubank: fecha no último dia, vence dia 8 -> compra de 07/10 vence em novembro
    assert purchase_months(40000, 4, TODAY, 31, 8) == [
        (date(2026, 11, 1), 10000),
        (date(2026, 12, 1), 10000),
        (date(2027, 1, 1), 10000),
        (date(2027, 2, 1), 10000),
    ]
    assert purchase_months(20000, 1, TODAY) == [(date(2026, 10, 1), 20000)]
    assert purchase_months(10000, 3, TODAY) == [
        (date(2026, 11, 1), 3334),
        (date(2026, 12, 1), 3333),
        (date(2027, 1, 1), 3333),
    ]


def test_media_avulsa_sem_parcelas_sem_contas_fixas_e_fora_da_janela() -> None:
    expenses = [
        _past(date(2026, 7, 10), 90000),
        _past(date(2026, 8, 10), 90000),
        _past(date(2026, 9, 10), 90000),
        _past(date(2026, 9, 12), 15000, "Academia Smart"),  # conta fixa: fora
        _past(date(2026, 9, 15), 30000, "tv", total=10),  # parcelado: fora
        _past(date(2026, 10, 2), 50000),  # mês corrente: fora
        _past(date(2026, 6, 30), 99900),  # antes da janela
    ]
    assert average_variable(expenses, ["academia"], TODAY) == (90000, 3)


def test_media_com_pouco_historico_divide_pelos_meses_que_ha() -> None:
    expenses = [_past(date(2026, 9, 20), 60000)]
    assert average_variable(expenses, [], TODAY) == (60000, 1)
    assert average_variable([], [], TODAY) == (0, 0)


def _advice(purchase, committed=None, pct=20):  # noqa: ANN001
    expenses = [_past(date(2026, m, 10), 90000) for m in (7, 8, 9)]
    for month, cents in (committed or {}).items():
        expenses.append(_past(date(2026, 9, 1), cents, "tv", total=10, month=month))
    return advise(
        purchase=purchase,
        income=350000,
        fixed=150000,
        fixed_names=["Aluguel"],
        expenses=expenses,
        today=TODAY,
        folga_pct=pct,
    )


def test_cenario_do_fone_em_4x() -> None:
    a = _advice(purchase_months(40000, 4, TODAY, 31, 8), {date(2026, 12, 1): 30000})
    dec = next(m for m in a.months if m.month == date(2026, 12, 1))
    assert dec.leftover == 70000  # 3.500 − 1.500 − 900 − 300 − 100 = 700 (20%)
    assert a.decisive.month == date(2026, 12, 1)
    assert a.verdict == "segura"


def test_atencao_entre_zero_e_a_folga() -> None:
    a = _advice(purchase_months(40000, 4, TODAY, 31, 8), {date(2026, 12, 1): 30001})
    assert a.verdict == "atencao"


def test_mes_negativo_e_arriscada() -> None:
    a = _advice(purchase_months(40000, 4, TODAY, 31, 8), {date(2027, 1, 1): 105000})
    assert a.verdict == "arriscada"
    assert a.decisive.month == date(2027, 1, 1)
    assert a.decisive.leftover == -5000


async def test_renda_e_contas_fixas(ctx: ToolContext) -> None:
    r = await gerenciar_renda(ctx, GerenciarRendaArgs(amount_cents=350000, day=5))
    assert r["status"] == "criado"
    assert r["resumo"] == "Renda: Salário, R$ 3.500,00 todo dia 5"
    assert r["renda_mensal"] == "R$ 3.500,00"
    await gerenciar_conta_fixa(
        ctx, GerenciarContaFixaArgs(name="Aluguel", amount_cents=90000, day=10)
    )
    a = await gerenciar_conta_fixa(
        ctx,
        GerenciarContaFixaArgs(
            name="Academia", amount_cents=15000, day=31, payment_method="nubank"
        ),
    )
    assert a["resumo"] == "Conta fixa: Academia, R$ 150,00 no último dia do mês, no Nubank"
    assert a["contas_fixas_mensal"] == "R$ 1.050,00"
    upd = await gerenciar_conta_fixa(
        ctx, GerenciarContaFixaArgs(name="aluguél", amount_cents=95000, day=10)
    )
    assert upd["status"] == "atualizado" and upd["contas_fixas_mensal"] == "R$ 1.100,00"
    tira = await gerenciar_conta_fixa(ctx, GerenciarContaFixaArgs(name="academia", remover=True))
    assert tira["status"] == "removido" and tira["contas_fixas_mensal"] == "R$ 950,00"
    with pytest.raises(ToolError) as exc:
        await gerenciar_conta_fixa(ctx, GerenciarContaFixaArgs(name="netflix", remover=True))
    assert exc.value.payload["opcoes"] == ["Aluguel"]
    # depois de removida, dá para cadastrar de novo com o mesmo nome
    again = await gerenciar_conta_fixa(
        ctx, GerenciarContaFixaArgs(name="Academia", amount_cents=12000, day=5)
    )
    assert again["status"] == "criado"


def test_valor_e_dia_obrigatorios_menos_para_remover() -> None:
    with pytest.raises(ValueError):
        GerenciarRendaArgs(amount_cents=100)
    GerenciarRendaArgs(remover=True)


async def test_sem_renda_pede_a_renda(ctx: ToolContext) -> None:
    with pytest.raises(ToolError) as exc:
        await avaliar_compra(ctx, AvaliarCompraArgs(amount_cents=20000, description="tênis"))
    assert exc.value.payload["falta"] == "renda"


async def test_avaliar_compra_no_banco(ctx: ToolContext) -> None:
    await gerenciar_renda(ctx, GerenciarRendaArgs(amount_cents=350000, day=5))
    await gerenciar_conta_fixa(
        ctx, GerenciarContaFixaArgs(name="Aluguel", amount_cents=150000, day=10)
    )
    for month in (7, 8, 9):
        await record_expense(
            ctx,
            LancarGastoArgs(
                amount_cents=90000, description="mercado", payment_method="Pix",
                spent_on=date(2026, month, 10),
            ),
        )  # fmt: skip
    # TV em 10x de R$ 30,00 em agosto: parcela de dezembro já comprometida
    await record_expense(
        ctx,
        LancarGastoArgs(
            amount_cents=30000, description="tv", payment_method="Nubank", installments=10,
            spent_on=date(2026, 8, 20),
        ),
    )  # fmt: skip
    r = await avaliar_compra(
        ctx,
        AvaliarCompraArgs(
            amount_cents=40000, description="fone", payment_method="nubank", installments=4
        ),
    )
    assert r["veredito"] == "segura"
    assert [m["mes"] for m in r["meses"]] == ["11/2026", "12/2026", "01/2027", "02/2027"]
    nov = r["meses"][0]
    assert nov["parcelas_comprometidas"] == "R$ 30,00" and nov["media_avulsa"] == "R$ 900,00"
    assert nov["sobra"] == "R$ 970,00" and nov["sobra_pct"] == 27
    assert r["compra"] == "R$ 400,00 em 4x no Nubank"
    assert "aviso" not in r


async def test_avaliar_parcelado_no_debito_recusa(ctx: ToolContext) -> None:
    await gerenciar_renda(ctx, GerenciarRendaArgs(amount_cents=350000, day=5))
    with pytest.raises(ToolError, match="Parcelamento só no crédito"):
        await avaliar_compra(
            ctx, AvaliarCompraArgs(amount_cents=40000, payment_method="pix", installments=4)
        )
