import json

from jarvis import events
from jarvis.agent import GIVE_UP, JarvisBrain
from jarvis.local_tools import Completed, LocalTools
from jarvis.mcp_client import ToolResult
from tests.fakes import ScriptedLLM, call, reply

CORE_TOOLS = [
    "contexto",
    "painel",
    "buscar_eventos",
    "lancar_gasto",
    "confirmar_pendente",
    "total_fatura",
]


class FakeCore:
    def __init__(self, results=None):
        self.calls: list[tuple[str, dict]] = []
        self.results = results or {}

    async def openai_tools(self):
        return [
            {"type": "function", "function": {"name": n, "description": "", "parameters": {}}}
            for n in CORE_TOOLS
        ]

    async def call(self, name, args):
        self.calls.append((name, args))
        if name == "contexto":
            return ToolResult(
                True, "Agora: 08/10/2026 17:00. amanhã: sexta 09/10/2026 (2026-10-09)"
            )
        res = self.results.get(name)
        if callable(res):
            return res(args)
        return res or ToolResult(True, {"status": "ok"})


class Runner:
    def __init__(self):
        self.calls = []

    async def __call__(self, argv, stdin):
        self.calls.append(argv)
        return Completed(0, "", "")


def brain(llm, core, runner=None):
    local = LocalTools(runner=runner or Runner(), config={})
    return JarvisBrain(llm, core, local, primary="fake/p", escalation="fake/e")


async def _ask(b, text, answers=()):
    got: list[events.Event] = []
    answers = list(answers)

    async def emit(ev):
        got.append(ev)
        if ev.type == "confirm":
            await b.resolve_confirmation(ev.confirm_id, answers.pop(0))

    await b.ask("r1", text, emit)
    return got


async def test_abre_safari_e_busca_agenda_de_amanha():
    agenda = {
        "eventos": [{"titulo": "Dentista", "data": "sexta 09/10/2026", "hora": "14:00"}],
        "total": 1,
        "omitidos": 0,
    }
    core = FakeCore({"buscar_eventos": ToolResult(True, agenda)})
    runner = Runner()
    llm = ScriptedLLM(
        call("abrir_app", {"nome": "Safari"}),
        call("buscar_eventos", {"de": "2026-10-09", "ate": "2026-10-09"}, n=2),
        reply("Abri o Safari. Amanhã você tem dentista às 14h."),
    )
    evs = await _ask(brain(llm, core, runner), "abre o Safari e me diz meus compromissos de amanhã")
    assert runner.calls == [["open", "-a", "Safari"]]
    assert ("buscar_eventos", {"de": "2026-10-09", "ate": "2026-10-09"}) in core.calls
    steps = [e.text for e in evs if e.type == "step"]
    assert steps == ["lendo o contexto…", "abrindo Safari…", "consultando a agenda…"]
    (card,) = [e.card for e in evs if e.type == "card"]
    assert card["kind"] == "agenda" and card["title"] == "Agenda · 09/10"
    assert evs[-1].type == "done" and "dentista" in evs[-1].text
    system = llm.calls[0]["messages"][0]["content"]
    assert "Jarvis" in system and "sexta 09/10/2026" in system
    offered = {t["function"]["name"] for t in llm.calls[0]["tools"]}
    assert not {"contexto", "painel"} & offered and {"abrir_app", "lancar_gasto"} <= offered
    assert evs[-1].data == {}  # só leitura: o painel não precisa atualizar


async def test_pendencia_do_nucleo_vira_confirmacao_na_interface():
    pend = {
        "status": "aguardando_confirmacao",
        "pending_id": "p1",
        "resumo": "R$ 900,00 no Nubank — jantar. Confirma?",
    }
    core = FakeCore(
        {
            "lancar_gasto": ToolResult(True, pend),
            "confirmar_pendente": lambda a: ToolResult(
                True, {"status": "gravado", "resumo": "R$ 900,00 — jantar"}
            ),
        }
    )
    llm = ScriptedLLM(call("lancar_gasto", {"amount_cents": 90000}), reply("Gravado."))
    evs = await _ask(brain(llm, core), "jantar 900 no nubank", answers=[True])
    (conf,) = [e for e in evs if e.type == "confirm"]
    assert "Confirma?" in conf.text
    assert ("confirmar_pendente", {"pending_id": "p1", "decisao": "sim"}) in core.calls
    tool_msg = llm.calls[1]["messages"][-1]["content"]
    assert json.loads(tool_msg)["status"] == "gravado"


