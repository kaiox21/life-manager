import json

import httpx

from app.channel.evolution import EvolutionClient
from app.types import OutgoingMessage
from tests.conftest import OWNER


async def test_send_text_monta_requisicao(settings):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"key": {"id": "BAE5ABC", "fromMe": True}})

    client = EvolutionClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    # Mesmo vindo sem o nono dígito, o envio vai para o OWNER_PHONE configurado.
    wa_id = await client.send_text(OutgoingMessage(to="556199998888", text="oi"))

    assert wa_id == "BAE5ABC"
    (req,) = seen
    assert str(req.url) == "http://evolution.test:8080/message/sendText/assistente"
    assert req.headers["apikey"] == "chave-de-teste"
    assert json.loads(req.content) == {"number": OWNER, "text": "oi"}


async def test_create_instance_leva_header_secreto(settings):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"instance": {"instanceName": "assistente"}})

    client = EvolutionClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await client.create_instance()

    body = json.loads(seen[0].content)
    assert body["integration"] == "WHATSAPP-BAILEYS"
    assert body["webhook"]["url"] == "http://app:8000/webhook/evolution"
    assert body["webhook"]["headers"] == {"X-Webhook-Secret": "segredo-de-teste"}
    assert "MESSAGES_UPSERT" in body["webhook"]["events"]
