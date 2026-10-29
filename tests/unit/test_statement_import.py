"""Importação da fatura em PDF contra o Postgres de teste, com o LLM falso (sem rede)."""

import json
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.service import Models, answer
from app.agent.tools.base import ToolContext
from app.agent.tools.confirmacao import ConfirmarPendenteArgs, confirmar_pendente
from app.agent.tools.gastos import LancarGastoArgs, SemArgs, desfazer_ultimo, record_expense
from app.clock import fixed_clock
from app.db.models import AgentRun, Expense, PendingAction, StatementImport
from app.statements.service import import_statement
from tests.conftest import NOW
from tests.fakes import ScriptedLLM, call
from tests.pdfs import FATURA_FICTICIA, text_pdf

PDF = text_pdf(FATURA_FICTICIA)
CLOCK = fixed_clock(NOW)
MODELS = Models("fake/classifier", "fake/primary", "fake/escalation")

TRANSCRICAO = {
    "emissor": "Banco Ficticio",
    "final_cartao": "7890",
    "vencimento": "2026-11-08",
    "total_impresso": "R$ 1.307,40",
    "saldo_anterior": "R$ 900,00",
    "pagamentos": "-R$ 900,00",
    "itens": [
        {"data": "16/10", "descricao": "RESTAURANTE X", "valor": "47,90", "tipo": "compra",
         "categoria": "Alimentação"},
        {"data": "18/10", "descricao": "LOJA Y", "valor": "120,00", "parcela": "03/10",
         "tipo": "compra", "categoria": "Compras"},
        {"data": "20/10", "descricao": "MERCADO Z", "valor": "1.234,56", "tipo": "compra",
         "categoria": "mercado"},
        {"data": "21/10", "descricao": "ESTORNO MERCADO Z", "valor": "-95,06", "tipo": "estorno"},
        {"data": "22/10", "descricao": "IOF COMPRA INTERNACIONAL", "valor": "0,00",
         "tipo": "encargo"},
        {"data": "25/10", "descricao": "PAGAMENTO RECEBIDO", "valor": "-900,00",
         "tipo": "pagamento"},
    ],
}  # fmt: skip


def _llm(*payloads: dict | str) -> ScriptedLLM:  # type: ignore[type-arg]
    return ScriptedLLM(*(call("registrar_fatura", p) for p in payloads))


async def _import(s: AsyncSession, llm: ScriptedLLM, cartao: str | None = "nubank") -> dict:  # type: ignore[type-arg]
    return await import_statement(
        llm=llm,
        primary="fake/primary",
        escalation="fake/escalation",
        session=s,
        clock=CLOCK,
        pdf=PDF,
        cartao=cartao,
    )


async def test_importa_e_so_grava_depois_do_sim(seeded: async_sessionmaker[AsyncSession]) -> None:
    async with seeded.begin() as s:
        result = await _import(s, _llm(TRANSCRICAO))
        assert result["status"] == "aguardando_confirmacao"
        assert result["soma_confere"] is True
        assert result["novos"] == 4  # pagamento e linha zerada não viram gasto
        assert "A soma confere com o total da fatura." in result["resumo"]
        assert await s.scalar(select(func.count()).select_from(Expense)) == 0

    async with seeded.begin() as s:
        ctx = ToolContext(session=s, clock=CLOCK)
        done = await confirmar_pendente(ctx, ConfirmarPendenteArgs(decisao="sim"))
        assert done["status"] == "fatura_gravada"
        assert done["resumo"] == (
            "Lancei 4 gastos da fatura do Nubank (venc. 08/11), R$ 1.307,40, "
            "mais 7 parcelas futuras."
        )

    async with seeded() as s:
        rows = (
            await s.scalars(select(Expense).order_by(Expense.spent_on, Expense.installment_no))
        ).all()
        assert len(rows) == 11  # 3 avulsos + parcelas 3 a 10
        assert {r.source for r in rows} == {"fatura"}
        loja = [r for r in rows if r.description == "LOJA Y"]
        assert [r.installment_no for r in loja] == list(range(3, 11))
        assert loja[0].statement_month == date(2026, 11, 1)
        assert loja[-1].statement_month == date(2027, 6, 1)
        assert len({r.purchase_group for r in loja}) == 1
        estorno = next(r for r in rows if r.description.startswith("ESTORNO"))
        assert estorno.amount_cents == -9506
        imp = (await s.scalars(select(StatementImport))).one()
        assert imp.printed_total_cents == 130740 and imp.items_count == 5


async def test_casa_o_que_ja_foi_lancado(ctx: ToolContext) -> None:
    await record_expense(
        ctx,
        LancarGastoArgs(
            amount_cents=4790, description="almoço", payment_method="Nubank",
            spent_on=date(2026, 10, 15),
        ),
    )  # fmt: skip
    result = await _import(ctx.session, _llm(TRANSCRICAO))
    assert result["ja_lancados"] == 1 and result["novos"] == 3
    assert "1 já estavam lançados." in result["resumo"]
    assert "RESTAURANTE X" not in result["resumo"]


async def test_nao_descarta(seeded: async_sessionmaker[AsyncSession]) -> None:
    async with seeded.begin() as s:
        await _import(s, _llm(TRANSCRICAO))
    async with seeded.begin() as s:
        done = await confirmar_pendente(
            ToolContext(session=s, clock=CLOCK), ConfirmarPendenteArgs(decisao="nao")
        )
        assert done["status"] == "cancelado"
        assert "Importar 4 gastos da fatura do Nubank" in done["resumo"]
        assert await s.scalar(select(func.count()).select_from(Expense)) == 0


