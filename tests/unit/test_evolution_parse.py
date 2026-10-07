from datetime import UTC, datetime

from app.channel.evolution import parse_webhook
from tests.conftest import OWNER, load_payload


def test_texto_simples_do_dono():
    msg = parse_webhook(load_payload("text_owner.json"))
    assert msg is not None
    assert msg.wa_message_id == "3EB0A1B2C3D4E5F60001"
    assert msg.sender == OWNER
    assert msg.type == "text"
    assert msg.text == "oi"
    assert not msg.from_me and not msg.is_group and not msg.is_broadcast
    assert msg.sent_at == datetime.fromtimestamp(1791374400, tz=UTC)


def test_extended_text():
    msg = parse_webhook(load_payload("extended_text_owner.json"))
    assert msg is not None
    assert msg.type == "text"
    assert msg.text == "olha esse link https://exemplo.com"


def test_lid_usa_remote_jid_alt():
    msg = parse_webhook(load_payload("text_owner_lid.json"))
    assert msg is not None
    assert msg.sender == OWNER
    assert msg.chat_jid == f"{OWNER}@s.whatsapp.net"


def test_from_me_marcado():
    msg = parse_webhook(load_payload("text_from_me.json"))
    assert msg is not None and msg.from_me


def test_grupo_marcado_com_participante_como_remetente():
    msg = parse_webhook(load_payload("text_group.json"))
    assert msg is not None
    assert msg.is_group
    assert msg.sender == OWNER


def test_status_marcado_como_broadcast():
    msg = parse_webhook(load_payload("status_broadcast.json"))
    assert msg is not None and msg.is_broadcast


def test_audio_sem_texto():
    msg = parse_webhook(load_payload("audio_owner.json"))
    assert msg is not None
    assert msg.type == "audio"
    assert msg.text is None


def test_outros_eventos_devolvem_none():
    assert parse_webhook(load_payload("connection_update.json")) is None


def test_evento_em_maiusculas_tambem_aceito():
    payload = load_payload("text_owner.json") | {"event": "MESSAGES_UPSERT"}
    assert parse_webhook(payload) is not None


def test_payload_malformado_devolve_none():
    assert parse_webhook({}) is None
    assert parse_webhook({"event": "messages.upsert", "data": []}) is None
    assert parse_webhook({"event": "messages.upsert", "data": {"key": {}}}) is None
