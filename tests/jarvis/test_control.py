import asyncio
import secrets
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from jarvis.agent import JarvisBrain
from jarvis.control import OUTPUT, TerminalControl
from jarvis.local_tools import LocalTools
from jarvis.permissions import ALLOW, DENY_MESSAGE, IN_TAB, Permissions
from jarvis.sessions import Folders, PtyClient
from jarvis.terminals import PERMISSION, WAITING, WORKING, Terminals
from jarvis.tmux import Tmux, find_tmux, minimal_env
from tests.fakes import ScriptedLLM, call, reply
from tests.jarvis.test_agent import FakeCore, Runner, _ask
from tests.jarvis.test_sessions import wait_for

CONF = Path(__file__).resolve().parents[2] / "jarvis/tmux.conf"
pytestmark = pytest.mark.skipif(find_tmux() is None, reason="sem tmux")
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

    def output(self) -> bytes:
        return b"".join(f[9:] for f in self.frames if f[:1] == OUTPUT)


@pytest.fixture
async def env(tmp_path: Path):
    (tmp_path / "proj/life-manager").mkdir(parents=True)
    (tmp_path / "proj/sisdec").mkdir(parents=True)
    tmux = Tmux(socket=f"jt-ctl-{secrets.token_hex(3)}", conf=CONF)
    terminals = Terminals(path=tmp_path / "events.jsonl", alive=lambda pid: True)
    control = TerminalControl(
        tmux, terminals, Permissions(), Folders([tmp_path / "proj"]), memory=lambda: 50
    )
    sent: list = []

    async def broadcast(ev):
        sent.append(ev)

    control.broadcast = broadcast
    yield control, sent, tmp_path
    await control.shutdown()
    await tmux.run("kill-server")


def claude_on(control, t, event="SessionStart", pid=4242):
    """Simula um Claude Code rodando no terminal (eventos dos hooks pelo painel)."""
    control.terminals.apply(
        {
            "evento": event,
            "pid": pid,
            "sessao": "c1",
            "painel": t.painel,
            "socket": control.tmux.socket,
            "t": 1,
        }
    )


async def opened(control, pasta="life-manager"):
    result = await control.open(pasta)
    assert result["status"] == "aberto", result
    t = control.terminals.by_key(f"tmux:{result['sessao']}")
    await asyncio.sleep(0.6)  # shell de login pronto
    return result, t


def window(control, tmux_args):
    """Uma 'janela do Terminal.app': cliente do tmux num pty, fora do controle."""
    out: list[bytes] = []
    c = PtyClient(
        [*control.tmux.base(), *tmux_args], minimal_env(), Path.home(), out.append, lambda: None
    )
    return c, out


async def refreshed(control, pred):
    await control.refresh()
    return pred()


async def until(pred, limit=6.0):
    end = asyncio.get_running_loop().time() + limit
    while not await pred():
        if asyncio.get_running_loop().time() > end:
            raise AssertionError("tempo esgotado")
        await asyncio.sleep(0.1)


async def yes(_q):
    return True


async def no(_q):
    return False


async def test_abre_terminal_com_aba_e_numero(env):
    control, sent, _ = env
    control.terminals.apply(
        {"evento": "SessionStart", "pid": 999, "sessao": "x", "pasta": "/fora", "t": 1}
    )
    result, t = await opened(control)
    assert result["numero"] == 2 and result["tipo"] == "shell" and result["pasta"] == "life-manager"
    assert (t.tipo, t.aba, t.origem, t.janela) == ("shell", True, "jarvis", False)
    view = next(x for x in sent[-1].data["terminais"] if x["numero"] == 2)
    assert view["aba"] is True and view["ocupado"] is False


async def test_abrir_claude_manda_o_comando(env, monkeypatch):
    control, _, _ = env
    sent_cmds: list[str] = []

    async def fake_send(painel, cmd):
        sent_cmds.append(cmd)
        return True

    monkeypatch.setattr(control.tmux, "send_command", fake_send)
    result = await control.open("sisdec", claude=True)
    assert result["tipo"] == "claude" and sent_cmds == ["claude"]


