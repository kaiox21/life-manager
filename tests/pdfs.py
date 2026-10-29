"""PDFs fictícios para os testes da fatura (o repositório é público: nada de fatura real)."""

import io

from pypdf import PdfWriter


def text_pdf(lines: list[str]) -> bytes:
    """PDF de uma página com as linhas em Helvetica, montado à mão (texto extraível)."""

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    body = "BT /F1 10 Tf 14 TL 40 800 Td " + " ".join(f"({esc(line)}) Tj T*" for line in lines)
    stream = (body + " ET").encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for n, obj in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % n + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    )
    return out.getvalue()


def blank_pdf() -> bytes:
    """Página sem texto (como um PDF escaneado)."""
    w = PdfWriter()
    w.add_blank_page(595, 842)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def encrypted_pdf(lines: list[str]) -> bytes:
    from pypdf import PdfReader

    w = PdfWriter(clone_from=PdfReader(io.BytesIO(text_pdf(lines))))
    w.encrypt("12345")
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


FATURA_FICTICIA = [
    "Banco Ficticio - Fatura do cartao final 5162 9012 3456 7890",
    "Vencimento: 08/11/2026          Total a pagar: R$ 1.307,40",
    "Fatura anterior R$ 900,00   Pagamento recebido -R$ 900,00",
    "16 OUT   RESTAURANTE X                         47,90",
    "18 OUT   LOJA Y PARCELA 03/10                 120,00",
    "20 OUT   MERCADO Z                          1.234,56",
    "21 OUT   ESTORNO MERCADO Z                    -95,06",
    "22 OUT   IOF COMPRA INTERNACIONAL               0,00",
] + [f"linha de preenchimento {i}" for i in range(10)]
