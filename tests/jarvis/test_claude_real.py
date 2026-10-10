"""Claude Code de verdade num terminal compartilhado (tmux isolado), com o hook de permissão do
Jarvis (tarefa 3.4). Fora do `pytest` comum: `uv run pytest -m claude tests/jarvis/test_claude_real.py`.

Usa o `claude` instalado e o login dele, com o Haiku e no modo manual (pede permissão para
`touch`). Custa centavos. A tela não é lida para decidir nada: o efeito (arquivo criado ou não)
diz o que valeu.
"""

import asyncio
import json
import secrets
from pathlib import Path

import pytest

from jarvis.control import TerminalControl
from jarvis.permissions import HookServer, Permissions
from jarvis.sessions import Folders
from jarvis.terminals import Terminals
from jarvis.tmux import Tmux, find_tmux
from tests.jarvis.test_control import FakeClient
from tests.jarvis.test_sessions import wait_for

pytestmark = pytest.mark.claude
REPO = Path(__file__).resolve().parents[2]
CLAUDE = Path.home() / ".local/bin/claude"


@pytest.fixture
async def env(tmp_path_factory):
    if not CLAUDE.exists() or find_tmux() is None:
        pytest.skip("sem claude ou sem tmux")
    root = tmp_path_factory.mktemp("projetos")
    socket = f"jt-real-{secrets.token_hex(3)}"
    tmux = Tmux(socket=socket, conf=REPO / "jarvis/tmux.conf")
    terminals = Terminals(path=root / "events.jsonl")
    control = TerminalControl(tmux, terminals, Permissions(), Folders([root]), memory=lambda: 50)
    alerts: list[dict] = []

    async def broadcast(ev):
        if ev.type == "terminal_alert":
            alerts.append(ev.data)

    control.broadcast = broadcast
    token = secrets.token_urlsafe(16)
    hooks = HookServer(lambda tk: "jarvis" if tk == token else None, control.on_hook)
    async with hooks.run() as port:
        session = root / "session.json"
        session.write_text(json.dumps({"port": 1, "token": token, "hook_port": port}))
        settings = root / "settings.json"
        hook = f'/usr/bin/python3 "{REPO}/jarvis/hooks/claude_permission.py" 2>/dev/null || true'
        settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PermissionRequest": [
                            {"hooks": [{"type": "command", "command": hook, "timeout": 600}]}
                        ]
                    }
                }
            )
        )
        yield control, root, alerts, socket, session, settings
    await control.shutdown()
    await tmux.run("kill-server")


async def screen(control, painel) -> str:
    _, out = await control.tmux.run("capture-pane", "-p", "-t", painel)
    return out


async def start_claude(control, root, name, socket, session, settings, hook_port_override=None):
    (root / name).mkdir()
    result = await control.open(name)
    t = control.terminals.by_key(f"tmux:{result['sessao']}")
    await asyncio.sleep(1.0)
    if hook_port_override is not None:
        session.write_text(
            json.dumps({**json.loads(session.read_text()), "hook_port": hook_port_override})
        )
    await control.tmux.send_command(
        t.painel,
        f"JARVIS_TMUX_SOCKET={socket} JARVIS_SESSION_FILE='{session}' {CLAUDE} "
        f"--model claude-haiku-5-5 --permission-mode default --settings '{settings}'",
    )
    for _ in range(80):  # pergunta de confiança da pasta nova ("No, exit" vem marcado)
        text = await screen(control, t.painel)
        if "Enter to confirm" in text:
            await asyncio.sleep(2)
            await control.tmux.run("send-keys", "-t", t.painel, "Down")
            await asyncio.sleep(0.5)
            await control.tmux.run("send-keys", "-t", t.painel, "Enter")
        if "manual mode" in text:
            break
        await asyncio.sleep(0.5)
    assert "manual mode" in await screen(control, t.painel)
    return t


async def ask_touch(control, t, alerts, arquivo):
    n = len(alerts)
    await control.tmux.send_message(t.painel, f"Use the Bash tool to run exactly: touch {arquivo}")
    await wait_for(lambda: len(alerts) > n, 90)
    return alerts[-1]


async def test_permitir_e_negar_pelo_jarvis(env):
    control, root, alerts, socket, session, settings = env
    t = await start_claude(control, root, "p1", socket, session, settings)
    alert = await ask_touch(control, t, alerts, "a.txt")
    assert alert["chave"] == t.chave and "touch a.txt" in alert["resumo"]
    await control.permissions.resolve(alert["pedido"], "permitido")
    await wait_for(lambda: (root / "p1/a.txt").exists(), 60)
    alert = await ask_touch(control, t, alerts, "b.txt")
    await control.permissions.resolve(alert["pedido"], "negado")
    for _ in range(60):
        if "Kaio negou" in await screen(control, t.painel) or "Denied" in await screen(
            control, t.painel
        ):
            break
        await asyncio.sleep(1)
    assert not (root / "p1/b.txt").exists()


async def test_resposta_na_aba_vence(env):
    control, root, alerts, socket, session, settings = env
    t = await start_claude(control, root, "p2", socket, session, settings)
    panel = FakeClient()
    await control.handle(panel, {"type": "term_attach", "sessao": t.tmux})
    alert = await ask_touch(control, t, alerts, "c.txt")
    await asyncio.sleep(1.5)
    await control.handle(panel, {"type": "term_input", "sessao": t.tmux, "data": "1"})
    await wait_for(lambda: (root / "p2/c.txt").exists(), 60)
    assert control.permissions.pending_for(t.chave) is None
    assert not await control.permissions.resolve(alert["pedido"], "negado")  # já respondido


async def test_cerebro_fora_o_dialogo_segue(env):
    control, root, alerts, socket, session, settings = env
    t = await start_claude(control, root, "p3", socket, session, settings, hook_port_override=9)
    await control.tmux.send_message(t.painel, "Use the Bash tool to run exactly: touch d.txt")
    for _ in range(90):
        if "Do you want to proceed" in await screen(control, t.painel):
            break
        await asyncio.sleep(1)
    assert not alerts
    await control.tmux.run("send-keys", "-t", t.painel, "1")
    await wait_for(lambda: (root / "p3/d.txt").exists(), 60)
