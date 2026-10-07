import httpx
import pytest

from app.main import create_app
from tests.conftest import SECRET, load_payload


@pytest.mark.parametrize("headers", [{}, {"X-Webhook-Secret": "errado"}, {"X-Webhook-Secret": ""}])
async def test_sem_segredo_valido_401(settings, sender, headers):
    app = create_app(settings, sessions=None, sender=sender)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as c:
        resp = await c.post(
            "/webhook/evolution", json=load_payload("text_owner.json"), headers=headers
        )
    assert resp.status_code == 401
    assert sender.sent == []


async def test_segredo_certo_passa_da_autenticacao(settings, sender):
    app = create_app(settings, sessions=None, sender=sender)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as c:
        resp = await c.post(
            "/webhook/evolution",
            json=load_payload("connection_update.json"),
            headers={"X-Webhook-Secret": SECRET},
        )
    assert resp.status_code == 200


async def test_health(settings, sender):
    app = create_app(settings, sessions=None, sender=sender)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as c:
        resp = await c.get("/health")
    assert resp.json() == {"status": "ok"}
