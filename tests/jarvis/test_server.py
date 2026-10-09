import asyncio
import json
import stat

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from jarvis import events
from jarvis.server import JarvisServer, write_session


class EchoBrain:
    def __init__(self) -> None:
        self.confirmations: list[tuple[str, bool]] = []

    async def ask(self, rid, text, emit, mode="texto"):
        await emit(events.step(rid, "pensando…"))
        await emit(events.card(rid, {"kind": "texto", "text": text}))
        await emit(events.done(rid, f"eco: {text}"))

    async def resolve_confirmation(self, confirm_id, accepted):
        self.confirmations.append((confirm_id, accepted))

    async def panel(self, rid, emit):
        await emit(events.panel(rid, {"mes": {"total_centavos": 1}}))


class BrokenBrain(EchoBrain):
    async def ask(self, rid, text, emit, mode="texto"):
        raise RuntimeError("boom")


async def _collect(ws, until="done"):
    out = []
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
        out.append(msg)
        if msg["type"] in (until, "error"):
            return out


async def test_sem_token_e_recusado():
    server = JarvisServer(EchoBrain(), token="certo")
    async with server.run(session_file=None) as port:
        with pytest.raises(InvalidStatus):
            async with connect(f"ws://127.0.0.1:{port}/?token=errado"):
                pass


async def test_pergunta_gera_eventos_em_ordem():
    brain = EchoBrain()
    server = JarvisServer(brain, token="tk")
    async with (
        server.run(session_file=None) as port,
        connect(f"ws://127.0.0.1:{port}/?token=tk") as ws,
    ):
        await ws.send(json.dumps({"type": "ask", "id": "r1", "text": "oi"}))
        msgs = await _collect(ws)
        assert [m["type"] for m in msgs] == ["step", "card", "done"]
        assert msgs[-1] == {"type": "done", "id": "r1", "text": "eco: oi"}
        await ws.send(
            json.dumps({"type": "confirm", "id": "r1", "confirm_id": "c1", "accepted": True})
        )
        await asyncio.sleep(0.05)
    assert brain.confirmations == [("c1", True)]


async def test_falha_do_cerebro_vira_evento_de_erro():
    server = JarvisServer(BrokenBrain(), token="tk")
    async with (
        server.run(session_file=None) as port,
        connect(f"ws://127.0.0.1:{port}/?token=tk") as ws,
    ):
        await ws.send(json.dumps({"type": "ask", "id": "r2", "text": "x"}))
        (msg,) = await _collect(ws)
        assert msg["type"] == "error"


def test_arquivo_de_sessao_so_para_o_dono(tmp_path):
    path = tmp_path / "Jarvis" / "session.json"
    write_session(51234, "segredo", path)
    assert json.loads(path.read_text())["port"] == 51234
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


async def test_painel_responde_com_evento_panel():
    server = JarvisServer(EchoBrain(), token="tk")
    async with (
        server.run(session_file=None) as port,
        connect(f"ws://127.0.0.1:{port}/?token=tk") as ws,
    ):
        await ws.send(json.dumps({"type": "panel", "id": "p1"}))
        (msg,) = await _collect(ws, until="panel")
        assert msg == {"type": "panel", "id": "p1", "data": {"mes": {"total_centavos": 1}}}


async def test_greeting_e_broadcast_chegam_a_todas_as_conexoes():
    server = JarvisServer(EchoBrain(), token="tk")
    server.greeting = lambda: [events.terminals([{"numero": 1}])]
    async with server.run(session_file=None) as port:
        url = f"ws://127.0.0.1:{port}/?token=tk"
        async with connect(url) as a, connect(url) as b:
            for ws in (a, b):
                msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert msg["type"] == "terminals" and msg["data"]["terminais"] == [{"numero": 1}]
            await server.broadcast(events.terminal_alert({"texto": "Terminal 1 terminou"}))
            for ws in (a, b):
                msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert msg == {
                    "type": "terminal_alert",
                    "id": "terminais",
                    "data": {"texto": "Terminal 1 terminou"},
                }


class FakeControl:
    def __init__(self) -> None:
        self.msgs: list[dict] = []
        self.detached = 0

    async def handle(self, client, msg):
        self.msgs.append(msg)
        if msg["type"] == "term_attach":
            await client.send_bytes(b"\x02abcd1234tela")
            await client.emit(events.terminal_tabs([]))

    def detach(self, client):
        self.detached += 1


async def test_mensagens_de_terminal_vao_para_o_controle_e_saida_binaria():
    server = JarvisServer(EchoBrain(), token="tk")
    control = FakeControl()
    server.control = control
    async with (
        server.run(session_file=None) as port,
        connect(f"ws://127.0.0.1:{port}/?token=tk") as ws,
    ):
        await ws.send(json.dumps({"type": "term_attach", "sid": "abcd1234"}))
        assert await asyncio.wait_for(ws.recv(), 5) == b"\x02abcd1234tela"
        assert json.loads(await asyncio.wait_for(ws.recv(), 5))["type"] == "terminal_tabs"
        await ws.send(
            json.dumps({"type": "permission_answer", "pedido": "p", "decisao": "permitir"})
        )
        await ws.send(json.dumps({"type": "ask", "id": "r1", "text": "oi"}))  # o resto segue igual
        msgs = await _collect(ws)
        assert msgs[-1]["type"] == "done"
    await asyncio.sleep(0.05)
    assert [m["type"] for m in control.msgs] == ["term_attach", "permission_answer"]
    assert control.detached == 1


async def test_sem_controle_mensagens_de_terminal_sao_ignoradas():
    server = JarvisServer(EchoBrain(), token="tk")
    async with (
        server.run(session_file=None) as port,
        connect(f"ws://127.0.0.1:{port}/?token=tk") as ws,
    ):
        await ws.send(json.dumps({"type": "term_input", "sid": "x", "data": "rm -rf ~\r"}))
        await ws.send(json.dumps({"type": "ask", "id": "r1", "text": "oi"}))
        msgs = await _collect(ws)
        assert msgs[-1]["type"] == "done"
