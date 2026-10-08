"""Integração com o núcleo rodando no Docker (marcador integracao, fora do padrão).

docker compose up -d && uv run pytest -m integracao
"""

import pytest

from app.config import get_settings
from jarvis.mcp_client import CoreClient

pytestmark = pytest.mark.integracao
URL = "http://localhost:8000/mcp/"


async def test_lista_e_chama_ferramentas_do_nucleo():
    token = get_settings().mcp_token.get_secret_value()
    if not token:
        pytest.skip("MCP_TOKEN não configurado")
    async with CoreClient.connect(URL, token) as core:
        names = {t["function"]["name"] for t in await core.openai_tools()}
        assert {"contexto", "buscar_eventos", "lancar_gasto"} <= names
        ctx = await core.call("contexto", {})
        assert ctx.ok and "Agora:" in ctx.data
        bad = await core.call(
            "total_fatura", {"payment_method": "nubank", "mes_vencimento": "11/2026"}
        )
        assert not bad.ok and "AAAA-MM" in bad.data