async def test_pasta_fora_memoria_e_limite(env):
    control, _, _ = env
    assert "erro" in await control.open("/")
    control._memory = lambda: 10
    assert "pouca memória" in (await control.open("sisdec"))["erro"]
    control._memory = lambda: 50
    _, t = await opened(control)
    control.max_claude = 1
    claude_on(control, t)
    assert "limite é 1" in (await control.open("sisdec", claude=True))["erro"]
    assert (await control.open("sisdec"))["status"] == "aberto"  # shell continua liberado


async def test_comando_no_shell_confirmado_cancelado_e_ocupado(env):
    control, _, tmp = env
    _, t = await opened(control)
    asked: list[str] = []

    async def ask(q):
        asked.append(q)
        return True

    out = await control.send(t.numero, "echo ok > feito.txt", ask)
    assert out["status"] == "enviado" and out["tipo"] == "comando"
    assert asked == [f"Comando no Terminal {t.numero} (life-manager): echo ok > feito.txt"]
    await wait_for(lambda: (tmp / "proj/life-manager/feito.txt").exists())
    assert (await control.send(t.numero, "echo x > nao.txt", no))["status"] == "cancelado"
    await asyncio.sleep(0.5)
    assert not (tmp / "proj/life-manager/nao.txt").exists()
    assert "uma linha" in (await control.send(t.numero, "echo a\necho b", yes))["erro"]
    await control.tmux.send_command(t.painel, "sleep 5")
    await until(lambda: refreshed(control, lambda: control.terminals.by_key(t.chave).ocupado))
    assert "programa rodando" in (await control.send(t.numero, "git status", yes))["erro"]


async def test_ficou_ocupado_entre_a_confirmacao_e_o_envio(env):
    control, _, tmp = env
    _, t = await opened(control)

    async def busy_then_yes(_q):
        await control.tmux.send_command(t.painel, "sleep 5")
        await asyncio.sleep(0.8)
        return True

    out = await control.send(t.numero, "echo tarde > tarde.txt", busy_then_yes)
    assert "programa rodando" in out["erro"]
    await asyncio.sleep(0.3)
    assert not (tmp / "proj/life-manager/tarde.txt").exists()


async def test_mensagem_ao_claude_so_parado(env):
    control, _, tmp = env
    _, t = await opened(control)
    claude_on(control, t)  # esperando você
    t = control.terminals.by_key(t.chave)
    assert t.tipo == "claude" and t.estado == WAITING
    out = await control.send(t.numero, "echo colado > msg.txt", yes)  # o "claude" aqui é o zsh
    assert out["tipo"] == "mensagem"
    await wait_for(lambda: (tmp / "proj/life-manager/msg.txt").exists())
    claude_on(control, t, "UserPromptSubmit")
    assert "trabalhando" in (await control.send(t.numero, "oi", yes))["erro"]
    claude_on(control, t, "PermissionRequest")
    assert control.terminals.by_key(t.chave).estado == PERMISSION
    assert "diálogo de permissão" in (await control.send(t.numero, "roda os testes", yes))["erro"]


async def test_sessao_de_fora_e_inexistente(env):
    control, _, _ = env
    control.terminals.apply(
        {"evento": "SessionStart", "pid": 999, "sessao": "x", "pasta": "/fora", "t": 1}
    )
    assert "não é um terminal compartilhado" in (await control.send(1, "oi", yes))["erro"]
    assert "Não há Terminal 9" in (await control.send(9, "oi", yes))["erro"]


async def test_fechar_pede_confirmacao_com_janela(env):
    control, _, _ = env
    _, t = await opened(control)
    win, _ = window(control, ["attach-session", "-t", t.tmux])
    await until(lambda: refreshed(control, lambda: control.terminals.by_key(t.chave).janela))
    asked: list[str] = []

    async def ask_no(q):
        asked.append(q)
        return False

    assert (await control.close(t.numero, ask_no))["status"] == "cancelado"
    assert "janela dele no Terminal.app também fecha" in asked[0]
    assert (await control.close(t.numero, yes))["status"] == "fechado"
    assert await control.tmux.panes() == []
    await win.close()