async def test_recusar_confirmacao_cancela():
    pend = {
        "status": "aguardando_confirmacao",
        "pending_id": "p2",
        "resumo": "Remover X. Confirma?",
    }
    core = FakeCore(
        {
            "lancar_gasto": ToolResult(True, pend),
            "confirmar_pendente": lambda a: ToolResult(
                True, {"status": "cancelado", "resumo": "X"}
            ),
        }
    )
    llm = ScriptedLLM(call("lancar_gasto", {}), reply("Cancelado."))
    await _ask(brain(llm, core), "x", answers=[False])
    assert ("confirmar_pendente", {"pending_id": "p2", "decisao": "nao"}) in core.calls


async def test_erro_de_validacao_volta_e_escala_continuando_a_conversa():
    core = FakeCore({"total_fatura": ToolResult(False, "argumentos inválidos: use AAAA-MM")})
    llm = ScriptedLLM(
        call("total_fatura", {"mes_vencimento": "11/2026"}),
        call("abrir_app", {"nome": "Safari", "x": 1}, n=2),
        reply("Ok."),
    )
    evs = await _ask(brain(llm, core), "fatura")
    assert [c["model"] for c in llm.calls] == ["fake/p", "fake/p", "fake/e"]
    # a escalada recebe a conversa inteira, com os erros anteriores
    assert sum(1 for m in llm.calls[2]["messages"] if m.get("role") == "tool") == 2
    assert evs[-1].text == "Ok."


async def test_desiste_depois_da_escalada():
    core = FakeCore({"total_fatura": ToolResult(False, "inválido")})
    llm = ScriptedLLM(*[call("total_fatura", {}, n=i) for i in range(4)])
    evs = await _ask(brain(llm, core), "fatura")
    assert evs[-1].text == GIVE_UP


async def test_historico_entre_perguntas():
    core = FakeCore()
    llm = ScriptedLLM(reply("Oi, Kaio."), reply("De nada."))
    b = brain(llm, core)
    await _ask(b, "oi")
    await _ask(b, "valeu")
    msgs = llm.calls[1]["messages"]
    assert {"role": "user", "content": "oi"} in msgs
    assert {"role": "assistant", "content": "Oi, Kaio."} in msgs


PAINEL = {"agora": "2026-10-08T17:00:00-03:00", "mes": {"total_centavos": 4790}, "registro": []}


async def _panel(b):
    got: list[events.Event] = []

    async def emit(ev):
        got.append(ev)

    await b.panel("p1", emit)
    return got


async def test_painel_vem_do_nucleo_sem_o_modelo_e_com_as_perguntas():
    core = FakeCore({"painel": ToolResult(True, PAINEL)})
    llm = ScriptedLLM(reply("Oi."))
    b = brain(llm, core)
    await _ask(b, "oi jarvis")
    llm_calls = len(llm.calls)

    (ev,) = await _panel(b)
    assert ev.type == "panel" and ev.id == "p1"
    assert ev.data["mes"] == {"total_centavos": 4790}
    assert ev.data["perguntas"] == ["oi jarvis"]
    assert len(llm.calls) == llm_calls  # nenhum token
    assert core.calls[-1] == ("painel", {})


async def test_painel_com_nucleo_fora_do_ar():
    class DownCore(FakeCore):
        async def call(self, name, args):
            raise ConnectionError("núcleo parado")

    (ev,) = await _panel(brain(ScriptedLLM(), DownCore()))
    assert ev.data == {"erro": "núcleo indisponível"}


async def test_done_avisa_quando_o_turno_gravou():
    core = FakeCore({"lancar_gasto": ToolResult(True, {"status": "gravado", "resumo": "ok"})})
    llm = ScriptedLLM(call("lancar_gasto", {"amount_cents": 3000}), reply("Lancei."))
    evs = await _ask(brain(llm, core), "30 de uber no nubank")
    assert evs[-1].type == "done" and evs[-1].data == {"wrote": True}
