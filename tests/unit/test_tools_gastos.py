from datetime import date, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.agent.tools.base import ToolError, brl
from app.agent.tools.confirmacao import ConfirmarPendenteArgs, confirmar_pendente
from app.agent.tools.consultas import (
    BuscarGastosArgs,
    ResumoGastosArgs,
    TotalFaturaArgs,
    buscar_gastos,
    resumo_gastos,
    total_fatura,
)
from app.agent.tools.gastos import (
    GerenciarMeioPagamentoArgs,
    LancarGastoArgs,
    SemArgs,
    desfazer_ultimo,
    gerenciar_meio_pagamento,
    lancar_gasto,
)
from app.agent.tools.resolve import resolve_payment_method
from app.clock import fixed_clock
from app.db.models import Expense, PaymentMethod, PendingAction
from tests.conftest import NOW


def gasto(**kw) -> LancarGastoArgs:
    base = {"amount_cents": 4790, "description": "almoço", "payment_method": "nubank"}
    return LancarGastoArgs(**(base | kw))


async def _expenses(ctx) -> list[Expense]:
    stmt = select(Expense).where(Expense.deleted_at.is_(None)).order_by(Expense.installment_no)
    return list((await ctx.session.scalars(stmt)).all())


def test_brl():
    assert brl(4790) == "R$ 47,90"
    assert brl(123456) == "R$ 1.234,56"
    assert brl(5) == "R$ 0,05"


# --- resolução de meio de pagamento


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("nubank", "Nubank"),
        ("NUBANK", "Nubank"),
        ("débito", "Itaú Débito"),
        ("debito do itau", "Itaú Débito"),
        ("crédito do itaú", "Itaú Crédito"),
        ("itau credito", "Itaú Crédito"),
        ("Itaú Crédito", "Itaú Crédito"),
        ("pix", "Pix"),
    ],
)
async def test_resolve_meio(ctx, texto, esperado):
    assert (await resolve_payment_method(ctx.session, texto)).name == esperado


@pytest.mark.parametrize("texto", ["itaú", "crédito", "cartão"])
async def test_meio_ambiguo_pede_para_perguntar(ctx, texto):
    with pytest.raises(ToolError) as err:
        await resolve_payment_method(ctx.session, texto)
    assert len(err.value.payload["opcoes"]) >= 2


async def test_meio_inexistente(ctx):
    with pytest.raises(ToolError) as err:
        await resolve_payment_method(ctx.session, "inter")
    assert "não cadastrado" in err.value.payload["erro"]


async def test_fatura_so_considera_credito(ctx):
    pm = await resolve_payment_method(ctx.session, "itaú", kinds={"credito"})
    assert pm.name == "Itaú Crédito"


# --- lancar_gasto


async def test_lanca_gasto_no_credito_com_fatura(ctx):
    out = await lancar_gasto(ctx, gasto(category="alimentacao"))
    assert out["status"] == "gravado"
    assert out["valor"] == "R$ 47,90"
    assert out["categoria"] == "Alimentação"
    assert out["fatura_vence"] == "08/11/2026"
    (row,) = await _expenses(ctx)
    assert row.amount_cents == 4790
    assert row.spent_on == date(2026, 10, 7)
    assert row.statement_month == date(2026, 11, 1)
    assert row.source == "texto"


async def test_lanca_no_debito_sem_fatura(ctx):
    out = await lancar_gasto(ctx, gasto(payment_method="débito"))
    assert out["meio"] == "Itaú Débito"
    assert "fatura_vence" not in out
    (row,) = await _expenses(ctx)
    assert row.statement_month is None


async def test_sem_categoria_vai_para_outros(ctx):
    out = await lancar_gasto(ctx, gasto())
    assert out["categoria"] == "Outros"


async def test_data_passada_e_futura(ctx):
    await lancar_gasto(ctx, gasto(spent_on=date(2026, 10, 6)))
    (row,) = await _expenses(ctx)
    assert row.spent_on == date(2026, 10, 6)
    with pytest.raises(ToolError):
        await lancar_gasto(ctx, gasto(spent_on=date(2026, 10, 8)))


async def test_acima_de_500_vira_pendencia_e_nao_grava(ctx):
    out = await lancar_gasto(
        ctx,
        gasto(
            amount_cents=60000, description="tênis", installments=3, payment_method="itaú crédito"
        ),
    )
    assert out["status"] == "aguardando_confirmacao"
    assert "R$ 600,00 em 3x" in out["resumo"]
    assert await _expenses(ctx) == []


async def test_exatamente_500_grava_direto(ctx):
    out = await lancar_gasto(ctx, gasto(amount_cents=50000))
    assert out["status"] == "gravado"