async def test_aba_mantem_terminal_do_terminal_app_sem_janela(env):
    control, _, tmp = env
    # janela do Terminal.app: o bloco do .zshrc liga destroy-unattached depois de conectar
    win, _ = window(
        control,
        [
            "new-session", "-c", str(tmp), ";",
            "set-option", "destroy-unattached", "on", ";",
            "set-option", "@jarvis_origem", "terminal",
        ],
    )  # fmt: skip
    await until(
        lambda: refreshed(
            control, lambda: any(t.origem == "terminal" for t in control.terminals._by_key.values())
        )
    )
    t = next(iter(control.terminals._by_key.values()))
    assert await control.open_tab(t.tmux)
    await win.close()  # fecha a janela
    await asyncio.sleep(0.5)
    await control.refresh()
    kept = control.terminals.by_key(t.chave)
    assert kept is not None and kept.aba and not kept.janela  # vive pela aba
    await control.close_tab(t.tmux)  # × sem janela: acaba
    await asyncio.sleep(0.3)
    assert await control.tmux.panes() == []


async def test_aba_anexada_mostra_e_digita(env):
    control, _, _ = env
    _, t = await opened(control)
    win, win_out = window(control, ["attach-session", "-t", t.tmux])
    panel = FakeClient()
    await control.handle(panel, {"type": "term_attach", "sessao": t.tmux, "cols": 100, "rows": 30})
    assert panel.attached == t.tmux
    await asyncio.sleep(0.5)
    await control.handle(
        panel, {"type": "term_input", "sessao": t.tmux, "data": "echo digitado-na-aba\r"}
    )
    await wait_for(lambda: b"digitado-na-aba" in panel.output())
    await wait_for(lambda: b"digitado-na-aba" in b"".join(win_out))  # aparece na janela também
    assert control.own_clients() == {t.tmux: 1}
    await control.handle(panel, {"type": "term_detach", "sessao": t.tmux})
    assert panel.attached is None and control.own_clients() == {}
    await win.close()


async def test_permitir_pelo_botao(env):
    control, sent, _ = env
    _, t = await opened(control)
    claude_on(control, t, "UserPromptSubmit")
    hook = asyncio.create_task(control.on_hook("jarvis", {**BODY, "jarvis_painel": t.painel}))
    await wait_for(lambda: any(e.type == "terminal_alert" for e in sent))
    alert = [e for e in sent if e.type == "terminal_alert"][-1].data
    assert alert["pedido"] and alert["chave"] == t.chave
    assert (
        alert["texto"] == f"Terminal {t.numero} (life-manager) está pedindo para rodar `npm test`"
    )
    client = FakeClient()
    answer = {"type": "permission_answer", "pedido": alert["pedido"], "decisao": "permitir"}
    await control.handle(client, answer)
    out = await hook
    assert out["hookSpecificOutput"]["decision"] == {"behavior": "allow"}
    assert control.terminals.by_key(t.chave).estado == WORKING
    assert [e for e in sent if e.type == "terminal_resolved"][-1].data["resultado"] == ALLOW
    await control.handle(client, {**answer, "decisao": "negar"})
    assert client.got[-1].data == {"pedido": alert["pedido"], "resultado": "já respondido"}


