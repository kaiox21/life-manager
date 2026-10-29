"""Jarvis: importar_fatura (lê o PDF local e entrega ao núcleo) e os cartões do conselho."""

import base64
import json
import os
import time
from datetime import datetime
from pathlib import Path

from jarvis.agent import HIDDEN_CORE_TOOLS, JarvisBrain
from jarvis.cards import card_for
from jarvis.local_tools import ImportarFaturaArgs, LocalTools
from jarvis.mcp_client import ToolResult
from tests.fakes import ScriptedLLM, call, reply
from tests.jarvis.test_agent import CORE_TOOLS, FakeCore, Runner, _ask

PDF = b"%PDF-1.4 fatura ficticia"


def _tools(home: Path, now: datetime | None = None) -> LocalTools:
    return LocalTools(runner=Runner(), config={}, home=home, now=lambda: now or datetime.now())


def _write(path: Path, data: bytes = PDF, age_days: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    t = time.time() - age_days * 86400
    os.utime(path, (t, t))
    return path


async def test_arquivo_na_pasta_pessoal_vai_ao_nucleo(tmp_path: Path) -> None:
    _write(tmp_path / "Downloads" / "fatura nubank.pdf")
    r = await _tools(tmp_path).importar_fatura(
        ImportarFaturaArgs(arquivo="~/Downloads/fatura nubank.pdf", cartao="nubank")
    )
    assert r["_core"] == "importar_fatura_pdf"
    assert base64.b64decode(r["_core_args"]["pdf_base64"]) == PDF
    assert r["_core_args"]["cartao"] == "nubank"
    assert r["arquivo"] == "~/Downloads/fatura nubank.pdf"


async def test_sem_arquivo_usa_o_pdf_mais_novo_de_downloads(tmp_path: Path) -> None:
    _write(tmp_path / "Downloads" / "velha.pdf", age_days=3)
    _write(tmp_path / "Downloads" / "nova.pdf", b"%PDF nova", age_days=1)
    _write(tmp_path / "Downloads" / "antiga.pdf", age_days=10)
    _write(tmp_path / "Downloads" / "foto.png", age_days=0)
    r = await _tools(tmp_path).importar_fatura(ImportarFaturaArgs())
    assert r["arquivo"] == "~/Downloads/nova.pdf"


async def test_nada_recente_em_downloads(tmp_path: Path) -> None:
    _write(tmp_path / "Downloads" / "antiga.pdf", age_days=10)
    r = await _tools(tmp_path).importar_fatura(ImportarFaturaArgs())
    assert "Não achei PDF em Downloads" in r["erro"]


async def test_fora_da_pasta_pessoal_recusa(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    outside = _write(tmp_path / "outro" / "x.pdf")
    tools = _tools(home)
    for arquivo in ("/etc/passwd", str(outside), "~/../outro/x.pdf"):
        r = await tools.importar_fatura(ImportarFaturaArgs(arquivo=arquivo))
        assert r["erro"] == "Só leio faturas dentro da sua pasta pessoal.", arquivo
    link = home / "link.pdf"
    link.symlink_to(outside)
    r = await tools.importar_fatura(ImportarFaturaArgs(arquivo="~/link.pdf"))
    assert "pasta pessoal" in r["erro"]


async def test_nao_pdf_e_grande_demais(tmp_path: Path) -> None:
    _write(tmp_path / "planilha.xlsx")
    tools = _tools(tmp_path)
    r = await tools.importar_fatura(ImportarFaturaArgs(arquivo="~/planilha.xlsx"))
    assert "não é um PDF" in r["erro"]
    big = tmp_path / "grande.pdf"
    big.write_bytes(b"%PDF" + b"0" * (10 * 1024 * 1024 + 1))
    r = await tools.importar_fatura(ImportarFaturaArgs(arquivo="~/grande.pdf"))
    assert "grande demais" in r["erro"]
    assert big.exists()  # nunca apaga


def test_marcas_internas_nao_voltam_ao_modelo(tmp_path: Path) -> None:
    data = {
        "arquivo": "~/x.pdf",
        "_core": "importar_fatura_pdf",
        "_core_args": {"pdf_base64": "AA"},
    }
    assert _tools(tmp_path).for_model("importar_fatura", data) == {"arquivo": "~/x.pdf"}


async def test_fatura_pelo_jarvis_confirma_na_tela(tmp_path: Path) -> None:
    _write(tmp_path / "Downloads" / "fatura.pdf")
    pend = {
        "status": "aguardando_confirmacao",
        "pending_id": "pf",
        "resumo": "Fatura do Nubank (vence 08/11/2026): 5 itens.\nLanço os 4? (sim/não)",
    }
    core = FakeCore(
        {
            "importar_fatura_pdf": ToolResult(True, pend),
            "confirmar_pendente": lambda a: ToolResult(
                True, {"status": "fatura_gravada", "resumo": "Lancei 4 gastos da fatura do Nubank."}
            ),
        }
    )
    local = _tools(tmp_path)
    b = JarvisBrain(
        ScriptedLLM(call("importar_fatura", {"cartao": "nubank"}), reply("Feito, senhor.")),
        core,
        local,
        primary="fake/p",
        escalation="fake/e",
    )
    evs = await _ask(b, "lê a fatura do nubank que eu baixei", answers=[True])
    (conf,) = [e for e in evs if e.type == "confirm"]
    assert conf.text.startswith("Fatura do Nubank")
    name, args = core.calls[1]
    assert name == "importar_fatura_pdf" and args["cartao"] == "nubank"
    assert ("confirmar_pendente", {"pending_id": "pf", "decisao": "sim"}) in core.calls
    (card,) = [e.card for e in evs if e.type == "card"]
    assert card["title"] == "Fatura importada"


def test_ferramenta_do_pdf_fica_escondida_do_modelo() -> None:
    assert "importar_fatura_pdf" in HIDDEN_CORE_TOOLS
    assert "importar_fatura_pdf" not in CORE_TOOLS


def test_cartao_do_conselho() -> None:
    data = {
        "veredito": "atenção",
        "compra": "R$ 400,00 em 4x no Nubank",
        "texto": "11/2026: ... = sobra R$ 600,00 (17%)",
        "aviso": "Média calculada com 1 mês(es) de histórico.",
    }
    card = card_for("avaliar_compra", {}, data)
    assert card == {
        "kind": "texto",
        "title": "Conselho · R$ 400,00 em 4x no Nubank · atenção",
        "text": "11/2026: ... = sobra R$ 600,00 (17%)\nMédia calculada com 1 mês(es) de histórico.",
    }
    renda = card_for(
        "gerenciar_renda",
        {},
        {"resumo": "Renda: Salário, R$ 3.500,00 todo dia 5", "renda_mensal": "R$ 3.500,00",
         "contas_fixas_mensal": "R$ 0,00"},
    )  # fmt: skip
    assert renda is not None and renda["title"] == "Orçamento"
    erro = card_for("avaliar_compra", {}, {"erro": "Sem renda cadastrada", "falta": "renda"})
    assert erro is not None and erro["title"] == "Atenção"
    assert json.dumps(card)
