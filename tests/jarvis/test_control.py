import asyncio
import json
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from jarvis import events
from jarvis.agent import JarvisBrain
from jarvis.control import OUTPUT, REPLAY, TerminalControl
from jarvis.local_tools import LocalTools
from jarvis.permissions import ALLOW, DENY_MESSAGE, IN_TAB, Permissions
from jarvis.sessions import Folders, Sessions
from jarvis.terminals import PERMISSION, WORKING, Terminals
from tests.fakes import ScriptedLLM, call, reply
from tests.jarvis.test_agent import FakeCore, Runner, _ask
from tests.jarvis.test_sessions import fake_command, wait_for

BODY = {
    "hook_event_name": "PermissionRequest",
    "tool_name": "Bash",
    "tool_input": {"command": "npm test"},
}


@dataclass(eq=False)
class FakeClient:
    got: list = field(default_factory=list)
    frames: list = field(default_factory=list)
    attached: str | None = None
    backlog: int = 0

    async def emit(self, ev):
        self.got.append(ev)

    async def send_bytes(self, data):
        self.frames.append(data)

    def output(self, sid: str) -> bytes:
        return b"".join(
            f[9:] for f in self.frames if f[:1] == OUTPUT and f[1:9].decode().strip() == sid
        )


@pytest.fixture
def setup(tmp_path: Path):
    (tmp_path / "proj/life-manager").mkdir(parents=True)
    (tmp_path / "proj/sisdec").mkdir(parents=True)
    sessions = Sessions(
        Folders([tmp_path / "proj"]),
        command=fake_command,
        memory=lambda: 50,
        tabs_file=tmp_path / "abas.json",
    )
    terminals = Terminals(path=tmp_path / "events.jsonl", alive=lambda pid: True)
    control = TerminalControl(sessions, terminals, Permissions())
    sent: list[events.Event] = []

    async def broadcast(ev):
        sent.append(ev)

    control.broadcast = broadcast
    return control, sent, tmp_path


async def close_all(control: TerminalControl) -> None:
    for sid in list(control.sessions.open):
        await control.sessions.close(sid)


async def open_ready(control, pasta="life-manager"):
    result = await control.open(pasta)
    s = control.sessions.open[result["sid"]]
    await wait_for(lambda: b"<pronto" in bytes(s.buffer))
    return result, s


async def test_abre_com_o_proximo_numero_e_publica_as_abas(setup):
    control, sent, tmp = setup
    control.terminals.apply(
        {"evento": "SessionStart", "pid": 999, "sessao": "x", "pasta": "/tmp/fora", "t": 1}
    )
    result, s = await open_ready(control)
    assert (
        result["status"] == "aberto" and result["numero"] == 2 and result["pasta"] == "life-manager"
    )
    t = control.terminals.by_pid(s.pid)
    assert t.numero == 2 and t.aba == s.sid
    tabs = [e for e in sent if e.type == "terminal_tabs"][-1].data["abas"]
    assert tabs == [
        {"sid": s.sid, "numero": 2, "pasta": "life-manager", "aberta": True, "pid": s.pid}
    ]
    hello = bytes(s.buffer).decode()
    assert '"--settings"' in hello and "permissao" in hello
    await close_all(control)


async def test_pasta_fora_e_ambigua(setup):
    control, _, _ = setup
    assert "erro" in await control.open("/")
    assert "erro" in await control.open("nao-existe")


async def test_mandar_confirmado_cancelado_e_de_fora(setup):
    control, _, _ = setup
    control.terminals.apply(
        {"evento": "SessionStart", "pid": 999, "sessao": "x", "pasta": "/tmp/fora", "t": 1}
    )
    _, s = await open_ready(control)
    asked: list[str] = []

    async def yes(q):
        asked.append(q)
        return True

    async def no(q):
        return False

    out = await control.send(2, "roda os testes\x03", yes)
    assert out == {
        "status": "enviado",
        "numero": 2,
        "pasta": "life-manager",
        "texto": "roda os testes",
    }
    assert asked == ["Mandar para o Terminal 2 (life-manager): roda os testes"]
    await wait_for(lambda: b"<eco \r>" in bytes(s.buffer))  # colagem e o Enter chegaram
    assert b"\x1b[200~roda os testes\x1b[201~" in bytes(s.buffer)
    before = bytes(s.buffer)
    assert (await control.send(2, "outra coisa", no))["status"] == "cancelado"
    await asyncio.sleep(0.3)
    assert bytes(s.buffer) == before  # nada escrito
    assert "não foi aberto pelo Jarvis" in (await control.send(1, "oi", yes))["erro"]
    assert "Não há Terminal 7" in (await control.send(7, "oi", yes))["erro"]
    await close_all(control)


async def test_fechar_trabalhando_pede_confirmacao(setup):
    control, _, _ = setup
    _, s = await open_ready(control)
    control.terminals.apply({"evento": "UserPromptSubmit", "pid": s.pid, "sessao": "a", "t": 5})
    assert control.terminals.by_pid(s.pid).estado == WORKING
    asked: list[str] = []

    async def no(q):
        asked.append(q)
        return False

    assert (await control.close(1, no))["status"] == "cancelado"
    assert "está trabalhando" in asked[0] and s.sid in control.sessions.open

    async def yes(q):
        return True

    assert (await control.close(1, yes))["status"] == "fechado"
    assert control.sessions.open == {}


