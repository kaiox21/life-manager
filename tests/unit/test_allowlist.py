import httpx
import pytest

from app.channel.evolution import EvolutionClient, ForbiddenDestinationError
from app.main import create_app
from app.security import is_owner, phone_variants
from app.types import OutgoingMessage
from tests.conftest import OWNER, SECRET, load_payload


def test_variantes_do_nono_digito():
    assert phone_variants("5561999998888") == {"5561999998888", "556199998888"}
    assert phone_variants("556199998888") == {"556199998888", "5561999998888"}
    assert phone_variants("+55 (61) 99999-8888") == {"5561999998888", "556199998888"}


@pytest.mark.parametrize("numero", ["5561999998888", "556199998888", "+55 61 99999-8888"])
def test_dono_passa(numero):
    assert is_owner(numero, OWNER)


@pytest.mark.parametrize("numero", ["5511988887777", "5561999998887", "", "61999998888"])
def test_outros_numeros_barrados(numero):
    assert not is_owner(numero, OWNER)


@pytest.mark.parametrize(
    ("fixture", "motivo"),
    [
        ("text_stranger.json", "not_owner"),
        ("text_group.json", "group_or_broadcast"),
        ("status_broadcast.json", "group_or_broadcast"),
        ("text_from_me.json", "from_me"),
        ("video_owner.json", "unsupported_type"),
        ("connection_update.json", "not_a_message"),
    ],
)
async def test_webhook_ignora_sem_responder(settings, sender, fixture, motivo):
    # sessions=None: se o código tentasse gravar, quebraria.
    app = create_app(settings, sessions=None, sender=sender)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as c:
        resp = await c.post(
            "/webhook/evolution",
            json=load_payload(fixture),
            headers={"X-Webhook-Secret": SECRET},
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored", "reason": motivo}
    assert sender.sent == []


async def test_send_text_recusa_outro_destino(settings):
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("não deveria chamar a rede")

    client = EvolutionClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(explode)))
    with pytest.raises(ForbiddenDestinationError):
        await client.send_text(OutgoingMessage(to="5511988887777", text="oi"))
