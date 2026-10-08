"""Modo provisório SELF_CHAT_MODE: bot no próprio número do dono (ver SPEC.md)."""

import httpx
import pytest

from app.main import create_app
from tests.conftest import OWNER, SECRET, load_payload
from tests.fakes import ScriptedLLM


@pytest.fixture
def self_chat_settings(settings):
    return settings.model_copy(update={"self_chat_mode": True})


async def _post(app, fixture: str) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as c:
        return await c.post(
            "/webhook/evolution",
            json=load_payload(fixture),
            headers={"X-Webhook-Secret": SECRET},
        )


async def test_mensagem_para_si_mesmo_responde_com_marca(self_chat_settings, sender, sessions):
    app = create_app(self_chat_settings, sessions=sessions, sender=sender, llm=ScriptedLLM())
    resp = await _post(app, "text_from_me.json")
    assert resp.json() == {"status": "accepted"}
    assert [(m.to, m.text) for m in sender.sent] == [(OWNER, "🤖 Oi!")]


@pytest.mark.parametrize(
    ("fixture", "motivo"),
    [
        ("bot_reply_self_chat.json", "bot_reply"),
        ("text_from_me_to_other.json", "from_me_other_chat"),
        ("text_stranger.json", "not_owner"),
        ("text_group.json", "group_or_broadcast"),
        ("status_broadcast.json", "group_or_broadcast"),
    ],
)
async def test_modo_provisorio_ignora(self_chat_settings, sender, fixture, motivo):
    app = create_app(self_chat_settings, sessions=None, sender=sender)
    resp = await _post(app, fixture)
    assert resp.json() == {"status": "ignored", "reason": motivo}
    assert sender.sent == []


async def test_resposta_do_bot_nao_gera_laco(self_chat_settings, sender, sessions):
    app = create_app(self_chat_settings, sessions=sessions, sender=sender, llm=ScriptedLLM())
    await _post(app, "text_from_me.json")
    await _post(app, "bot_reply_self_chat.json")  # a resposta voltando pelo webhook
    assert len(sender.sent) == 1


async def test_modo_desligado_continua_ignorando_from_me(settings, sender):
    app = create_app(settings, sessions=None, sender=sender)
    resp = await _post(app, "text_from_me.json")
    assert resp.json() == {"status": "ignored", "reason": "from_me"}
