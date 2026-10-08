"""Servidor WebSocket local do Jarvis (só 127.0.0.1, token por execução).

A porta e o token vão para um arquivo de sessão (permissão 600) que a interface lê.
"""

import asyncio
import contextlib
import json
import logging
import os
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

from websockets.asyncio.server import ServerConnection, serve
from websockets.http11 import Request, Response

from jarvis import events
from jarvis.events import Event

log = logging.getLogger(__name__)

SESSION_FILE = Path.home() / "Library/Application Support/Jarvis/session.json"

Emit = Callable[[Event], Awaitable[None]]


class Brain(Protocol):
    async def ask(self, rid: str, text: str, emit: Emit) -> None: ...
    async def resolve_confirmation(self, confirm_id: str, accepted: bool) -> None: ...


def write_session(port: int, token: str, path: Path = SESSION_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"port": port, "token": token, "pid": os.getpid()}, f)
    tmp.replace(path)


class JarvisServer:
    def __init__(self, brain: Brain, token: str | None = None) -> None:
        self.brain = brain
        self.token = token or secrets.token_urlsafe(32)
        self._tasks: set[asyncio.Task[Any]] = set()

    def _authorize(self, conn: ServerConnection, request: Request) -> Response | None:
        query = parse_qs(urlparse(request.path).query)
        sent = (query.get("token") or [""])[0]
        if not secrets.compare_digest(sent, self.token):
            return conn.respond(401, "unauthorized\n")
        return None

    async def _handle(self, conn: ServerConnection) -> None:
        lock = asyncio.Lock()

        async def emit(event: Event) -> None:
            async with lock:
                await conn.send(event.to_json())

        async for raw in conn:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            rid = str(msg.get("id") or secrets.token_hex(4))
            if msg.get("type") == "ask" and str(msg.get("text", "")).strip():
                task = asyncio.create_task(self._ask(rid, str(msg["text"]), emit))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            elif msg.get("type") == "confirm" and msg.get("confirm_id"):
                await self.brain.resolve_confirmation(
                    str(msg["confirm_id"]), bool(msg.get("accepted"))
                )

    async def _ask(self, rid: str, text: str, emit: Emit) -> None:
        try:
            await self.brain.ask(rid, text, emit)
        except Exception:
            log.exception("falha ao responder %s", rid)
            await emit(events.error(rid, "Tive um problema para responder agora."))

    @contextlib.asynccontextmanager
    async def run(self, port: int = 0, session_file: Path | None = SESSION_FILE):
        async with serve(
            self._handle, "127.0.0.1", port, process_request=self._authorize
        ) as server:
            bound = next(iter(server.sockets)).getsockname()[1]
            if session_file is not None:
                write_session(bound, self.token, session_file)
            log.info("Jarvis ouvindo em 127.0.0.1:%d", bound)
            yield bound
