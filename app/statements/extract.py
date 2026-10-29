"""Texto do PDF da fatura, extraído no núcleo (sem OCR) e com o número do cartão mascarado."""

import io
import logging
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

log = logging.getLogger(__name__)

MAX_PDF_BYTES = 10 * 1024 * 1024
MIN_TEXT_CHARS = 200  # menos que isso: PDF escaneado (só imagem)

# 13 a 19 dígitos, com ou sem espaço, ponto ou hífen entre os grupos.
_CARD = re.compile(r"(?<!\d)(?:\d[ .-]?){12,18}\d(?!\d)")


class StatementRefused(Exception):
    """PDF que não dá para ler: a mensagem vai ao usuário."""


def mask_card_numbers(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m[0])
        return "****" + digits[-4:]

    return _CARD.sub(repl, text)


def extract_pages(pdf: bytes) -> list[str]:
    """Texto de cada página (modo layout: fatura é tabela), já mascarado."""
    if len(pdf) > MAX_PDF_BYTES:
        raise StatementRefused("PDF grande demais (máx. 10 MB).")
    if not pdf.startswith(b"%PDF"):
        raise StatementRefused(
            "Esse arquivo não é um PDF. Mande o PDF da fatura exportado pelo app do banco."
        )
    try:
        reader = PdfReader(io.BytesIO(pdf))
        if reader.is_encrypted:
            raise StatementRefused(
                "Esse PDF tem senha. Exporte a fatura sem senha no app do banco e mande de novo."
            )
        pages = [p.extract_text(extraction_mode="layout") or "" for p in reader.pages]
    except StatementRefused:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        log.info("PDF ilegível: %s", exc.__class__.__name__)
        raise StatementRefused(
            "Não consegui abrir esse PDF. Pode exportar a fatura de novo?"
        ) from exc
    if sum(len(p.strip()) for p in pages) < MIN_TEXT_CHARS:
        raise StatementRefused(
            "Esse PDF parece escaneado (sem texto). Preciso do PDF da fatura exportado pelo app "
            "do banco."
        )
    return [mask_card_numbers(p) for p in pages]