async def test_permitir_pelo_botao(setup):
    control, sent, _ = setup
    _, s = await open_ready(control)
    hook = asyncio.create_task(control.permissions.handle(s.sid, BODY))
    await wait_for(lambda: any(e.type == "terminal_alert" for e in sent))
    alert = [e for e in sent if e.type == "terminal_alert"][-1].data
    assert alert["pedido"] and alert["aba"] == s.sid and alert["numero"] == 1
    assert alert["texto"] == "Terminal 1 (life-manager) está pedindo para rodar `npm test`"
    assert control.terminals.by_pid(s.pid).estado == PERMISSION
    client = FakeClient()
    await control.handle(
        client, {"type": "permission_answer", "pedido": alert["pedido"], "decisao": "permitir"}
    )
    out = await hook
    assert out["hookSpecificOutput"]["decision"] == {"behavior": "allow"}
    assert control.terminals.by_pid(s.pid).estado == WORKING
    resolved = [e for e in sent if e.type == "terminal_resolved"][-1].data
    assert resolved == {"pedido": alert["pedido"], "resultado": ALLOW}
    # clique atrasado
    await control.handle(
        client, {"type": "permission_answer", "pedido": alert["pedido"], "decisao": "negar"}
    )
    assert client.got[-1].data == {"pedido": alert["pedido"], "resultado": "já respondido"}
    await close_all(control)


async def test_negar_pelo_botao(setup):
    control, sent, _ = setup
    _, s = await open_ready(control)
    hook = asyncio.create_task(control.permissions.handle(s.sid, BODY))
    await wait_for(lambda: any(e.type == "terminal_alert" for e in sent))
    pedido = [e for e in sent if e.type == "terminal_alert"][-1].data["pedido"]
    await control.handle(
        FakeClient(), {"type": "permission_answer", "pedido": pedido, "decisao": "negar"}
    )
    assert (await hook)["hookSpecificOutput"]["decision"] == {
        "behavior": "deny",
        "message": DENY_MESSAGE,
    }
    await close_all(control)


async def test_decisao_invalida_nao_faz_nada(setup):
    control, sent, _ = setup
    _, s = await open_ready(control)
    hook = asyncio.create_task(control.permissions.handle(s.sid, BODY))
    await wait_for(lambda: any(e.type == "terminal_alert" for e in sent))
    pedido = [e for e in sent if e.type == "terminal_alert"][-1].data["pedido"]
    await control.handle(
        FakeClient(), {"type": "permission_answer", "pedido": pedido, "decisao": "sempre"}
    )
    assert not hook.done()
    await control.permissions.resolve(pedido, IN_TAB)
    assert await hook == {}
    await close_all(control)


async def test_tecla_na_aba_resolve_o_pedido(setup):
    control, sent, _ = setup
    _, s = await open_ready(control)
    hook = asyncio.create_task(control.permissions.handle(s.sid, BODY))
    await wait_for(lambda: any(e.type == "terminal_alert" for e in sent))
    await control.handle(FakeClient(), {"type": "term_input", "sid": s.sid, "data": "1"})
    assert await hook == {}  # o diálogo da aba decide
    assert [e for e in sent if e.type == "terminal_resolved"][-1].data["resultado"] == IN_TAB
    await close_all(control)


async def test_proximo_evento_resolve_e_guarda_a_sessao(setup):
    control, sent, _ = setup
    _, s = await open_ready(control)
    control.terminals.apply({"evento": "SessionStart", "pid": s.pid, "sessao": "sess-1", "t": 2})
    assert s.sessao == "sess-1"
    assert json.loads(control.sessions._tabs_file.read_text())[0]["sessao"] == "sess-1"
    hook = asyncio.create_task(control.permissions.handle(s.sid, BODY))
    await wait_for(lambda: any(e.type == "terminal_alert" for e in sent))
    # o hook global anota o mesmo pedido: não gera um segundo aviso nem resolve
    assert (
        control.terminals.apply(
            {"evento": "PermissionRequest", "pid": s.pid, "ferramenta": "Bash", "t": 3}
        )
        is None
    )
    await asyncio.sleep(0.05)
    assert not hook.done()
    control.terminals.apply({"evento": "PostToolUse", "pid": s.pid, "t": 4})
    assert await asyncio.wait_for(hook, 2) == {}
    await close_all(control)


async def test_pedido_aberto_nao_expira_em_20s(setup):
    control, sent, _ = setup
    now = [1000.0]
    control.terminals._clock = lambda: now[0]
    _, s = await open_ready(control)
    hook = asyncio.create_task(control.permissions.handle(s.sid, BODY))
    await wait_for(lambda: any(e.type == "terminal_alert" for e in sent))
    now[0] += 60
    control.terminals.tick()
    assert control.terminals.by_pid(s.pid).estado == PERMISSION
    await control.permissions.resolve_session(s.sid, IN_TAB)
    await hook
    await close_all(control)


