import asyncio

import httpx
from sqlalchemy import select

from app.db.models import Message
from app.main import create_app
from tests.conftest import OWNER, SECRET, load_payload
from tests.fakes import ScriptedLLM


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t")


async def _post(c: httpx.AsyncClient, fixture: str) -> httpx.Response:
    return await c.post(
        "/webhook/evolution", json=load_payload(fixture), headers={"X-Webhook-Secret": SECRET}
    )


async def _rows(sessions) -> list[Message]:
    async with sessions() as s:
        return list((await s.scalars(select(Message).order_by(Message.created_at))).all())


async def test_dono_recebe_resposta_do_agente(settings, sender, sessions):
    app = create_app(settings, sessions=sessions, sender=sender, llm=ScriptedLLM())
    async with _client(app) as c:
        resp = await _post(c, "text_owner.json")
    assert resp.json() == {"status": "accepted"}
    assert [(m.to, m.text) for m in sender.sent] == [(OWNER, "Oi!")]
    rows = await _rows(sessions)
    assert [(r.direction, r.body, r.wa_message_id) for r in rows] == [
        ("in", "oi", "3EB0A1B2C3D4E5F60001"),
        ("out", "Oi!", "BOT0001"),
    ]


async def test_webhook_repetido_responde_uma_vez(settings, sender, sessions):
    app = create_app(settings, sessions=sessions, sender=sender, llm=ScriptedLLM())
    async with _client(app) as c:
        first = await _post(c, "text_owner.json")
        second = await _post(c, "text_owner.json")
    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "ignored", "reason": "duplicate"}
    assert len(sender.sent) == 1
    assert [r.direction for r in await _rows(sessions)] == ["in", "out"]


async def test_webhooks_simultaneos_respondem_uma_vez(settings, sender, sessions):
    app = create_app(settings, sessions=sessions, sender=sender, llm=ScriptedLLM())
    async with _client(app) as c:
        results = await asyncio.gather(*[_post(c, "text_owner.json") for _ in range(5)])
    assert sorted(r.json()["status"] for r in results) == ["accepted"] + ["ignored"] * 4
    assert len(sender.sent) == 1


async def test_variantes_do_dono_tambem_respondem(settings, sender, sessions):
    app = create_app(settings, sessions=sessions, sender=sender, llm=ScriptedLLM())
    async with _client(app) as c:
        for fixture in ("text_owner_without_ninth_digit.json", "text_owner_lid.json"):
            assert (await _post(c, fixture)).json() == {"status": "accepted"}
    assert len(sender.sent) == 2


async def test_outro_numero_nao_grava_nada(settings, sender, sessions):
    app = create_app(settings, sessions=sessions, sender=sender, llm=ScriptedLLM())
    async with _client(app) as c:
        await _post(c, "text_stranger.json")
    assert await _rows(sessions) == []
    assert sender.sent == []
