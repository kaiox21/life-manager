"""Sobe o cérebro do Jarvis: uv run python -m jarvis

Lê o mesmo .env do núcleo (modelos, gateway, MCP_TOKEN). JARVIS_CORE_URL troca o endereço
do núcleo (padrão: o Docker local; depois do VPS, o host do Tailscale).
"""

import asyncio
import logging
import os

from app.agent.llm import GatewayLLM
from app.config import get_settings, provider_list
from jarvis.agent import JarvisBrain
from jarvis.local_tools import LocalTools
from jarvis.mcp_client import CoreClient
from jarvis.server import JarvisServer


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    s = get_settings()
    llm = GatewayLLM(
        api_key=s.ai_gateway_api_key.get_secret_value(),
        base_url=s.ai_gateway_base_url,
        allowed_providers=provider_list(s.allowed_providers),
        reasoning_effort=s.reasoning_effort,
    )
    url = os.environ.get("JARVIS_CORE_URL", "http://localhost:8000/mcp/")
    async with CoreClient.connect(url, s.mcp_token.get_secret_value()) as core:
        brain = JarvisBrain(
            llm,
            core,
            LocalTools(),
            primary=os.environ.get("JARVIS_MODEL_PRIMARY", s.model_primary),
            escalation=os.environ.get("JARVIS_MODEL_ESCALATION", s.model_escalation),
        )
        async with JarvisServer(brain).run(port=int(os.environ.get("JARVIS_PORT", "0"))):
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