async def test_audio_sempre_pede_confirmacao(ctx):
    ctx.source = "audio"
    out = await lancar_gasto(ctx, gasto())
    assert out["status"] == "aguardando_confirmacao"


async def test_parcelado_so_no_credito(ctx):
    with pytest.raises(ToolError):
        await lancar_gasto(ctx, gasto(payment_method="pix", installments=2))


async def test_argumentos_invalidos_falham_na_validacao():
    with pytest.raises(ValidationError):
        LancarGastoArgs(amount_cents=0, description="x", payment_method="pix")
    with pytest.raises(ValidationError):
        LancarGastoArgs(amount_cents=10, description="x", payment_method="pix", extra=1)
    with pytest.raises(ValidationError):
        LancarGastoArgs(amount_cents=47.9, description="x", payment_method="pix")


# --- confirmação


async def test_confirmar_sim_grava_parcelas(ctx):
    await lancar_gasto(
        ctx,
        gasto(
            amount_cents=60000, description="tênis", installments=3, payment_method="itaú crédito"
        ),
    )
    out = await confirmar_pendente(ctx, ConfirmarPendenteArgs(decisao="sim"))
    assert out["status"] == "gravado"
    rows = await _expenses(ctx)
    assert [(r.installment_no, r.amount_cents, r.statement_month) for r in rows] == [
        (1, 20000, date(2026, 11, 1)),
        (2, 20000, date(2026, 12, 1)),
        (3, 20000, date(2027, 1, 1)),
    ]
    assert len({r.purchase_group for r in rows}) == 1
    # Confirmar de novo não grava duas vezes.
    again = await confirmar_pendente(ctx, ConfirmarPendenteArgs(decisao="sim"))
    assert again["status"] == "sem_pendencia"
    assert len(await _expenses(ctx)) == 3


async def test_confirmar_nao_cancela(ctx):
    await lancar_gasto(ctx, gasto(amount_cents=90000))
    out = await confirmar_pendente(ctx, ConfirmarPendenteArgs(decisao="nao"))
    assert out["status"] == "cancelado"
    assert await _expenses(ctx) == []
    status = await ctx.session.scalar(select(PendingAction.status))
    assert status == "cancelled"


async def test_pendencia_expira_em_30_minutos(ctx):
    await lancar_gasto(ctx, gasto(amount_cents=90000))
    ctx.clock = fixed_clock(NOW + timedelta(minutes=31))
    out = await confirmar_pendente(ctx, ConfirmarPendenteArgs(decisao="sim"))
    assert out["status"] == "sem_pendencia"
    assert await _expenses(ctx) == []


# --- desfazer


async def test_desfazer_remove_compra_inteira_logicamente(ctx):
    await lancar_gasto(ctx, gasto(amount_cents=30000, installments=3, description="fone"))
    out = await desfazer_ultimo(ctx, SemArgs())
    assert out["status"] == "desfeito"
    assert "R$ 300,00" in out["resumo"]
    assert await _expenses(ctx) == []
    total_rows = await ctx.session.scalar(select(func.count()).select_from(Expense))
    assert total_rows == 3  # exclusão lógica


async def test_desfazer_sem_nada(ctx):
    assert (await desfazer_ultimo(ctx, SemArgs()))["status"] == "nada_para_desfazer"


# --- meios de pagamento


async def test_cadastra_e_atualiza_cartao(ctx):
    args = GerenciarMeioPagamentoArgs(name="C6", kind="credito", closing_day=5, due_day=15)
    assert (await gerenciar_meio_pagamento(ctx, args))["status"] == "criado"
    args2 = GerenciarMeioPagamentoArgs(name="c6", kind="credito", closing_day=6, due_day=16)
    assert (await gerenciar_meio_pagamento(ctx, args2))["status"] == "atualizado"
    pm = await ctx.session.scalar(select(PaymentMethod).where(PaymentMethod.name == "C6"))
    assert (pm.closing_day, pm.due_day) == (6, 16)


def test_credito_exige_dias():
    with pytest.raises(ValidationError):
        GerenciarMeioPagamentoArgs(name="C6", kind="credito")
    with pytest.raises(ValidationError):
        GerenciarMeioPagamentoArgs(name="Pix2", kind="pix", closing_day=3)


# --- consultas (somas sempre em SQL)


