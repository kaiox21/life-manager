"""Cliente MCP do núcleo: o único caminho do Jarvis para agenda e gastos."""

import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: dict[str, Any] | str  # JSON da ferramenta, ou texto de erro

    def for_model(self) -> str:
        if self.ok:
            return (
                self.data
                if isinstance(self.data, str)
                else json.dumps(self.data, ensure_ascii=False)
            )
        return json.dumps({"erro_validacao": self.data}, ensure_ascii=False)


class CoreClient:
    """Sessão MCP aberta com o núcleo (use com `async with CoreClient.connect(...)`)."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._tools: list[dict[str, Any]] | None = None

    @classmethod
    @contextlib.asynccontextmanager
    async def connect(cls, url: str, token: str) -> AsyncIterator["CoreClient"]:
        headers = {"Authorization": f"Bearer {token}"}
        async with (
            httpx2.AsyncClient(headers=headers, timeout=60) as http,
            streamable_http_client(url, http_client=http) as streams,
            ClientSession(streams[0], streams[1]) as session,
        ):
            await session.initialize()
            yield cls(session)

    async def openai_tools(self) -> list[dict[str, Any]]:
        """Ferramentas do núcleo no formato de tool calling da API da OpenAI."""
        if self._tools is None:
            listed = (await self._session.list_tools()).tools
            self._tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.input_schema,
                    },
                }
                for t in listed
            ]
        return self._tools

    async def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        result = await self._session.call_tool(name, args)
        text = "".join(getattr(c, "text", "") for c in result.content)
        if result.is_error:
            return ToolResult(False, text)
        try:
            return ToolResult(True, json.loads(text))
        except ValueError:
            return ToolResult(True, text)
