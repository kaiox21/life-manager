from datetime import date

import pytest
from sqlalchemy import select

from app.agent.intent import parse_intent
from app.agent.loop import GIVE_UP, run_agent
from app.agent.service import Models, answer
from app.clock import fixed_clock
from app.db.models import AgentRun, Expense, Message, PendingAction
from tests.conftest import NOW
from tests.fakes import ScriptedLLM, call, reply


def cls(intent: str):
    return call("classificar", {"intencao": intent})


MODELS = Models(classifier="fake/cls", primary="fake/primary", escalation="fake/strong")
GASTO = {
    "amount_cents": 4790,
    "description": "almoço",
    "payment_method": "nubank",
    "category": "Alimentação",
}


CLOCK = fixed_clock(NOW)


async def _answer(seeded, llm, text, clock=CLOCK, strip_prefix=""):
    async with seeded.begin() as s:
        return await answer(
            llm=llm,
            models=MODELS,
            session=s,
            clock=clock,
            text=text,
            message_id=None,
            strip_prefix=strip_prefix,
        )


async def _all(seeded, model):
    async with seeded() as s:
        return list((await s.scalars(select(model))).all())


@pytest.mark.parametrize(
    ("raw", "intent"),
    [
        ("gasto", "gasto"),
        ("consulta_gasto", "consulta_gasto"),
        ("Intenção: CONSULTA_GASTO.", "consulta_gasto"),
        ("confirmacao", "confirmacao"),
        ("confirmação", "confirmacao"),
        ("não sei", "fora_do_escopo"),
        ("", "fora_do_escopo"),
        ('{"intencao": "gasto"}', "gasto"),
    ],
)
def test_parse_intent(raw, intent):
    assert parse_intent(raw) == intent


async def test_gasto_grava_e_registra_agent_run(seeded):
    llm = ScriptedLLM(
        cls("gasto"),
        call("lancar_gasto", GASTO),
        reply("Gravado: R$ 47,90 no Nubank. Diga desfazer para reverter."),
    )
    out = await _answer(seeded, llm, "gastei 47,90 no almoço no nubank")
    assert out.startswith("Gravado")
    (exp,) = await _all(seeded, Expense)
    assert exp.amount_cents == 4790 and exp.statement_month == date(2026, 11, 1)
    (run,) = await _all(seeded, AgentRun)
    assert run.intent == "gasto"
    assert run.model == "fake/primary"
    assert not run.escalated
    assert [t["name"] for t in run.tools_called] == ["lancar_gasto"]
    assert run.tools_called[0]["ok"] is True
    assert run.input_tokens == 20 + 20 + 10  # classificador + chamada + resposta
    assert run.cost_usd > 0
    # Só as ferramentas do grupo da intenção foram oferecidas.
    offered = {t["function"]["name"] for t in llm.calls[1]["tools"]}
    assert offered == {"lancar_gasto", "desfazer_ultimo", "gerenciar_meio_pagamento"}


async def test_argumento_invalido_volta_ao_modelo_uma_vez(seeded):
    llm = ScriptedLLM(
        cls("gasto"),
        call("lancar_gasto", GASTO | {"amount_cents": "47,90"}),
        call("lancar_gasto", GASTO, n=2),
        reply("Gravado."),
    )
    await _answer(seeded, llm, "gastei 47,90 no almoço no nubank")
    (run,) = await _all(seeded, AgentRun)
    assert not run.escalated
    assert [t["ok"] for t in run.tools_called] == [False, True]
    assert "erro_validacao" in llm.calls[2]["messages"][-1]["content"]
    assert len(await _all(seeded, Expense)) == 1


async def test_dois_fracassos_escalam_e_desfazem_efeitos_da_tentativa(seeded):
    llm = ScriptedLLM(
        cls("gasto"),
        # primário: grava, depois erra duas vezes
        call("lancar_gasto", GASTO),
        call("lancar_gasto", {"amount_cents": -1}, n=2),
        call("lancar_gasto", "{não é json", n=3),
        # escalada: acerta
        call("lancar_gasto", GASTO, n=4),
        reply("Gravado."),
    )
    out = await _answer(seeded, llm, "gastei 47,90 no almoço no nubank")
    assert out == "Gravado."
    (run,) = await _all(seeded, AgentRun)
    assert run.escalated and run.model == "fake/strong"
    assert len(await _all(seeded, Expense)) == 1  # o gasto do primário foi revertido
    assert [c["model"] for c in llm.calls[-2:]] == ["fake/strong", "fake/strong"]


async def test_escalada_tambem_falha_pede_para_reformular(seeded):
    bad = {"amount_cents": 0}
    llm = ScriptedLLM(
        cls("gasto"),
        call("lancar_gasto", bad),
        call("lancar_gasto", bad, n=2),
        call("lancar_gasto", bad, n=3),
        call("lancar_gasto", bad, n=4),
    )
    out = await _answer(seeded, llm, "lança aí")
    assert out == GIVE_UP
    (run,) = await _all(seeded, AgentRun)
    assert run.escalated and run.error
    assert await _all(seeded, Expense) == []


async def test_consulta_sem_ferramenta_escala(seeded):
    llm = ScriptedLLM(
        cls("consulta_gasto"),
        reply("Sua fatura está em R$ 1.000,00."),
        call("total_fatura", {"payment_method": "nubank", "mes_vencimento": "2026-11"}),
        reply("A fatura do Nubank que vence 08/11 está em R$ 0,00."),
    )
    out = await _answer(seeded, llm, "quanto tá a fatura do nubank?")
    assert "08/11" in out
    (run,) = await _all(seeded, AgentRun)
    assert run.escalated


