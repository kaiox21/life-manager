"""Servidor WebSocket local do Jarvis (só 127.0.0.1, token por execução).

A porta e o token vão para um arquivo de sessão (permissão 600) que a interface lê.
Mensagens JSON (ask, confirm, interrupt, voice_*, term_*, permission_answer) e quadros
binários: da interface, o PCM da voz; para a interface, a saída das abas de terminal.
"""

import asyncio
import contextlib
import json
import logging
import os
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from jarvis import events
from jarvis.events import Event

log = logging.getLogger(__name__)

SESSION_FILE = Path.home() / "Library/Application Support/Jarvis/session.json"
MAX_VOICE_BYTES = 16_000 * 2 * 120  # 2 min de PCM Int16 a 16 kHz

Emit = Callable[[Event], Awaitable[None]]


class Brain(Protocol):
    async def ask(self, rid: str, text: str, emit: Emit, mode: str = "texto") -> None: ...
    async def voice(self, rid: str, pcm: bytes, sample_rate: int, emit: Emit) -> None: ...
    async def resolve_confirmation(self, confirm_id: str, accepted: bool) -> None: ...
    def interrupt(self) -> None: ...
    async def panel(self, rid: str, emit: Emit) -> None: ...


def write_session(
    port: int, token: str, path: Path = SESSION_FILE, extra: dict[str, Any] | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"port": port, "token": token, "pid": os.getpid(), **(extra or {})}, f)
    tmp.replace(path)


class Control(Protocol):
    """Abas de terminal (jarvis/control.py)."""

    async def handle(self, client: "Client", msg: dict[str, Any]) -> None: ...
    def detach(self, client: "Client") -> None: ...


@dataclass(eq=False)
class Client:
    """Uma interface conectada (HUD ou painel)."""

    emit: Emit
    send_bytes: Callable[[bytes], Awaitable[None]]
    attached: str | None = None  # aba de terminal cuja saída esta interface recebe
    backlog: int = 0  # bytes de terminal ainda não entregues


@dataclass
class _Voice:
    rid: str
    sample_rate: int
    chunks: list[bytes] = field(default_factory=list)
    size: int = 0


