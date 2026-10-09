"""Pedidos de permissão das sessões abertas pelo Jarvis (hook `PermissionRequest` do tipo http).

Cada sessão recebe pelo `--settings` um hook que faz POST em `http://127.0.0.1:<porta>/permissao`
com `Authorization: Bearer $JARVIS_HOOK_TOKEN` (o token vai no ambiente, não na linha de comando,
que aparece no `ps`). O cérebro segura a requisição até o Kaio clicar Permitir/Negar; se ele
responder na aba (tecla na aba, próximo evento da sessão), ou a sessão acabar, ou passar do
prazo, a resposta é vazia e o diálogo do terminal decide (design, decisão 4). Conferido na
prática em 09/10/2026: o diálogo aparece na tela em paralelo e vale a primeira resposta.

Nunca devolve `updatedPermissions` ("sempre permitir"), `updatedInput` nem `interrupt`.
"""

import asyncio
import contextlib
import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

MAX_BODY = 256 * 1024
MAX_HEADER = 16 * 1024
REQUEST_TIMEOUT = 590.0  # o hook está configurado com 600 s
HOOK_TIMEOUT = 600
DENY_MESSAGE = "O Kaio negou pelo Jarvis."

ALLOW = "permitido"
DENY = "negado"
IN_TAB = "respondido na aba"
EXPIRED = "sem resposta"


def hook_settings(port: int) -> str:
    """JSON do `--settings` das sessões do Jarvis (soma-se aos hooks globais)."""
    return json.dumps(
        {
            "hooks": {
                "PermissionRequest": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "http",
                                "url": f"http://127.0.0.1:{port}/permissao",
                                "headers": {"Authorization": "Bearer $JARVIS_HOOK_TOKEN"},
                                "allowedEnvVars": ["JARVIS_HOOK_TOKEN"],
                                "timeout": HOOK_TIMEOUT,
                            }
                        ],
                    }
                ]
            }
        },
        separators=(",", ":"),
    )


def decision(result: str) -> dict[str, Any]:
    if result == ALLOW:
        behavior: dict[str, Any] = {"behavior": "allow"}
    elif result == DENY:
        behavior = {"behavior": "deny", "message": DENY_MESSAGE}
    else:
        return {}  # sem decisão: o diálogo do terminal segue
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": behavior}}


@dataclass
class Request:
    pedido: str
    sid: str
    body: dict[str, Any]
    future: asyncio.Future[str] = field(repr=False)


class Permissions:
    """Pedidos abertos, um por sessão (um pedido novo da mesma sessão encerra o anterior)."""

    def __init__(self, timeout: float = REQUEST_TIMEOUT) -> None:
        self._timeout = timeout
        self._by_id: dict[str, Request] = {}
        # avisos para o controle: pedido aberto e pedido resolvido (com o resultado)
        self.on_open: Callable[[Request], Awaitable[None]] | None = None
        self.on_close: Callable[[Request, str], Awaitable[None]] | None = None

    def pending_for(self, sid: str) -> Request | None:
        return next((r for r in self._by_id.values() if r.sid == sid), None)

    async def handle(self, sid: str, body: dict[str, Any]) -> dict[str, Any]:
        """Chamado pelo servidor HTTP: espera a resposta e devolve a saída do hook."""
        old = self.pending_for(sid)
        if old is not None:  # o anterior já foi respondido na aba (só existe um diálogo por vez)
            await self.resolve(old.pedido, IN_TAB)
        req = Request(secrets.token_hex(6), sid, body, asyncio.get_running_loop().create_future())
        self._by_id[req.pedido] = req
        if self.on_open is not None:
            await self.on_open(req)
        try:
            result = await asyncio.wait_for(asyncio.shield(req.future), timeout=self._timeout)
        except TimeoutError:
            result = EXPIRED
            await self.resolve(req.pedido, EXPIRED)
        except asyncio.CancelledError:
            await self.resolve(req.pedido, EXPIRED)
            raise
        return decision(result)

    async def resolve(self, pedido: str, result: str) -> bool:
        """Resolve um pedido. False se ele já tinha sido resolvido (clique atrasado)."""
        req = self._by_id.pop(pedido, None)
        if req is None:
            return False
        if not req.future.done():
            req.future.set_result(result)
        if self.on_close is not None:
            await self.on_close(req, result)
        return True

    async def resolve_session(self, sid: str, result: str) -> None:
        req = self.pending_for(sid)
        if req is not None:
            await self.resolve(req.pedido, result)

    async def close_all(self) -> None:
        for pedido in list(self._by_id):
            await self.resolve(pedido, EXPIRED)


Auth = Callable[[str], str | None]  # token -> id da sessão
Handler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class HookServer:
    """Servidor HTTP mínimo (só `POST /permissao`, só 127.0.0.1). A biblioteca do WebSocket
    não lê corpo de POST, por isso um servidor separado, sem dependência nova."""

    def __init__(self, auth: Auth, handler: Handler) -> None:
        self._auth = auth
        self._handler = handler
        self.port = 0

    @contextlib.asynccontextmanager
    async def run(self, port: int = 0):
        server = await asyncio.start_server(self._client, "127.0.0.1", port, limit=MAX_HEADER)
        self.port = server.sockets[0].getsockname()[1]
        log.info("hook de permissões em 127.0.0.1:%d", self.port)
        try:
            yield self.port
        finally:
            server.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(server.wait_closed(), 1)

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            status, payload = await self._process(reader)
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            ValueError,
            ConnectionError,
        ):
            status, payload = 400, {"erro": "requisição inválida"}
        except Exception:
            log.exception("hook de permissões: falha")
            status, payload = 500, {}
        body = json.dumps(payload).encode()
        reason = {
            200: "OK",
            400: "Bad Request",
            401: "Unauthorized",
            404: "Not Found",
            413: "Payload Too Large",
        }
        head = (
            f"HTTP/1.1 {status} {reason.get(status, 'Error')}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode()
        with contextlib.suppress(ConnectionError):
            writer.write(head + body)
            await writer.drain()
        writer.close()

    async def _process(self, reader: asyncio.StreamReader) -> tuple[int, dict[str, Any]]:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
        lines = head.decode("latin-1").split("\r\n")
        method, path, _ = lines[0].split(" ", 2)
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        if method != "POST" or path.split("?")[0] != "/permissao":
            return 404, {}
        length = int(headers.get("content-length", "0"))
        if length < 0 or length > MAX_BODY:
            return 413, {}
        auth = headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        sid = self._auth(token) if token else None
        if sid is None:
            return 401, {}
        raw = await asyncio.wait_for(reader.readexactly(length), timeout=10)
        body = json.loads(raw or b"{}")
        if (
            not isinstance(body, dict)
            or body.get("hook_event_name", "PermissionRequest") != "PermissionRequest"
        ):
            return 200, {}
        return 200, await self._handler(sid, body)
