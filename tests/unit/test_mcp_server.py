import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError as McpToolError
from pydantic import SecretStr
from sqlalchemy import select

from app.clock import fixed_clock
from app.db.models import AgentRun, Expense, PendingAction
from app.main import create_app
from app.mcp_server import build_mcp
from tests.conftest import NOW

EXPECTED = {
    "lancar_gasto",
    "desfazer_ultimo",
    "gerenciar_meio_pagamento",
    "buscar_gastos",
    "total_fatura",
    "resumo_gastos",
    "criar_evento",
    "buscar_eventos",
    "atualizar_evento",
    "remover_evento",
    "gerenciar_pessoa",
    "confirmar_pendente",
    "contexto",
    "painel",
}


@pytest.fixture
def server(seeded):
    return build_mcp(get_sessions=lambda: seeded, clock=fixed_clock(NOW))


def _payload(result) -> dict:
    assert not result.is_error, result
    return json.loads(result.content[0].text)


async def _all(seeded, model):
    async with seeded() as s:
        return list((await s.scalars(select(model))).all())


async def test_lista_as_ferramentas_do_nucleo_com_schema(server):
    tools = {t.name: t for t in await server.list_tools()}
    assert set(tools) == EXPECTED
    schema = tools["lancar_gasto"].input_schema
    assert set(schema["required"]) == {"amount_cents", "description", "payment_method"}
    assert "centavos" in schema["properties"]["amount_cents"]["description"]
    assert tools["total_fatura"].description.startswith("Total de uma fatura")


async def test_lancar_gasto_grava_e_registra_canal_desktop(server, seeded):
    out = _payload(
        await server.call_tool(
            "lancar_gasto",
            {
                "amount_cents": 2500,
                "description": "café",
                "payment_method": "débito",
                "category": "Alimentação",
            },
        )
    )
    assert out["status"] == "gravado" and out["meio"] == "Itaú Débito"
    (exp,) = await _all(seeded, Expense)
    assert exp.amount_cents == 2500 and exp.source == "texto"
    (run,) = await _all(seeded, AgentRun)
    assert run.channel == "desktop" and run.tools_called[0]["name"] == "lancar_gasto"


async def test_ferramenta_com_datas(server, seeded):
    # o SDK converte as datas em objetos date antes de chamar a ferramenta
    _payload(
        await server.call_tool(
            "lancar_gasto", {"amount_cents": 1000, "description": "pão", "payment_method": "pix"}
        )
    )
    out = _payload(
        await server.call_tool("buscar_gastos", {"de": "2026-10-07", "ate": "2026-10-07"})
    )
    assert out["total_centavos"] == 1000
    runs = await _all(seeded, AgentRun)
    busca = [r for r in runs if r.tools_called[0]["name"] == "buscar_gastos"]
    assert busca[0].tools_called[0]["args"]["de"] == "2026-10-07"  # gravado como texto ISO


async def test_validacao_do_modelo_original(server, seeded):
    # chamada direta levanta; pelo transporte HTTP vira resultado com is_error e esta mensagem
    with pytest.raises(McpToolError, match="crédito precisa de closing_day"):
        await server.call_tool("gerenciar_meio_pagamento", {"name": "C6", "kind": "credito"})
    (run,) = await _all(seeded, AgentRun)
    assert run.error


async def test_erro_de_dominio_volta_como_resultado(server):
    out = _payload(
        await server.call_tool(
            "lancar_gasto",
            {"amount_cents": 1200, "description": "padaria", "payment_method": "itaú"},
        )
    )
    assert "ambíguo" in out["erro"]


async def test_acima_de_500_e_remocao_pedem_confirmacao(server, seeded):
    out = _payload(
        await server.call_tool(
            "lancar_gasto",
            {"amount_cents": 90000, "description": "jantar", "payment_method": "nubank"},
        )
    )
    assert out["status"] == "aguardando_confirmacao"
    assert await _all(seeded, Expense) == []
    done = _payload(await server.call_tool("confirmar_pendente", {"decisao": "sim"}))
    assert done["status"] == "gravado"
    assert {p.status for p in await _all(seeded, PendingAction)} == {"confirmed"}


async def test_contexto_traz_dados_sem_persona(server):
    result = await server.call_tool("contexto", {})
    text = result.content[0].text
    assert "hoje: quarta 07/10/2026" in text
    assert "Nubank: fatura aberta vence 08/11/2026" in text
    assert "Mariana (irmã)" in text
    assert "WhatsApp" not in text and "Regras:" not in text


async def test_http_exige_token(settings, seeded):
    s = settings.model_copy(update={"mcp_token": SecretStr("tok-123")})
    app = create_app(s, sessions=seeded, sender=None, llm=None)
    transport = httpx.ASGITransport(app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as c:
        assert (await c.post("/mcp/", json={})).status_code == 401
        bad = await c.post("/mcp/", json={}, headers={"Authorization": "Bearer errado"})
        assert bad.status_code == 401
        # o webhook continua com a própria autenticação, sem exigir o token do MCP
        assert (await c.get("/health")).json() == {"status": "ok"}


async def test_sem_token_o_mcp_fica_desligado(settings, seeded):
    app = create_app(settings, sessions=seeded, sender=None, llm=None)
    assert app.state.mcp is None


async def test_painel_so_le_sem_agent_runs_nem_sync(seeded):
    writes = []

    async def after_write() -> None:
        writes.append(1)

    server = build_mcp(get_sessions=lambda: seeded, clock=fixed_clock(NOW), after_write=after_write)
    await server.call_tool(
        "lancar_gasto", {"amount_cents": 4790, "description": "almoço", "payment_method": "nubank"}
    )
    runs_antes, writes_antes = len(await _all(seeded, AgentRun)), len(writes)

    out = _payload(await server.call_tool("painel", {}))
    assert out["mes"]["total_centavos"] == 4790
    assert out["registro"][0]["texto"] == "almoço · R$ 47,90 · Nubank"
    assert out["registro"][0]["origem"] == "mac"
    assert len(await _all(seeded, AgentRun)) == runs_antes
    assert len(writes) == writes_antes
    assert len(await _all(seeded, Expense)) == 1
