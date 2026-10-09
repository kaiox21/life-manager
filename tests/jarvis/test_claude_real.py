"""Sessão real do Claude Code num pty, com o hook de permissões do Jarvis (tarefa 2.3).

Fora do `pytest` comum: `uv run pytest -m claude tests/jarvis/test_claude_real.py`.
Usa o `claude` instalado e o login dele, com o Haiku e no modo manual (pede permissão para
`touch`). Custa centavos. A tela não é lida: o efeito (arquivo criado ou não) diz o que valeu.
"""

import asyncio
import re
import shutil
from pathlib import Path

import pytest

from jarvis.control import TerminalControl
from jarvis.permissions import HookServer, Permissions
from jarvis.sessions import Folders, Sessions
from jarvis.terminals import Terminals
from tests.jarvis.test_sessions import wait_for

pytestmark = pytest.mark.claude

CLAUDE = Path.home() / ".local/bin/claude"
_ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


def screen(s) -> str:
    return _ANSI.sub(b" ", bytes(s.buffer)).decode(errors="replace")


@pytest.fixture
async def env(tmp_path_factory):
    if not CLAUDE.exists() or shutil.which("zsh") is None:
        pytest.skip("sem o claude instalado")
    root = tmp_path_factory.mktemp("projetos")
    sessions = Sessions(
        Folders([root]),
        claude=str(CLAUDE),
        memory=lambda: 50,
        tabs_file=root / "abas.json",
        claude_args=["--model", "claude-haiku-5-5", "--permission-mode", "default"],
    )
    terminals = Terminals(path=root / "events.jsonl")
    perms = Permissions()
    control = TerminalControl(sessions, terminals, perms)
    alerts: list[dict] = []

    async def broadcast(ev):
        if ev.type == "terminal_alert":
            alerts.append(ev.data)

    control.broadcast = broadcast
    hooks = HookServer(lambda tk: s.sid if (s := sessions.by_token(tk)) else None, perms.handle)
    async with hooks.run() as port:
        control.hook_port = port
        yield control, root, alerts
        for sid in list(sessions.open):
            await sessions.close(sid)


async def start(control, root: Path, name: str):
    (root / name).mkdir()
    result = await control.open(name)
    s = control.sessions.open[result["sid"]]
    await wait_for(lambda: "enter to confirm" in screen(s).lower(), 40)
    # pasta nova: "No, exit" vem marcado; o diálogo só aceita teclas depois de montado
    for _ in range(5):
        await asyncio.sleep(2)
        control.sessions.write(s.sid, b"\x1b[B")
        await asyncio.sleep(0.5)
        control.sessions.write(s.sid, b"\r")
        await asyncio.sleep(3)
        if "manual mode" in screen(s).lower():
            break
    assert "manual mode" in screen(s).lower()
    return s


async def ask_touch(control, s, alerts, arquivo: str) -> dict:
    n = len(alerts)
    await control.sessions.send_text(s.sid, f"Use the Bash tool to run exactly: touch {arquivo}")
    await wait_for(lambda: len(alerts) > n, 90)
    return alerts[-1]


async def test_permitir_e_negar_pelo_jarvis(env):
    control, root, alerts = env
    s = await start(control, root, "p1")
    alert = await ask_touch(control, s, alerts, "a.txt")
    assert alert["aba"] == s.sid and "touch a.txt" in alert["resumo"]
    await control.permissions.resolve(alert["pedido"], "permitido")
    await wait_for(lambda: (root / "p1/a.txt").exists(), 60)

    alert = await ask_touch(control, s, alerts, "b.txt")
    await control.permissions.resolve(alert["pedido"], "negado")
    await wait_for(lambda: "Kaio negou" in screen(s) or "denied" in screen(s).lower(), 60)
    assert not (root / "p1/b.txt").exists()


async def test_resposta_na_aba_vence(env):
    control, root, alerts = env
    s = await start(control, root, "p2")
    alert = await ask_touch(control, s, alerts, "c.txt")
    await asyncio.sleep(1)
    await control.handle(_Client(), {"type": "term_input", "sid": s.sid, "data": "1"})
    await wait_for(lambda: (root / "p2/c.txt").exists(), 60)
    assert control.permissions.pending_for(s.sid) is None
    assert not await control.permissions.resolve(alert["pedido"], "negado")  # já respondido


async def test_cerebro_fora_o_dialogo_segue(env):
    control, root, alerts = env
    control.hook_port = 9  # porta fechada: o hook falha sem bloquear
    s = await start(control, root, "p3")
    await control.sessions.send_text(s.sid, "Use the Bash tool to run exactly: touch d.txt")
    await wait_for(lambda: "proceed" in screen(s).lower(), 90)
    assert not alerts
    control.sessions.write(s.sid, b"1")
    await wait_for(lambda: (root / "p3/d.txt").exists(), 60)


class _Client:
    attached = None
    backlog = 0

    async def emit(self, ev):
        return None

    async def send_bytes(self, data):
        return None