async def _carga(ctx):
    for kw in [
        {"amount_cents": 4790, "description": "almoço", "category": "Alimentação"},
        {
            "amount_cents": 21000,
            "description": "mercado",
            "category": "Mercado",
            "spent_on": date(2026, 10, 2),
        },
        {
            "amount_cents": 2300,
            "description": "uber",
            "category": "Transporte",
            "payment_method": "pix",
        },
        {
            "amount_cents": 1500,
            "description": "Uber Eats",
            "category": "Alimentação",
            "spent_on": date(2026, 9, 29),
        },
        {
            "amount_cents": 8990,
            "description": "spotify",
            "category": "Assinaturas",
            "payment_method": "itaú crédito",
            "spent_on": date(2026, 9, 26),
        },
        {
            "amount_cents": 31245,
            "description": "mercado grande",
            "category": "Mercado",
            "payment_method": "itaú crédito",
            "spent_on": date(2026, 9, 20),
        },
    ]:
        await lancar_gasto(ctx, gasto(**kw))


async def test_buscar_gastos_soma_em_sql(ctx):
    await _carga(ctx)
    out = await buscar_gastos(
        ctx, BuscarGastosArgs(de=date(2026, 10, 1), ate=date(2026, 10, 7), category="mercado")
    )
    assert out["total_centavos"] == 21000
    assert out["lancamentos"] == 1


async def test_buscar_por_texto_sem_acento_e_caixa(ctx):
    await _carga(ctx)
    out = await buscar_gastos(ctx, BuscarGastosArgs(query="UBER"))
    assert out["total_centavos"] == 3800
    out = await buscar_gastos(ctx, BuscarGastosArgs(query="almoco"))
    assert out["total_centavos"] == 4790


async def test_buscar_limite_nao_afeta_a_soma(ctx):
    await _carga(ctx)
    out = await buscar_gastos(ctx, BuscarGastosArgs(limite=2))
    assert len(out["itens"]) == 2
    assert out["lancamentos"] == 6
    assert out["itens_omitidos"] == 4
    assert out["total_centavos"] == 4790 + 21000 + 2300 + 1500 + 8990 + 31245


async def test_buscar_ignora_desfeitos(ctx):
    await _carga(ctx)
    await desfazer_ultimo(ctx, SemArgs())  # mercado grande
    out = await buscar_gastos(ctx, BuscarGastosArgs(payment_method="itaú crédito"))
    assert out["total_centavos"] == 8990


async def test_total_fatura_nubank_bate_com_a_soma_a_mao(ctx):
    await _carga(ctx)
    # Nubank fecha no último dia: 29/09 cai na fatura de 08/10; outubro na de 08/11.
    nov = await total_fatura(
        ctx, TotalFaturaArgs(payment_method="nubank", mes_vencimento="2026-11")
    )
    assert nov["total_centavos"] == 4790 + 21000
    assert nov["lancamentos"] == 2
    assert nov["vencimento"] == "08/11/2026"
    assert nov["fechamento"] == "31/10/2026"
    assert nov["situacao"] == "aberta"
    assert nov["maiores_itens"][0]["descricao"] == "mercado"
    out_ = await total_fatura(
        ctx, TotalFaturaArgs(payment_method="nubank", mes_vencimento="2026-10")
    )
    assert out_["total_centavos"] == 1500
    assert out_["situacao"] == "fechada"


async def test_total_fatura_itau_resolve_para_credito(ctx):
    await _carga(ctx)
    # Itaú fecha 25: 20/09 -> vence 05/10; 26/09 -> vence 05/11.
    out = await total_fatura(ctx, TotalFaturaArgs(payment_method="itaú", mes_vencimento="2026-10"))
    assert out["cartao"] == "Itaú Crédito"
    assert out["total_centavos"] == 31245
    out = await total_fatura(ctx, TotalFaturaArgs(payment_method="itau", mes_vencimento="2026-11"))
    assert out["total_centavos"] == 8990


def test_mes_vencimento_formato():
    with pytest.raises(ValidationError):
        TotalFaturaArgs(payment_method="nubank", mes_vencimento="11/2026")


async def test_resumo_por_categoria_e_dia(ctx):
    await _carga(ctx)
    out = await resumo_gastos(
        ctx, ResumoGastosArgs(de=date(2026, 9, 1), ate=date(2026, 9, 30), agrupar_por="categoria")
    )
    assert out["total_centavos"] == 1500 + 8990 + 31245
    assert out["grupos"][0] == {
        "grupo": "Mercado",
        "total": "R$ 312,45",
        "total_centavos": 31245,
        "lancamentos": 1,
    }
    out = await resumo_gastos(
        ctx, ResumoGastosArgs(de=date(2026, 10, 1), ate=date(2026, 10, 7), agrupar_por="dia")
    )
    assert [g["grupo"] for g in out["grupos"]] == ["02/10/2026", "07/10/2026"]


def test_periodo_invertido_invalido():
    with pytest.raises(ValidationError):
        ResumoGastosArgs(de=date(2026, 10, 7), ate=date(2026, 10, 1), agrupar_por="dia")