class JarvisServer:
    def __init__(self, brain: Brain, token: str | None = None) -> None:
        self.brain = brain
        self.token = token or secrets.token_urlsafe(32)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._clients: set[Emit] = set()
        # eventos mandados a cada conexão nova (ex.: a lista atual de terminais)
        self.greeting: Callable[[], list[Event]] = lambda: []
        self.control: Control | None = None
        self.wake: Any = None  # WakeService (escuta da palavra "Jarvis"), se houver
        self._listen: set[Emit] = set()  # conexões de escuta (o app em Rust)

    async def broadcast(self, event: Event) -> None:
        """Manda um evento a todas as conexões (HUD, painel e a escuta do app)."""
        for emit in list(self._clients):
            await emit(event)

    async def broadcast_ui(self, event: Event) -> None:
        """Só às interfaces que desenham (HUD e painel), sem a conexão de escuta."""
        for emit in list(self._clients):
            if emit not in self._listen:
                await emit(event)

    def _authorize(self, conn: ServerConnection, request: Request) -> Response | None:
        query = parse_qs(urlparse(request.path).query)
        sent = (query.get("token") or [""])[0]
        if not secrets.compare_digest(sent, self.token):
            return conn.respond(401, "unauthorized\n")
        return None

    async def _handle(self, conn: ServerConnection) -> None:
        lock = asyncio.Lock()
        voice: _Voice | None = None
        active: asyncio.Task[None] | None = None

        async def emit(event: Event) -> None:
            async with lock:
                with contextlib.suppress(ConnectionClosed):  # a interface pode já ter saído
                    await conn.send(event.to_json())

        async def send_bytes(data: bytes) -> None:
            async with lock:
                with contextlib.suppress(ConnectionClosed):
                    await conn.send(data)

        client = Client(emit, send_bytes)
        self._clients.add(emit)
        for event in self.greeting():
            await emit(event)

        def launch(coro: Awaitable[None]) -> asyncio.Task[None]:
            nonlocal active
            task = asyncio.create_task(coro)  # type: ignore[arg-type]
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            active = task
            return task

        try:
            async for raw in conn:
                if isinstance(raw, bytes):
                    if emit in self._listen:
                        if raw[:1] == b"\x10" and self.wake is not None:
                            self.wake.feed(raw[1:])
                        continue
                    if voice is not None and voice.size + len(raw) <= MAX_VOICE_BYTES:
                        voice.chunks.append(raw)
                        voice.size += len(raw)
                    continue
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                kind = msg.get("type")
                if kind == "wake_listen":
                    self._listen.add(emit)
                    if self.wake is not None:
                        self.wake.set_listening(bool(msg.get("on")))
                    continue
                if isinstance(kind, str) and kind.startswith(("term_", "permission_")):
                    if self.control is not None:
                        try:
                            await self.control.handle(client, msg)
                        except Exception:
                            log.exception("terminais: falha em %s", kind)
                    continue
                rid = str(msg.get("id") or secrets.token_hex(4))
                if kind == "ask" and str(msg.get("text", "")).strip():
                    mode = "voz" if msg.get("mode") == "voz" else "texto"
                    launch(self._run(rid, emit, self.brain.ask(rid, str(msg["text"]), emit, mode)))
                elif kind == "confirm" and msg.get("confirm_id"):
                    await self.brain.resolve_confirmation(
                        str(msg["confirm_id"]), bool(msg.get("accepted"))
                    )
                elif kind == "interrupt":
                    self.brain.interrupt()
                    if active and not active.done():
                        active.cancel()
                elif kind == "voice_start":
                    voice = _Voice(rid, int(msg.get("sampleRate") or 16_000))
                    set_ptt = getattr(self.brain, "set_ptt", None)
                    if set_ptt is not None:
                        set_ptt(True)
                    prewarm = getattr(self.brain, "prewarm", None)
                    if prewarm is not None:
                        prewarm()
                elif kind == "voice_end" and voice is not None and voice.rid == rid:
                    pcm, rate = b"".join(voice.chunks), voice.sample_rate
                    voice = None
                    if getattr(self.brain, "set_ptt", None) is not None:
                        self.brain.set_ptt(False)
                    launch(self._run(rid, emit, self.brain.voice(rid, pcm, rate, emit)))
                elif kind == "voice_cancel":
                    voice = None
                    if getattr(self.brain, "set_ptt", None) is not None:
                        self.brain.set_ptt(False)
                elif kind == "panel":
                    # fora do `active`: atualizar o painel não pode ser cancelado por "interrupt"
                    task = asyncio.create_task(self._run(rid, emit, self.brain.panel(rid, emit)))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
        finally:
            self._clients.discard(emit)
            if emit in self._listen:
                self._listen.discard(emit)
                if self.wake is not None and not self._listen:
                    self.wake.set_listening(False)
            if self.control is not None:
                self.control.detach(client)

    async def _run(self, rid: str, emit: Emit, coro: Awaitable[None]) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await emit(events.error(rid, "cancelado"))
        except Exception:
            log.exception("falha ao responder %s", rid)
            await emit(events.error(rid, "Tive um problema para responder agora."))

    def check_token(self, token: str) -> str | None:
        """Autentica o hook de permissões (mesmo token do WebSocket, lido do session.json)."""
        return "jarvis" if token and secrets.compare_digest(token, self.token) else None

    @contextlib.asynccontextmanager
    async def run(
        self,
        port: int = 0,
        session_file: Path | None = SESSION_FILE,
        extra: dict[str, Any] | None = None,
    ):
        async with serve(
            self._handle, "127.0.0.1", port, process_request=self._authorize
        ) as server:
            bound = next(iter(server.sockets)).getsockname()[1]
            if session_file is not None:
                write_session(bound, self.token, session_file, extra)
            log.info("Jarvis ouvindo em 127.0.0.1:%d", bound)
            yield bound
