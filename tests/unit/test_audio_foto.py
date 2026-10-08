"""Fase 4: áudio e foto pelo webhook, com transcrição e LLM falsos (sem rede)."""

import httpx
from sqlalchemy import select

from app.channel.evolution import parse_webhook
from app.clock import fixed_clock
from app.db.models import AgentRun, Expense, Message, PendingAction
from app.integrations.transcribe import Transcription
from app.main import create_app
from tests.conftest import NOW, SECRET, FakeSender, load_payload
from tests.fakes import ScriptedLLM, call, reply


def cls(intent: str):
    return call("classificar", {"intencao": intent})


class FakeTranscriber:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[bytes] = []

    async def transcribe(self, audio: bytes, hints=None) -> Transcription:
        self.calls.append(audio)
        self.hints = hints
        return Transcription(text=self.text, model="fake/whisper", elapsed_ms=12)


def _text_payload(wid: str, text: str) -> dict:
    p = load_payload("text_owner.json")
    p["data"]["key"]["id"] = wid
    p["data"]["message"] = {"conversation": text}
    return p


async def _post(app, payload) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as c:
        return await c.post(
            "/webhook/evolution", json=payload, headers={"X-Webhook-Secret": SECRET}
        )


def _app(settings, seeded, sender, llm, transcriber=None):
    return create_app(
        settings,
        sessions=seeded,
        sender=sender,
        llm=llm,
        clock=fixed_clock(NOW),
        transcriber=transcriber,
    )


async def _all(seeded, model):
    async with seeded() as s:
        return list((await s.scalars(select(model))).all())


def test_parse_midia():
    audio = parse_webhook(load_payload("audio_owner.json"))
    assert audio.media.mimetype == "audio/ogg"
    assert audio.media.seconds == 4
    assert audio.media.data_b64 == "T2dnUw=="
    assert "base64" not in audio.media.ref["message"]
    img = parse_webhook(load_payload("image_owner_no_base64.json"))
    assert img.type == "image" and img.text == "mercado"
    assert img.media.data_b64 is None
    assert img.media.ref["message"]["imageMessage"]["mediaKey"] == "FAKEKEY"


async def test_audio_de_gasto_pede_confirmacao_e_grava_no_sim(settings, seeded):
    sender = FakeSender()
    whisper = FakeTranscriber("paguei 120 de gasolina no pix")
    gas = {
        "amount_cents": 12000,
        "description": "gasolina",
        "payment_method": "pix",
        "category": "Transporte",
    }
    llm = ScriptedLLM(
        cls("gasto"), call("lancar_gasto", gas), reply("R$ 120,00 no Pix — gasolina. Confirma?")
    )
    app = _app(settings, seeded, sender, llm, whisper)

    assert (await _post(app, load_payload("audio_owner.json"))).json()["status"] == "accepted"
    assert whisper.calls == [b"OggS"]
    assert "Nubank" in whisper.hints and "Mariana" in whisper.hints
    assert (
        sender.sent[-1].text
        == '🎙️ "paguei 120 de gasolina no pix"\nR$ 120,00 no Pix — gasolina. Confirma?'
    )
    assert await _all(seeded, Expense) == []
    (pending,) = await _all(seeded, PendingAction)
    assert pending.status == "pending"
    msgs = await _all(seeded, Message)
    assert any(m.type == "audio" and m.body == "paguei 120 de gasolina no pix" for m in msgs)
    (run,) = await _all(seeded, AgentRun)
    assert [t["name"] for t in run.tools_called] == ["transcricao", "lancar_gasto"]

    await _post(app, _text_payload("SIM0001", "sim"))
    (exp,) = await _all(seeded, Expense)
    assert exp.amount_cents == 12000 and exp.source == "audio"
    assert sender.sent[-1].text.startswith("Gravado: R$ 120,00")