async def test_negar_tecla_na_aba_e_proximo_evento(env):
    control, sent, _ = env
    _, t = await opened(control)
    claude_on(control, t, "UserPromptSubmit")

    def alerts():
        return [e for e in sent if e.type == "terminal_alert"]

    async def ask():
        n = len(alerts())
        task = asyncio.create_task(control.on_hook("jarvis", {**BODY, "jarvis_painel": t.painel}))
        await wait_for(lambda: len(alerts()) > n)
        return task, alerts()[-1].data["pedido"]

    hook, pedido = await ask()
    await control.handle(
        FakeClient(), {"type": "permission_answer", "pedido": pedido, "decisao": "negar"}
    )
    decision = (await hook)["hookSpecificOutput"]["decision"]
    assert decision == {"behavior": "deny", "message": DENY_MESSAGE}

    panel = FakeClient()
    await control.handle(panel, {"type": "term_attach", "sessao": t.tmux})
    hook, _ = await ask()
    await control.handle(panel, {"type": "term_input", "sessao": t.tmux, "data": "1"})
    assert await hook == {}
    assert [e for e in sent if e.type == "terminal_resolved"][-1].data["resultado"] == IN_TAB

    hook, _ = await ask()
    claude_on(control, t, "PostToolUse")
    assert await asyncio.wait_for(hook, 2) == {}


async def test_hook_de_painel_desconhecido_responde_vazio(env):
    control, _, _ = env
    assert await control.on_hook("jarvis", {**BODY, "jarvis_painel": "%999"}) == {}


async def test_term_open_e_abas_pela_interface(env):
    control, _, _ = env
    client = FakeClient()
    await control.handle(client, {"type": "term_open", "pasta": "sisdec"})
    ev = client.got[-1]
    assert ev.type == "terminal_opened" and ev.data["status"] == "aberto"
    sessao = ev.data["sessao"]
    await control.handle(client, {"type": "term_tab_close", "sessao": sessao})
    t = control.terminals.by_key(f"tmux:{sessao}")
    assert t is not None and not t.aba  # aberto pelo Jarvis: fechar a aba não encerra
    await control.handle(client, {"type": "term_tab_open", "sessao": sessao})
    assert control.terminals.by_key(f"tmux:{sessao}").aba


# --- pelo modelo (tarefa 4.2)


def brain_with(control, llm):
    local = LocalTools(
        runner=Runner(), config={}, terminals=control.terminals.snapshot, control=control
    )
    return JarvisBrain(llm, FakeCore(), local, primary="fake/p", escalation="fake/e")


async def test_modelo_manda_comando_com_confirmacao(env):
    control, _, tmp = env
    _, t = await opened(control)
    llm = ScriptedLLM(
        call("mandar_terminal", {"numero": t.numero, "texto": "echo voz > voz.txt"}),
        reply("Feito."),
    )
    evs = await _ask(brain_with(control, llm), "Terminal 1, roda echo voz", answers=[True])
    (confirm,) = [e for e in evs if e.type == "confirm"]
    assert confirm.text == f"Comando no Terminal {t.numero} (life-manager): echo voz > voz.txt"
    await wait_for(lambda: (tmp / "proj/life-manager/voz.txt").exists())


async def test_modelo_cancelado_nao_escreve(env):
    control, _, tmp = env
    _, t = await opened(control)
    llm = ScriptedLLM(
        call("mandar_terminal", {"numero": t.numero, "texto": "touch nao.txt"}), reply("Ok.")
    )
    await _ask(brain_with(control, llm), "Terminal 1, cria o arquivo", answers=[False])
    await asyncio.sleep(0.5)
    assert not (tmp / "proj/life-manager/nao.txt").exists()


async def test_modelo_abre_terminal_sem_expor_a_sessao(env):
    control, _, _ = env
    llm = ScriptedLLM(call("abrir_terminal", {"pasta": "sisdec"}), reply("Aberto, senhor."))
    await _ask(brain_with(control, llm), "abre um terminal no sisdec")
    sent_to_model = llm.calls[1]["messages"][-1]["content"]
    assert '"numero": 1' in sent_to_model and "sessao" not in sent_to_model


def test_nao_existe_ferramenta_de_aprovar(env):
    control, _, _ = env
    tools = LocalTools(runner=Runner(), config={}, control=control).openai_tools()
    names = {t["function"]["name"] for t in tools}
    assert not {n for n in names if any(w in n for w in ("permit", "aprov", "negar", "permiss"))}