async def test_meio_ambiguo_volta_como_resultado_e_modelo_pergunta(seeded):
    llm = ScriptedLLM(
        cls("gasto"),
        call("lancar_gasto", GASTO | {"payment_method": "itaú"}),
        reply("Foi no Itaú Crédito ou no Itaú Débito?"),
    )
    out = await _answer(seeded, llm, "padaria 12 no itaú")
    assert out.endswith("?")
    tool_msg = llm.calls[2]["messages"][-1]["content"]
    assert "ambíguo" in tool_msg and "Itaú Débito" in tool_msg
    (run,) = await _all(seeded, AgentRun)
    assert not run.escalated
    assert await _all(seeded, Expense) == []


async def test_ferramenta_de_outro_grupo_conta_como_falha(seeded):
    llm = ScriptedLLM(
        cls("gasto"),
        call("total_fatura", {}),
        call("lancar_gasto", GASTO, n=2),
        reply("Gravado."),
    )
    await _answer(seeded, llm, "gastei 47,90 no almoço no nubank")
    (run,) = await _all(seeded, AgentRun)
    assert run.tools_called[0]["ok"] is False
    assert "não serve" in run.tools_called[0]["error"]


async def test_agenda_recebe_ferramentas_de_agenda_e_pessoa(seeded):
    llm = ScriptedLLM(cls("agenda"), reply("Que horas?"))
    await _answer(seeded, llm, "dentista sexta")
    offered = {t["function"]["name"] for t in llm.calls[1]["tools"]}
    assert offered == {
        "criar_evento",
        "buscar_eventos",
        "atualizar_evento",
        "remover_evento",
        "gerenciar_pessoa",
    }


async def test_agenda_sem_consultar_escala(seeded):
    llm = ScriptedLLM(
        cls("agenda"),
        reply("É dia 31/10."),
        call("buscar_eventos", {"person": "Mariana"}),
        reply("Não achei."),
    )
    await _answer(seeded, llm, "quando é o aniversário dela?")
    (run,) = await _all(seeded, AgentRun)
    assert run.escalated
    assert [t["name"] for t in run.tools_called] == ["buscar_eventos"]


async def test_fora_do_escopo_sem_ferramentas(seeded):
    llm = ScriptedLLM(cls("fora_do_escopo"), reply("Isso não é comigo."))
    await _answer(seeded, llm, "qual a capital da Austrália?")
    assert llm.calls[1]["tools"] is None


async def test_sim_com_pendencia_confirma_sem_llm(seeded):
    big = GASTO | {
        "amount_cents": 60000,
        "description": "tênis",
        "installments": 3,
        "payment_method": "itaú crédito",
    }
    llm = ScriptedLLM(
        cls("gasto"),
        call("lancar_gasto", big),
        reply("R$ 600,00 em 3x no Itaú Crédito — tênis. Confirma?"),
    )
    await _answer(seeded, llm, "comprei um tênis de 600 em 3x no itaú crédito")
    assert await _all(seeded, Expense) == []

    llm2 = ScriptedLLM()
    out = await _answer(seeded, llm2, "Sim!")
    assert llm2.calls == []
    assert out.startswith("Gravado: R$ 600,00 em 3x")
    assert len(await _all(seeded, Expense)) == 3
    (pending,) = await _all(seeded, PendingAction)
    assert pending.status == "confirmed"
    runs = await _all(seeded, AgentRun)
    assert runs[-1].intent == "confirmacao"


async def test_nao_com_pendencia_cancela(seeded):
    big = GASTO | {"amount_cents": 90000}
    await _answer(
        seeded,
        ScriptedLLM(cls("gasto"), call("lancar_gasto", big), reply("Confirma?")),
        "jantar 900 no nubank",
    )
    out = await _answer(seeded, ScriptedLLM(), "não")
    assert out.startswith("Cancelado")
    assert await _all(seeded, Expense) == []


async def test_historico_vai_para_o_modelo_sem_a_marca(seeded):
    async with seeded.begin() as s:
        s.add_all(
            [
                Message(
                    channel="whatsapp", direction="in", type="text", body="quanto tá a fatura?"
                ),
                Message(
                    channel="whatsapp", direction="out", type="text", body="🤖 Está em R$ 10,00."
                ),
            ]
        )
    llm = ScriptedLLM(cls("consulta_gasto"), reply("De qual cartão?"))
    await _answer(seeded, llm, "e no itaú?", strip_prefix="🤖 ")
    msgs = llm.calls[1]["messages"]
    assert {"role": "assistant", "content": "Está em R$ 10,00."} in msgs
    assert msgs[-1] == {"role": "user", "content": "e no itaú?"}


async def test_stop_at_first_tool_nao_executa(ctx):
    llm = ScriptedLLM(call("lancar_gasto", GASTO))
    out = await run_agent(
        llm=llm,
        ctx=ctx,
        intent="gasto",
        system_prompt="s",
        history=[],
        text="x",
        primary_model="p",
        escalation_model="e",
        stop_at_first_tool=True,
    )
    assert out.first_call and out.first_call.name == "lancar_gasto"
    assert out.first_call.args["amount_cents"] == 4790
    assert (await ctx.session.scalars(select(Expense))).all() == []
