"""Conexão do WhatsApp morta com o estado "open" (13/10/2026): reinicia, espera e reenvia."""

from datetime import timedelta

import httpx
import pytest

from app.channel.evolution import ConnectionLost, EvolutionClient
from app.types import OutgoingMessage
from tests.conftest import OWNER

CLOSED = httpx.Response(
    428, json={"status": 428, "error": "Precondition Required", "message": "Connection Closed"}
)


def client(settings, replies):
    """`replies`: lista de respostas para os envios; registra todas as chamadas."""
    calls = []
    sends = iter(replies)

    def handler(req):
        calls.append(req.url.path)
        if "/message/sendText/" in req.url.path:
            return next(sends)
        if "/instance/restart/" in req.url.path:
            return httpx.Response(200, json={"status": "ok"})
        if "/instance/connectionState/" in req.url.path:
            return httpx.Response(200, json={"instance": {"state": "open"}})
        return httpx.Response(404)

    c = EvolutionClient(settings, http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    async def nosleep(_s):
        pass

    c._sleep = nosleep
    return c, calls


OK = httpx.Response(201, json={"key": {"id": "MSG1"}})


async def test_conexao_morta_reinicia_e_reenvia(settings):
    c, calls = client(settings, [CLOSED, OK])
    seen = []

    async def on_send(ok):
        seen.append(ok)

    c.on_send = on_send
    assert await c.send_text(OutgoingMessage(to=OWNER, text="oi")) == "MSG1"
    assert [p.split("/")[2] for p in calls] == [
        "sendText",
        "restart",
        "connectionState",
        "sendText",
    ]
    assert seen == [True]  # deu certo na 2ª: o monitor vê conectado


async def test_sessao_perdida_levanta_e_nao_reinicia_em_laco(settings):
    c, calls = client(settings, [CLOSED, CLOSED, CLOSED])
    seen = []

    async def on_send(ok):
        seen.append(ok)

    c.on_send = on_send
    with pytest.raises(ConnectionLost):
        await c.send_text(OutgoingMessage(to=OWNER, text="oi"))
    with pytest.raises(ConnectionLost):  # logo depois: sem novo reinício (5 min)
        await c.send_text(OutgoingMessage(to=OWNER, text="oi"))
    assert sum("/restart/" in p for p in calls) == 1
    assert seen == [False, False]


async def test_outro_erro_nao_reinicia(settings):
    c, calls = client(settings, [httpx.Response(400, json={"message": "número inválido"})])
    with pytest.raises(httpx.HTTPStatusError):
        await c.send_text(OutgoingMessage(to=OWNER, text="oi"))
    assert not any("/restart/" in p for p in calls)


async def test_monitor_alerta_falha_de_envio_mesmo_com_estado_open():
    from datetime import datetime

    from app.alerts import ConnectionMonitor
    from app.clock import TZ

    sent = []

    class Notifier:
        async def notify(self, title, message, urgent=False):
            sent.append(title)

    m = ConnectionMonitor(Notifier())
    t0 = datetime(2026, 10, 13, 10, 40, tzinfo=TZ)
    await m.observe("open", t0)  # a Evolution diz "open"…
    await m.observe_send(False, t0)  # …mas o envio falha
    await m.observe_send(False, t0 + timedelta(minutes=1))
    assert sent == []  # tolerância de 2 min
    await m.observe_send(False, t0 + timedelta(minutes=3))
    assert sent == ["WhatsApp fora do ar"]
    await m.observe_send(True, t0 + timedelta(minutes=4))
    assert sent == ["WhatsApp fora do ar", "WhatsApp voltou"]