async def test_reimportar_nao_duplica(seeded: async_sessionmaker[AsyncSession]) -> None:
    async with seeded.begin() as s:
        await _import(s, _llm(TRANSCRICAO))
    async with seeded.begin() as s:
        await confirmar_pendente(
            ToolContext(session=s, clock=CLOCK), ConfirmarPendenteArgs(decisao="sim")
        )
    async with seeded.begin() as s:
        again = await _import(s, _llm(TRANSCRICAO))
        assert again["status"] == "nada_novo"
        assert "nada novo para lançar" in again["resumo"]
        assert "Já importada em" in again["resumo"]
        pending = await s.scalar(
            select(func.count()).select_from(PendingAction).where(PendingAction.status == "pending")
        )
        assert pending == 0
        assert await s.scalar(select(func.count()).select_from(Expense)) == 11


async def test_soma_divergente_avisa_no_comeco(ctx: ToolContext) -> None:
    sem_item = {**TRANSCRICAO, "itens": TRANSCRICAO["itens"][1:]}
    result = await _import(ctx.session, _llm(sem_item))
    assert result["soma_confere"] is False
    assert result["resumo"].startswith(
        "Atenção: os itens somam R$ 47,90 a menos que o total da fatura"
    )


async def test_invalida_volta_ao_modelo_e_depois_escala(ctx: ToolContext) -> None:
    ruim = {**TRANSCRICAO, "vencimento": "08/11/2026"}
    llm = _llm(ruim, ruim, TRANSCRICAO)
    result = await _import(ctx.session, llm)
    assert result["status"] == "aguardando_confirmacao"
    assert [c["model"] for c in llm.calls] == ["fake/primary", "fake/primary", "fake/escalation"]
    # a 2ª tentativa recebeu o erro de validação
    assert "erro_validacao" in llm.calls[1]["messages"][-2]["content"]


async def test_conta_impossivel_escala(ctx: ToolContext) -> None:
    sem_total = {**TRANSCRICAO, "total_impresso": None}
    llm = _llm(sem_total, TRANSCRICAO)
    result = await _import(ctx.session, llm)
    assert result["status"] == "aguardando_confirmacao"
    assert [c["model"] for c in llm.calls] == ["fake/primary", "fake/escalation"]


async def test_falha_nos_dois_modelos_recusa(ctx: ToolContext) -> None:
    sem_total = {**TRANSCRICAO, "total_impresso": None}
    result = await _import(ctx.session, _llm(sem_total, sem_total))
    assert result["status"] == "recusada"
    assert "Não consegui ler os itens" in result["resumo"]


async def test_cartao_desconhecido_pergunta(ctx: ToolContext) -> None:
    result = await _import(ctx.session, _llm(TRANSCRICAO), cartao=None)
    assert result["status"] == "qual_cartao"
    assert set(result["opcoes"]) == {"Nubank", "Itaú Crédito"}


async def test_cartao_pelo_emissor(ctx: ToolContext) -> None:
    itau = {**TRANSCRICAO, "emissor": "Banco Itaú"}
    result = await _import(ctx.session, _llm(itau), cartao=None)
    assert result["cartao"] == "Itaú Crédito"


async def test_debito_nao_e_cartao_de_fatura(ctx: ToolContext) -> None:
    result = await _import(ctx.session, _llm(TRANSCRICAO), cartao="itaú débito")
    assert result["status"] == "qual_cartao"


async def test_agent_runs_sem_conteudo_da_fatura(seeded: async_sessionmaker[AsyncSession]) -> None:
    async with seeded.begin() as s:
        await _import(s, _llm(TRANSCRICAO))
    async with seeded() as s:
        run = (await s.scalars(select(AgentRun))).one()
        assert run.intent == "fatura"
        assert run.input_tokens and run.cost_usd
        dumped = json.dumps(run.tools_called)
        assert "RESTAURANTE" not in dumped and "7890" not in dumped
        assert [t["name"] for t in run.tools_called] == [
            "extracao",
            "transcricao",
            "importar_fatura",
        ]


async def test_sim_pelo_whatsapp_responde_sem_modelo(
    seeded: async_sessionmaker[AsyncSession],
) -> None:
    async with seeded.begin() as s:
        await _import(s, _llm(TRANSCRICAO))
    async with seeded.begin() as s:
        reply = await answer(
            llm=ScriptedLLM(), models=MODELS, session=s, clock=CLOCK, text="sim", message_id=None
        )
    assert reply.startswith("Lancei 4 gastos da fatura do Nubank")


async def test_pendencia_expirada_nao_grava(seeded: async_sessionmaker[AsyncSession]) -> None:
    async with seeded.begin() as s:
        await _import(s, _llm(TRANSCRICAO))
    later = fixed_clock(NOW + timedelta(minutes=31))
    async with seeded.begin() as s:
        done = await confirmar_pendente(
            ToolContext(session=s, clock=later), ConfirmarPendenteArgs(decisao="sim")
        )
        assert done["status"] == "sem_pendencia"
        assert await s.scalar(select(func.count()).select_from(Expense)) == 0


async def test_casado_desfeito_antes_do_sim_avisa(seeded: async_sessionmaker[AsyncSession]) -> None:
    async with seeded.begin() as s:
        ctx = ToolContext(session=s, clock=CLOCK)
        await record_expense(
            ctx,
            LancarGastoArgs(
                amount_cents=4790, description="almoço", payment_method="Nubank",
                spent_on=date(2026, 10, 15),
            ),
        )  # fmt: skip
        await _import(s, _llm(TRANSCRICAO))
        await desfazer_ultimo(ctx, SemArgs())
    async with seeded.begin() as s:
        done = await confirmar_pendente(
            ToolContext(session=s, clock=CLOCK), ConfirmarPendenteArgs(decisao="sim")
        )
    assert "1 gasto(s) que casava(m) com a fatura foi(ram) desfeito(s)" in done["resumo"]
