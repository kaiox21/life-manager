"""Abrir projetos e rascunhos no cérebro (jarvis-projetos): turno encerrado com fala fixa, painel
fechado ao abrir o projeto, botão Copiar e texto do rascunho fora do log."""

import logging
from pathlib import Path

from jarvis.agent import PERSONA, JarvisBrain
from jarvis.local_tools import DRAFT_REPLY, LocalTools
from tests.fakes import StreamingScriptedLLM, call, reply
from tests.jarvis.test_agent import FakeCore
from tests.jarvis.test_local_tools import PASTA, FakeControl, FakeRunner
from tests.jarvis.test_voice import FakeSpeaker

TEXTO = "Prezado professor,\n\nEstive doente na semana da prova. Peço a segunda chamada.\n\nKaio"
PEDIDO = {
    "tipo": "email",
    "para": "professor de redes",
    "assunto": "Segunda chamada",
    "texto": TEXTO,
}


def build(tmp_path: Path, llm, control=None):
    runner = FakeRunner()
    local = LocalTools(runner=runner, config={}, control=control, drafts_dir=tmp_path / "rascunhos")
    brain = JarvisBrain(llm, FakeCore(), local, primary="fake/p", escalation="fake/e")
    return brain, runner


async def run(brain, text, mode="texto"):
    got = []

    async def emit(ev):
        got.append(ev)

    await brain.ask("r1", text, emit, mode=mode)
    return got


async def test_rascunho_encerra_o_turno_sem_segunda_chamada(tmp_path):
    llm = StreamingScriptedLLM(call("rascunho", PEDIDO), reply("NÃO DEVIA SER CHAMADO"))
    brain, runner = build(tmp_path, llm)
    got = await run(brain, "escreve um e-mail pro professor de redes pedindo a segunda chamada")
    assert len(llm.calls) == 1  # a ferramenta encerrou o turno
    done = [e for e in got if e.type == "done"]
    assert done and done[0].text == DRAFT_REPLY
    assert [e.text for e in got if e.type == "token"] == [DRAFT_REPLY]
    cards = [e.card for e in got if e.type == "card"]
    assert cards == [
        {
            "kind": "rascunho",
            "title": "Rascunho · e-mail para professor de redes",
            "to": "professor de redes",
            "subject": "Segunda chamada",
            "text": TEXTO,
            "file": str(next((tmp_path / "rascunhos").glob("*.md"))),
        }
    ]
    assert runner.calls == [(["pbcopy"], TEXTO.encode())]
    assert brain._history[-1] == {"role": "assistant", "content": DRAFT_REPLY}


async def test_rascunho_por_voz_fala_so_a_frase_fixa(tmp_path):
    llm = StreamingScriptedLLM(call("rascunho", PEDIDO))
    brain, _ = build(tmp_path, llm)
    brain.speaker = FakeSpeaker()
    await run(brain, "escreve um e-mail pro professor", mode="voz")
    assert DRAFT_REPLY in brain.speaker.said
    assert all(TEXTO.split("\n")[0] not in s for s in brain.speaker.said)


async def test_abrir_projeto_fecha_o_painel_e_responde_fixo(tmp_path):
    llm = StreamingScriptedLLM(call("abrir_projeto", {"nome": "NC Barber"}))
    brain, runner = build(tmp_path, llm, control=FakeControl({"pasta": PASTA}))
    got = await run(brain, "abre o NC Barber")
    assert len(llm.calls) == 1
    assert [e.type for e in got if e.type in ("card", "panel_close", "done")] == [
        "card",
        "panel_close",
        "done",
    ]
    assert got[-1].text == "NC-BARBER aberto no Visual Studio Code, senhor. Terminal 3."
    assert runner.calls[0][0][:2] == ["open", "-a"]


async def test_projeto_recusado_volta_ao_modelo_sem_fechar_o_painel(tmp_path):
    llm = StreamingScriptedLLM(
        call("abrir_projeto", {"nome": "sisdec"}), reply("Qual dos dois, senhor?")
    )
    control = FakeControl({"opcoes": ["~/A/sisdec", "~/P/sisdec"]})
    brain, _ = build(tmp_path, llm, control=control)
    got = await run(brain, "abre o sisdec")
    assert len(llm.calls) == 2 and got[-1].text == "Qual dos dois, senhor?"
    assert not [e for e in got if e.type == "panel_close"]


async def test_botao_copiar_passa_pelo_cerebro(tmp_path):
    brain, runner = build(tmp_path, StreamingScriptedLLM())
    await brain.local_action("rascunho_copiar", "oi de novo")
    await brain.local_action("rascunho_copiar", "x" * 7000)
    await brain.local_action("rascunho_copiar")
    assert runner.calls == [(["pbcopy"], b"oi de novo")]


async def test_texto_do_rascunho_nao_vai_para_o_log(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    brain, _ = build(tmp_path, StreamingScriptedLLM(call("rascunho", PEDIDO)))
    await run(brain, "escreve um e-mail pro professor")
    assert f"rascunho: email para professor de redes ({len(TEXTO)} caracteres)" in caplog.text
    assert "Prezado" not in caplog.text and "segunda chamada" not in caplog.text.lower()


def test_prompt_proibe_envio_e_tira_a_persona_do_texto():
    assert "Você nunca envia e-mail nem mensagem" in PERSONA
    assert 'assinado "Kaio", sem "senhor"' in PERSONA
