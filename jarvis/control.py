"""Controle das abas de terminal: liga as sessões (pty), os pedidos de permissão (hook HTTP),
a numeração dos terminais e a interface (WebSocket), e serve as ferramentas do modelo.

Regras (openspec/changes/jarvis-terminais-controle):
- aprovar/negar só por mensagem `permission_answer` da interface (clique do Kaio); o modelo
  não tem ferramenta para isso;
- o modelo escreve numa sessão só com confirmação, só texto puro e só nas abertas pelo Jarvis;
- o conteúdo da tela nunca vai para o modelo.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from jarvis import events
from jarvis.events import Event
from jarvis.hooks.claude_event import summary
from jarvis.permissions import ALLOW, DENY, EXPIRED, IN_TAB, Permissions, Request, hook_settings
from jarvis.sessions import Session, Sessions, clean_text
from jarvis.terminals import PERMISSION, WORKING, Terminal, Terminals

log = logging.getLogger(__name__)

OUTPUT, REPLAY = b"\x01", b"\x02"  # quadros binários: tipo + id da sessão (8) + bytes
HIGH_WATER = 4 * 1024 * 1024  # bytes ainda não entregues a uma interface: pausa a sessão
LOW_WATER = 512 * 1024
# eventos dos hooks globais que só chegam depois de o pedido ter sido respondido na aba
ANSWERED_EVENTS = {"PostToolUse", "PostToolUseFailure", "UserPromptSubmit", "Stop", "SessionEnd"}
BUSY = {WORKING, PERMISSION}

Confirm = Callable[[str], Awaitable[bool]]


class Client(Protocol):
    emit: Callable[[Event], Awaitable[None]]
    send_bytes: Callable[[bytes], Awaitable[None]]
    attached: str | None
    backlog: int


def frame(kind: bytes, sid: str, data: bytes) -> bytes:
    return kind + sid.encode()[:8].ljust(8, b" ") + data


class TerminalControl:
    def __init__(self, sessions: Sessions, terminals: Terminals, permissions: Permissions) -> None:
        self.sessions = sessions
        self.terminals = terminals
        self.permissions = permissions
        self.hook_port = 0
        self.broadcast: Callable[[Event], Awaitable[None]] = self._no_broadcast
        self._clients: set[Any] = set()
        self._tasks: set[asyncio.Task[Any]] = set()
        sessions.on_output = self._on_output
        sessions.on_exit = self._on_exit
        terminals.listener = self._on_terminal_event
        permissions.on_open = self._on_request
        permissions.on_close = self._on_resolved

    @staticmethod
    async def _no_broadcast(_e: Event) -> None:
        return None

    def _spawn(self, coro: Awaitable[Any]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # --- estado para a interface

    def greeting(self) -> list[Event]:
        return [events.terminal_tabs(self.sessions.tabs())]

    async def publish(self) -> None:
        await self.broadcast(events.terminal_tabs(self.sessions.tabs()))
        await self.broadcast(events.terminals(self.terminals.snapshot()))

    # --- abrir, mandar, fechar (usados pela interface e pelas ferramentas do modelo)

    async def open(self, pasta: str = "", retomar: str = "") -> dict[str, Any]:
        resume, cont = None, False
        if retomar:
            closed = self.sessions.closed.get(retomar)
            if closed is None:
                return {"erro": "Essa aba já não existe."}
            target = {"pasta": closed.pasta}
            resume, cont = (closed.sessao or None), not closed.sessao
        else:
            target = self.sessions.folders.resolve(pasta)
        if "pasta" not in target:
            return target
        refusal = self.sessions.can_open()
        if refusal:
            return {"erro": refusal}
        try:
            s = self.sessions.start(
                target["pasta"], lambda _tk: hook_settings(self.hook_port), resume=resume, cont=cont
            )
        except (OSError, RuntimeError) as exc:
            log.warning("não abriu a sessão: %s", exc)
            return {
                "erro": str(exc)
                if isinstance(exc, RuntimeError)
                else "Não consegui abrir o Claude Code."
            }
        if retomar:
            self.sessions.closed.pop(retomar, None)
        t = self.terminals.register(s.pid, str(s.pasta), s.sid)
        s.numero = t.numero
        self.sessions.save()
        await self.publish()
        return {"status": "aberto", "numero": s.numero, "pasta": s.pasta.name, "sid": s.sid}

    def _target(self, numero: int) -> tuple[Session | None, str | None]:
        s = self.sessions.by_numero(numero)
        if s is not None:
            return s, None
        if any(t["numero"] == numero for t in self.terminals.snapshot()):
            return None, (
                f"O Terminal {numero} não foi aberto pelo Jarvis: só escrevo e fecho as sessões "
                "abertas por mim."
            )
        return None, f"Não há Terminal {numero}."

    async def send(self, numero: int, texto: str, confirm: Confirm | None) -> dict[str, Any]:
        s, error = self._target(numero)
        if s is None:
            return {"erro": error}
        clean = clean_text(texto)
        if not clean:
            return {"erro": "Nada para mandar."}
        question = f"Mandar para o Terminal {s.numero} ({s.pasta.name}): {clean}"
        if confirm is None or not await confirm(question):
            return {"status": "cancelado", "numero": s.numero}
        if self.sessions.by_numero(numero) is not s:  # fechou enquanto o Kaio decidia
            return {"erro": f"O Terminal {numero} fechou."}
        await self.sessions.send_text(s.sid, clean)
        return {"status": "enviado", "numero": s.numero, "pasta": s.pasta.name, "texto": clean}

    async def close(self, numero: int, confirm: Confirm | None) -> dict[str, Any]:
        s, error = self._target(numero)
        if s is None:
            return {"erro": error}
        t = self.terminals.by_pid(s.pid)
        if t is not None and t.estado in BUSY:
            question = (
                f"O Terminal {s.numero} ({s.pasta.name}) está {t.estado}. Fechar mesmo assim?"
            )
            if confirm is None or not await confirm(question):
                return {"status": "cancelado", "numero": s.numero}
        await self.sessions.close(s.sid)
        return {"status": "fechado", "numero": s.numero, "pasta": s.pasta.name}

    # --- mensagens da interface

    async def handle(self, client: Client, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        sid = str(msg.get("sid") or "")
        self._clients.add(client)
        if kind == "term_attach":
            client.attached = sid
            s = self.sessions.open.get(sid)
            if s is not None:
                await client.send_bytes(frame(REPLAY, sid, bytes(s.buffer)))
                self.sessions.redraw(sid)
        elif kind == "term_detach":
            if client.attached == sid:
                client.attached = None
        elif kind == "term_input":
            data = str(msg.get("data") or "")
            if data and self.sessions.write(sid, data.encode()):
                # tecla na aba com um pedido aberto: o Kaio está respondendo ali
                await self.permissions.resolve_session(sid, IN_TAB)
        elif kind == "term_resize":
            with contextlib.suppress(TypeError, ValueError):
                self.sessions.resize(sid, int(msg["cols"]), int(msg["rows"]))
        elif kind == "term_pause":
            self.sessions.pause(sid, bool(msg.get("on")))
        elif kind == "term_open":
            result = await self.open(str(msg.get("pasta") or ""), str(msg.get("retomar") or ""))
            await client.emit(events.terminal_opened(result))
        elif kind == "term_close":
            # a interface já confirmou com o Kaio (aba trabalhando); aqui só encerra
            await self.sessions.close(sid)
            await self.publish()
        elif kind == "permission_answer":
            result = {"permitir": ALLOW, "negar": DENY}.get(str(msg.get("decisao")))
            pedido = str(msg.get("pedido") or "")
            if result is None or not pedido:
                return
            if not await self.permissions.resolve(pedido, result):
                await client.emit(events.terminal_resolved(pedido, "já respondido"))

    def detach(self, client: Client) -> None:
        self._clients.discard(client)

    # --- saída das sessões

    def _on_output(self, s: Session, data: bytes) -> None:
        for client in list(self._clients):
            if client.attached != s.sid:
                continue
            client.backlog += len(data)
            if client.backlog > HIGH_WATER and not s.paused:
                self.sessions.pause(s.sid, True)
            self._spawn(self._deliver(client, s.sid, frame(OUTPUT, s.sid, data)))

    async def _deliver(self, client: Client, sid: str, payload: bytes) -> None:
        try:
            await client.send_bytes(payload)
        finally:
            client.backlog -= len(payload) - 9
            s = self.sessions.open.get(sid)
            if s is not None and s.paused and client.backlog < LOW_WATER:
                self.sessions.pause(sid, False)

    def _on_exit(self, s: Session) -> None:
        self.terminals.forget(s.pid)
        for client in self._clients:
            if client.attached == s.sid:
                client.attached = None
        self._spawn(self._after_exit(s))

    async def _after_exit(self, s: Session) -> None:
        await self.permissions.resolve_session(s.sid, EXPIRED)
        await self.publish()

    # --- eventos dos hooks globais e pedidos de permissão

    def _on_terminal_event(self, t: Terminal, evento: str) -> None:
        if not t.aba:
            return
        s = self.sessions.open.get(t.aba)
        if s is None:
            return
        if t.sessao and t.sessao != s.sessao:
            s.sessao = t.sessao
            self.sessions.save()
        if evento in ANSWERED_EVENTS and t.pedido:
            self._spawn(self.permissions.resolve_session(s.sid, IN_TAB))

    async def _on_request(self, req: Request) -> None:
        s = self.sessions.open.get(req.sid)
        if s is None:
            return
        tool = str(req.body.get("tool_name") or "")
        tool_input = req.body.get("tool_input")
        t = self.terminals.open_request(s.pid, req.pedido, tool, summary(tool, tool_input))
        if t is None:  # sem número ainda (não deve acontecer: registrado ao abrir)
            t = self.terminals.register(s.pid, str(s.pasta), s.sid)
            self.terminals.open_request(s.pid, req.pedido, tool, summary(tool, tool_input))
        await self.broadcast(events.terminals(self.terminals.snapshot()))
        await self.broadcast(events.terminal_alert(self.terminals.alert_for(t)))

    async def _on_resolved(self, req: Request, result: str) -> None:
        s = self.sessions.open.get(req.sid)
        if s is not None:
            self.terminals.close_request(s.pid, req.pedido)
        await self.broadcast(events.terminal_resolved(req.pedido, result))
        await self.broadcast(events.terminals(self.terminals.snapshot()))

    async def shutdown(self) -> None:
        await self.permissions.close_all()
        await self.sessions.shutdown()
