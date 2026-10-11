"""Cliente MCP do núcleo: o único caminho do Jarvis para agenda e gastos."""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

log = logging.getLogger(__name__)


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


class CoreUnavailable(Exception):
    """O núcleo (Docker) está fora; o Jarvis segue com o resto (voz, Mac, terminais, música)."""


class ResilientCore:
    """Conexão com o núcleo que vive na própria tarefa e se refaz sozinha.

    Antes, o cérebro inteiro vivia dentro de `CoreClient.connect`: sem o núcleo ele não subia, e
    quando o Docker caía a sessão MCP derrubava o cérebro junto (11/10/2026). Agora a sessão cai
    sozinha, as chamadas levantam `CoreUnavailable` e uma nova tentativa sai a cada `retry` s.
    """

    def __init__(
        self,
        url: str,
        token: str,
        retry: float = 10.0,
        connect: Callable[[str, str], Any] = CoreClient.connect,
    ) -> None:
        self._url, self._token, self._retry, self._connect = url, token, retry, connect
        self._client: CoreClient | None = None
        self._tools: list[dict[str, Any]] = []
        self.ready = asyncio.Event()

    @property
    def online(self) -> bool:
        return self._client is not None

    async def run(self) -> None:
        down_logged = False
        while True:
            try:
                async with self._connect(self._url, self._token) as client:
                    self._client = client
                    with contextlib.suppress(Exception):
                        self._tools = await client.openai_tools()
                    self.ready.set()
                    log.info("núcleo conectado")
                    down_logged = False
                    await asyncio.Event().wait()  # até a sessão cair (o grupo de tarefas cancela)
            except asyncio.CancelledError:
                raise  # o próprio cérebro parando (a queda da sessão chega como ExceptionGroup)
            except Exception as exc:  # noqa: BLE001 (inclui o ExceptionGroup da sessão MCP)
                if not down_logged:
                    log.warning(
                        "núcleo indisponível (%s); tento de novo a cada %.0fs",
                        type(exc).__name__,
                        self._retry,
                    )
                    down_logged = True
            finally:
                self._client = None
                self.ready.clear()
            await asyncio.sleep(self._retry)

    async def openai_tools(self) -> list[dict[str, Any]]:
        # sem o núcleo, as ferramentas dele não são oferecidas ao modelo
        return self._tools if self._client is not None else []

    async def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        client = self._client
        if client is None:
            raise CoreUnavailable("núcleo indisponível")
        return await client.call(name, args)