async def test_foto_vai_como_imagem_ao_grupo_gasto_e_vira_pendencia(settings, seeded):
    sender = FakeSender()
    recibo = {
        "amount_cents": 8790,
        "description": "compras",
        "merchant": "Pão de Açúcar",
        "payment_method": "nubank",
        "category": "Mercado",
        "spent_on": "2026-10-06",
    }
    llm = ScriptedLLM(call("lancar_gasto", recibo), reply("R$ 87,90 no Nubank. Confirma?"))
    app = _app(settings, seeded, sender, llm)

    await _post(app, load_payload("image_owner.json"))
    first = llm.calls[0]
    assert {t["function"]["name"] for t in first["tools"]} == {
        "lancar_gasto",
        "desfazer_ultimo",
        "gerenciar_meio_pagamento",
    }
    content = first["messages"][-1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,iVBOR")
    assert await _all(seeded, Expense) == []
    (pending,) = await _all(seeded, PendingAction)
    assert pending.args["merchant"] == "Pão de Açúcar"
    (run,) = await _all(seeded, AgentRun)
    assert run.intent == "gasto"


async def test_resposta_a_pergunta_sobre_foto_continua_exigindo_confirmacao(settings, seeded):
    sender = FakeSender()
    recibo = {"amount_cents": 4500, "description": "farmácia", "payment_method": "nubank"}
    llm = ScriptedLLM(
        reply("Li R$ 45,00 na Drogasil. Qual cartão?"),  # foto: pergunta o meio
        cls("gasto"),
        call("lancar_gasto", recibo),
        reply("Confirma?"),  # "nubank"
    )
    app = _app(settings, seeded, sender, llm)
    await _post(app, load_payload("image_owner.json"))
    await _post(app, _text_payload("TXT0001", "nubank"))
    assert await _all(seeded, Expense) == []  # não gravou direto
    (pending,) = await _all(seeded, PendingAction)
    assert pending.status == "pending"


async def test_texto_comum_nao_herda_origem(settings, seeded):
    sender = FakeSender()
    gasto = {"amount_cents": 4790, "description": "almoço", "payment_method": "nubank"}
    llm = ScriptedLLM(cls("gasto"), call("lancar_gasto", gasto), reply("Gravado."))
    app = _app(settings, seeded, sender, llm)
    await _post(app, _text_payload("TXT0002", "almoço 47,90 nubank"))
    (exp,) = await _all(seeded, Expense)
    assert exp.source == "texto"


async def test_foto_sem_base64_busca_pelo_canal(settings, seeded):
    sender = FakeSender(media_b64="iVBORw0KGgo=")
    llm = ScriptedLLM(reply("Isso não parece um recibo."))
    app = _app(settings, seeded, sender, llm)
    await _post(app, load_payload("image_owner_no_base64.json"))
    assert len(sender.fetched) == 1
    assert llm.calls[0]["messages"][-1]["content"][0]["text"] == "mercado"


async def test_foto_que_nao_baixa_responde_sem_llm(settings, seeded):
    sender = FakeSender(media_b64=None)
    llm = ScriptedLLM()
    app = _app(settings, seeded, sender, llm)
    await _post(app, load_payload("image_owner_no_base64.json"))
    assert llm.calls == []
    assert "Não consegui baixar" in sender.sent[-1].text


async def test_audio_longo_e_recusado_sem_transcrever(settings, seeded):
    sender = FakeSender()
    whisper = FakeTranscriber("x")
    app = _app(settings, seeded, sender, ScriptedLLM(), whisper)
    await _post(app, load_payload("audio_long_owner.json"))
    assert whisper.calls == []
    assert "longo demais" in sender.sent[-1].text


async def test_audio_vazio_pede_para_repetir(settings, seeded):
    sender = FakeSender()
    app = _app(settings, seeded, sender, ScriptedLLM(), FakeTranscriber(""))
    await _post(app, load_payload("audio_owner.json"))
    assert "Não entendi o áudio" in sender.sent[-1].text
