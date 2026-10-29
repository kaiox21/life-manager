"""Fatura em PDF pelo WhatsApp: parsing do documento e o fluxo pelo webhook (LLM falso)."""

import base64
import copy

import httpx
from sqlalchemy import select

from app.channel.evolution import parse_webhook
from app.clock import fixed_clock
from app.db.models import Expense, Message, PendingAction
from app.main import create_app
from tests.conftest import NOW, SECRET, FakeSender, load_payload
from tests.fakes import ScriptedLLM, call
from tests.pdfs import FATURA_FICTICIA, text_pdf
from tests.unit.test_statement_import import TRANSCRICAO

PDF_B64 = base64.b64encode(text_pdf(FATURA_FICTICIA)).decode()


def _doc_payload(wid: str, caption: str | None = "nubank", mimetype="application/pdf", b64=PDF_B64):  # noqa: ANN001
    p = copy.deepcopy(load_payload("image_owner.json"))
    p["data"]["key"]["id"] = wid
    doc = {"mimetype": mimetype, "fileName": "fatura.pdf", "mediaKey": "FAKEKEY"}
    if caption is None:
        p["data"]["message"] = {"documentMessage": doc}
    else:
        p["data"]["message"] = {
            "documentWithCaptionMessage": {
                "message": {"documentMessage": {**doc, "caption": caption}}
            }
        }
    if b64:
        p["data"]["message"]["base64"] = b64
    p["data"]["messageType"] = "documentMessage"
    return p


def _text(wid: str, text: str) -> dict:
    p = load_payload("text_owner.json")
    p["data"]["key"]["id"] = wid
    p["data"]["message"] = {"conversation": text}
    return p


async def _post(app, payload) -> httpx.Response:  # noqa: ANN001
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as c:
        return await c.post(
            "/webhook/evolution", json=payload, headers={"X-Webhook-Secret": SECRET}
        )


def test_parse_pdf_com_e_sem_legenda() -> None:
    with_caption = parse_webhook(_doc_payload("D1"))
    assert with_caption is not None and with_caption.type == "document"
    assert with_caption.text == "nubank"
    assert with_caption.media is not None and with_caption.media.mimetype == "application/pdf"
    assert with_caption.media.data_b64 == PDF_B64
    bare = parse_webhook(_doc_payload("D2", caption=None, b64=None))
    assert bare is not None and bare.type == "document" and bare.text is None
    assert bare.media is not None and bare.media.data_b64 is None
    assert bare.media.ref["message"]["documentMessage"]["mediaKey"] == "FAKEKEY"


def test_planilha_e_ignorada() -> None:
    xlsx = parse_webhook(
        _doc_payload(
            "D3", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    )
    assert xlsx is not None and xlsx.type == "other" and xlsx.media is None


async def test_fatura_pelo_whatsapp_resumo_e_sim(settings, seeded) -> None:  # noqa: ANN001
    sender = FakeSender()
    llm = ScriptedLLM(call("registrar_fatura", TRANSCRICAO))
    app = create_app(settings, sessions=seeded, sender=sender, llm=llm, clock=fixed_clock(NOW))
    resp = await _post(app, _doc_payload("DOC0001"))
    assert resp.json() == {"status": "accepted"}
    assert "Fatura do Nubank (vence 08/11/2026)" in sender.sent[-1].text
    assert sender.sent[-1].text.endswith("Lanço os 4? (sim/não)")
    async with seeded() as s:
        assert (await s.scalars(select(Expense))).all() == []
        msg = await s.scalar(select(Message).where(Message.wa_message_id == "DOC0001"))
        assert msg is not None and msg.body == "nubank" and msg.media_path is None

    await _post(app, _text("DOC0002", "sim"))
    assert sender.sent[-1].text.startswith("Lancei 4 gastos da fatura do Nubank")
    async with seeded() as s:
        assert len((await s.scalars(select(Expense))).all()) == 11


async def test_pdf_sem_base64_baixa_de_novo(settings, seeded) -> None:  # noqa: ANN001
    sender = FakeSender(media_b64=PDF_B64)
    llm = ScriptedLLM(call("registrar_fatura", TRANSCRICAO))
    app = create_app(settings, sessions=seeded, sender=sender, llm=llm, clock=fixed_clock(NOW))
    await _post(app, _doc_payload("DOC0003", b64=None))
    assert len(sender.fetched) == 1
    assert "Fatura do Nubank" in sender.sent[-1].text


async def test_pdf_grande_demais_recusado(settings, seeded) -> None:  # noqa: ANN001
    sender = FakeSender()
    app = create_app(
        settings, sessions=seeded, sender=sender, llm=ScriptedLLM(), clock=fixed_clock(NOW)
    )
    big = base64.b64encode(b"%PDF" + b"0" * (10 * 1024 * 1024 + 10)).decode()
    await _post(app, _doc_payload("DOC0004", b64=big))
    assert sender.sent[-1].text.startswith("PDF grande demais")


async def test_cartao_desconhecido_pede_legenda(settings, seeded) -> None:  # noqa: ANN001
    sender = FakeSender()
    llm = ScriptedLLM(call("registrar_fatura", TRANSCRICAO))
    app = create_app(settings, sessions=seeded, sender=sender, llm=llm, clock=fixed_clock(NOW))
    await _post(app, _doc_payload("DOC0005", caption="fatura de outubro"))
    text = sender.sent[-1].text
    assert "Não sei de qual cartão" in text or "não cadastrado" in text
    assert "legenda" in text
    async with seeded() as s:
        assert (await s.scalars(select(PendingAction))).all() == []