async def test_saida_so_para_quem_anexou_e_replay(setup):
    control, _, _ = setup
    _, s = await open_ready(control)
    panel, hud = FakeClient(), FakeClient()
    await control.handle(hud, {"type": "term_resize", "sid": s.sid, "cols": 90, "rows": 20})
    await control.handle(panel, {"type": "term_attach", "sid": s.sid})
    assert panel.frames[0][:1] == REPLAY and b"<pronto" in panel.frames[0]
    await control.handle(panel, {"type": "term_input", "sid": s.sid, "data": "abc"})
    await wait_for(lambda: b"<eco abc>" in panel.output(s.sid))
    assert hud.output(s.sid) == b""
    await control.handle(panel, {"type": "term_detach", "sid": s.sid})
    await control.handle(panel, {"type": "term_input", "sid": s.sid, "data": "zz"})
    await wait_for(lambda: b"<eco zz>" in bytes(s.buffer))
    await asyncio.sleep(0.05)
    assert b"<eco zz>" not in panel.output(s.sid)
    await close_all(control)


async def test_sessao_que_sai_expira_o_pedido_e_vira_encerrada(setup):
    control, sent, _ = setup
    _, s = await open_ready(control)
    hook = asyncio.create_task(control.permissions.handle(s.sid, BODY))
    await wait_for(lambda: any(e.type == "terminal_alert" for e in sent))
    os.killpg(s.pid, signal.SIGTERM)
    assert await asyncio.wait_for(hook, 3) == {}
    await wait_for(lambda: control.terminals.by_pid(s.pid) is None)
    tabs = control.sessions.tabs()
    assert len(tabs) == 1 and tabs[0]["aberta"] is False
    # "Retomar" abre uma sessão nova na mesma pasta
    result = await control.open(retomar=tabs[0]["sid"])
    assert result["status"] == "aberto"
    new = control.sessions.open[result["sid"]]
    await wait_for(lambda: b"<pronto" in bytes(new.buffer))
    assert '"--continue"' in bytes(new.buffer).decode()  # sem session_id conhecido
    assert all(t["aberta"] for t in control.sessions.tabs())
    await close_all(control)


async def test_term_open_pela_interface(setup):
    control, _, _ = setup
    client = FakeClient()
    await control.handle(client, {"type": "term_open", "pasta": "sisdec"})
    ev = client.got[-1]
    assert ev.type == "terminal_opened" and ev.data["status"] == "aberto"
    await control.handle(client, {"type": "term_close", "sid": ev.data["sid"]})
    assert control.sessions.open == {}


# --- pelo modelo (tarefa 3.2)


def brain_with(control, llm):
    local = LocalTools(
        runner=Runner(), config={}, terminals=control.terminals.snapshot, control=control
    )
    return JarvisBrain(llm, FakeCore(), local, primary="fake/p", escalation="fake/e")


async def test_modelo_manda_recado_com_confirmacao(setup):
    control, _, _ = setup
    _, s = await open_ready(control)
    b = brain_with(
        control,
        ScriptedLLM(
            call("mandar_terminal", {"numero": 1, "texto": "roda os testes"}), reply("Feito.")
        ),
    )
    evs = await _ask(b, "Terminal 1, roda os testes", answers=[True])
    (confirm,) = [e for e in evs if e.type == "confirm"]
    assert confirm.text == "Mandar para o Terminal 1 (life-manager): roda os testes"
    await wait_for(lambda: b"roda os testes" in bytes(s.buffer))
    await close_all(control)


async def test_modelo_recado_cancelado_nao_escreve(setup):
    control, _, _ = setup
    _, s = await open_ready(control)
    b = brain_with(
        control,
        ScriptedLLM(call("mandar_terminal", {"numero": 1, "texto": "rm -rf"}), reply("Ok.")),
    )
    await _ask(b, "Terminal 1, apaga tudo", answers=[False])
    await asyncio.sleep(0.3)
    assert b"rm -rf" not in bytes(s.buffer)
    await close_all(control)


async def test_modelo_abre_terminal_sem_expor_o_sid(setup):
    control, _, _ = setup
    llm = ScriptedLLM(call("abrir_terminal", {"pasta": "sisdec"}), reply("Aberto, senhor."))
    b = brain_with(control, llm)
    evs = await _ask(b, "abre um Claude Code no sisdec")
    sent_to_model = llm.calls[1]["messages"][-1]["content"]
    assert '"numero": 1' in sent_to_model and "sid" not in sent_to_model
    assert any(e.type == "card" and "aberto" in (e.card.get("text") or "") for e in evs)
    await close_all(control)


def test_nao_existe_ferramenta_de_aprovar(setup):
    control, _, _ = setup
    names = {
        t["function"]["name"]
        for t in LocalTools(runner=Runner(), config={}, control=control).openai_tools()
    }
    assert not {n for n in names if any(w in n for w in ("permit", "aprov", "negar", "permiss"))}
