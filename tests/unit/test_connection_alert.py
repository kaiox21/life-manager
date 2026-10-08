import json
from datetime import datetime, timedelta

import httpx

from app.alerts import ConnectionMonitor, NtfyNotifier, heartbeat
from app.channel.evolution import parse_connection_update
from app.clock import TZ
from tests.conftest import load_payload

T0 = datetime(2026, 10, 8, 15, 0, tzinfo=TZ)


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, bool]] = []

    async def notify(self, title: str, message: str, urgent: bool = False) -> None:
        self.sent.append((title, message, urgent))


def test_parse_connection_update():
    assert parse_connection_update(load_payload("connection_update.json")) == "open"
    assert parse_connection_update(load_payload("text_owner.json")) is None
    assert (
        parse_connection_update({"event": "CONNECTION_UPDATE", "data": {"state": "close"}})
        == "close"
    )


async def test_queda_curta_nao_alerta():
    n = FakeNotifier()
    m = ConnectionMonitor(n)
    await m.observe("close", T0)
    await m.observe("connecting", T0 + timedelta(seconds=40))
    await m.observe("open", T0 + timedelta(seconds=50))
    assert n.sent == []


async def test_queda_longa_alerta_uma_vez_e_avisa_a_volta():
    n = FakeNotifier()
    m = ConnectionMonitor(n)
    await m.observe("close", T0)
    await m.observe("close", T0 + timedelta(minutes=1))
    assert n.sent == []
    await m.observe("close", T0 + timedelta(minutes=2))
    await m.observe("close", T0 + timedelta(minutes=3))
    assert [(t, u) for t, _, u in n.sent] == [("WhatsApp fora do ar", True)]
    assert "desde 15:00" in n.sent[0][1]
    await m.observe("open", T0 + timedelta(minutes=10))
    await m.observe("open", T0 + timedelta(minutes=11))
    assert [t for t, _, _ in n.sent] == ["WhatsApp fora do ar", "WhatsApp voltou"]


async def test_evolution_sem_resposta_tambem_alerta():
    n = FakeNotifier()
    m = ConnectionMonitor(n)
    await m.observe(None, T0)
    await m.observe(None, T0 + timedelta(minutes=2))
    assert "Evolution API não responde" in n.sent[0][1]


async def test_falha_no_canal_de_alerta_nao_quebra():
    class Broken:
        async def notify(self, *a, **k):
            raise RuntimeError("ntfy fora")

    m = ConnectionMonitor(Broken())
    await m.observe("close", T0)
    await m.observe("close", T0 + timedelta(minutes=5))  # não levanta


async def test_ntfy_publica_json_com_acentos():
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await NtfyNotifier("https://ntfy.sh/topico-secreto", "tk", http).notify(
        "WhatsApp fora do ar", "Não responde", urgent=True
    )
    (req,) = seen
    assert str(req.url) == "https://ntfy.sh"
    assert req.headers["authorization"] == "Bearer tk"
    body = json.loads(req.content)
    assert body == {
        "topic": "topico-secreto",
        "title": "WhatsApp fora do ar",
        "message": "Não responde",
        "tags": ["warning"],
        "priority": 4,
    }


async def test_heartbeat():
    hits: list[str] = []
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: hits.append(str(r.url)) or httpx.Response(200))
    )
    await heartbeat("https://hc-ping.com/abc", http)
    await heartbeat("", http)
    assert hits == ["https://hc-ping.com/abc"]
