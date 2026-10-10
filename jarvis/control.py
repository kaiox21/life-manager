"""Controle dos terminais compartilhados: liga o tmux do Jarvis, os pedidos de permissão (hook
síncrono), a numeração dos terminais e a interface (WebSocket), e serve as ferramentas do modelo.

Regras (openspec/changes/jarvis-terminais-controle):
- aprovar/negar só por mensagem `permission_answer` da interface (clique do Kaio); o modelo não
  tem ferramenta para isso;
- o modelo escreve num terminal só com confirmação, só texto puro, só nos terminais compartilhados,
  e só quando é seguro: Claude Code parado esperando o Kaio (com um diálogo na tela, o Enter
  escolheria uma opção) ou shell livre (sem programa em primeiro plano);
- o conteúdo da tela nunca vai para o modelo.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from jarvis import events
from jarvis.events import Event
from jarvis.hooks.claude_event import summary
from jarvis.permissions import ALLOW, DENY, EXPIRED, IN_TAB, Permissions, Request
from jarvis.sessions import Folders, PtyClient, clean_text, memory_level
from jarvis.terminals import DONE, FREE, PERMISSION, WAITING, Terminal, Terminals
from jarvis.tmux import Tmux, minimal_env

log = logging.getLogger(__name__)

OUTPUT = b"\x01"  # quadro binário: tipo + id da sessão do tmux (8) + bytes
HIGH_WATER = 4 * 1024 * 1024  # bytes ainda não entregues a uma interface: pausa o cliente
LOW_WATER = 512 * 1024
# eventos dos hooks que só chegam depois de o pedido ter sido respondido no terminal
ANSWERED_EVENTS = {"PostToolUse", "PostToolUseFailure", "UserPromptSubmit", "Stop", "SessionEnd"}

Confirm = Callable[[str], Awaitable[bool]]


class Client(Protocol):
    emit: Callable[[Event], Awaitable[None]]
    send_bytes: Callable[[bytes], Awaitable[None]]
    attached: str | None
    backlog: int


def frame(kind: bytes, sessao: str, data: bytes) -> bytes:
    return kind + sessao.encode()[:8].ljust(8, b" ") + data


@dataclass(eq=False)
class View:
    """Aba visível numa interface: um cliente `tmux attach` num pty do cérebro."""

    sessao: str
    pty: PtyClient


class TerminalControl:
    def __init__(
        self,
        tmux: Tmux,
        terminals: Terminals,
        permissions: Permissions,
        folders: Folders,
        *,
        max_claude: int = 4,
        min_memory: int = 20,
        memory: Callable[[], int | None] = memory_level,
        pty_factory: Callable[..., PtyClient] = PtyClient,
    ) -> None:
        self.tmux = tmux
        self.terminals = terminals
        self.permissions = permissions
        self.folders = folders
        self.max_claude = max_claude
        self.min_memory = min_memory
        self._memory = memory
        self._pty_factory = pty_factory
        self.broadcast: Callable[[Event], Awaitable[None]] = self._no_broadcast
        self._clients: set[Any] = set()
        self._views: dict[Any, View] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        terminals.socket = tmux.socket
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

    # --- lista do tmux

    def own_clients(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for view in self._views.values():
            out[view.sessao] = out.get(view.sessao, 0) + 1
        return out

    async def refresh(self) -> tuple[bool, list[dict[str, Any]]]:
        """Lê o tmux e atualiza os terminais. Chamado a cada 1 s e depois de cada ação."""
        return self.terminals.sync_tmux(await self.tmux.panes(), self.own_clients())

    async def publish(self) -> None:
        await self.broadcast(events.terminals(self.terminals.snapshot()))

    async def _refresh_and_publish(self) -> None:
        await self.refresh()
        await self.publish()

    # --- abrir, abas, mandar, fechar (interface e ferramentas do modelo)

    def _refusal(self, claude: bool) -> str | None:
        level = self._memory()
        if level is not None and level < self.min_memory:
            return (
                f"O Mac está com pouca memória livre ({level}%). Feche algo antes de abrir "
                "outro terminal."
            )
        if claude and self.terminals.claude_count() >= self.max_claude:
            return (
                f"Já há {self.terminals.claude_count()} Claude Code rodando nos terminais (o "
                f"limite é {self.max_claude}). Feche um deles antes."
            )
        return None

    async def open(self, pasta: str, claude: bool = False) -> dict[str, Any]:
        if not self.tmux.available:
            return {"erro": "O tmux não está instalado (brew install tmux)."}
        target = self.folders.resolve(pasta)
        if "pasta" not in target:
            return target
        refusal = self._refusal(claude)
        if refusal:
            return {"erro": refusal}
        path: Path = target["pasta"]
        sessao = await self.tmux.new_session(path)
        if sessao is None:
            return {"erro": "Não consegui abrir o terminal."}
        await self.tmux.set_option(sessao, "@jarvis_aba", "1")
        await self.refresh()
        t = self.terminals.by_key(f"tmux:{sessao}")
        if t is None:
            return {"erro": "O terminal abriu mas não apareceu na lista."}
        if claude:
            await asyncio.sleep(0.3)  # o shell de login termina de subir
            await self.tmux.send_command(t.painel, "claude")
        await self.publish()
        return {
            "status": "aberto",
            "numero": t.numero,
            "pasta": t.pasta,
            "tipo": "claude" if claude else "shell",
            "sessao": sessao,
        }

    async def open_tab(self, sessao: str) -> bool:
        """Aba aberta: o terminal vive mesmo sem janela e sem cliente (marca na sessão)."""
        if self.terminals.by_key(f"tmux:{sessao}") is None:
            return False
        await self.tmux.set_option(sessao, "@jarvis_aba", "1")
        await self.tmux.set_option(sessao, "destroy-unattached", "off")
        await self._refresh_and_publish()
        return True

    async def close_tab(self, sessao: str) -> None:
        """Aba fechada (×): sai a marca; terminal do Terminal.app sem janela acaba aqui."""
        t = self.terminals.by_key(f"tmux:{sessao}")
        for client, view in list(self._views.items()):
            if view.sessao == sessao:
                await self._close_view(client)
        await self.tmux.unset_option(sessao, "@jarvis_aba")
        if t is not None and t.origem == "terminal":
            await self.tmux.set_option(sessao, "destroy-unattached", "on")
        await self._refresh_and_publish()

    def _target(self, numero: int) -> tuple[Terminal | None, str | None]:
        t = self.terminals.by_numero(numero)
        if t is None:
            return None, f"Não há Terminal {numero}."
        if not t.tmux:
            return None, (
                f"O Terminal {numero} não é um terminal compartilhado: só escrevo e fecho os "
                "terminais do Jarvis (os do Terminal.app abertos depois da instalação e os que "
                "eu abri)."
            )
        return t, None

    @staticmethod
    def _send_problem(t: Terminal, text: str) -> tuple[str | None, str]:
        """(motivo para não mandar, tipo: "mensagem" | "comando")."""
        if t.tipo == "claude":
            if t.estado == PERMISSION:
                return (
                    f"O Terminal {t.numero} está esperando uma resposta no diálogo de permissão. "
                    "Responda pelo aviso ou no terminal.",
                    "mensagem",
                )
            if t.estado not in (DONE, WAITING):
                return f"O Terminal {t.numero} está trabalhando; espere ele terminar.", "mensagem"
            return None, "mensagem"
        if "\n" in text:
            return "Mande um comando de uma linha só.", "comando"
        if t.estado != FREE:
            return f"Há um programa rodando no Terminal {t.numero} ({t.comando}).", "comando"
        return None, "comando"

    async def send(self, numero: int, texto: str, confirm: Confirm | None) -> dict[str, Any]:
        t, error = self._target(numero)
        if t is None:
            return {"erro": error}
        clean = clean_text(texto)
        if not clean:
            return {"erro": "Nada para mandar."}
        problem, kind = self._send_problem(t, clean)
        if problem:
            return {"erro": problem}
        label = "Mensagem para o" if kind == "mensagem" else "Comando no"
        question = f"{label} Terminal {t.numero} ({t.pasta}): {clean}"
        if confirm is None or not await confirm(question):
            return {"status": "cancelado", "numero": t.numero}
        # o Kaio pode ter demorado: confere tudo de novo antes de escrever
        await self.refresh()
        again = self.terminals.by_key(t.chave)
        if again is None or again.painel != t.painel:
            return {"erro": f"O Terminal {numero} fechou."}
        problem, kind_now = self._send_problem(again, clean)
        if problem or kind_now != kind:
            return {"erro": problem or f"O Terminal {numero} mudou; peça de novo."}
        if kind == "mensagem":
            ok = await self.tmux.send_message(again.painel, clean)
        else:
            ok = await self.tmux.send_command(again.painel, clean)
        if not ok:
            return {"erro": f"Não consegui escrever no Terminal {numero}."}
        return {
            "status": "enviado",
            "numero": again.numero,
            "pasta": again.pasta,
            "tipo": kind,
            "texto": clean,
        }

    async def close(self, numero: int, confirm: Confirm | None) -> dict[str, Any]:
        t, error = self._target(numero)
        if t is None:
            return {"erro": error}
        if t.ocupado or t.janela:
            reasons = []
            if t.ocupado:
                reasons.append(f"está {t.estado}")
            if t.janela:
                reasons.append("a janela dele no Terminal.app também fecha")
            question = (
                f"O Terminal {t.numero} ({t.pasta}) {' e '.join(reasons)}. Fechar mesmo assim?"
            )
            if confirm is None or not await confirm(question):
                return {"status": "cancelado", "numero": t.numero}
        for client, view in list(self._views.items()):
            if view.sessao == t.tmux:
                await self._close_view(client)
        await self.tmux.kill(t.tmux)
        await self.permissions.resolve_session(t.chave, EXPIRED)
        await self._refresh_and_publish()
        return {"status": "fechado", "numero": t.numero, "pasta": t.pasta}

    # --- mensagens da interface

    async def handle(self, client: Client, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        sessao = str(msg.get("sessao") or "")
        self._clients.add(client)
        view = self._views.get(client)
        if kind == "term_attach":
            await self._attach(client, sessao, msg)
        elif kind == "term_detach":
            if view is not None and view.sessao == sessao:
                await self._close_view(client)
        elif kind == "term_input":
            data = str(msg.get("data") or "")
            if (
                view is not None
                and view.sessao == sessao
                and data
                and view.pty.write(data.encode())
            ):
                # tecla na aba com um pedido aberto: o Kaio está respondendo ali
                await self.permissions.resolve_session(f"tmux:{sessao}", IN_TAB)
        elif kind == "term_resize":
            if view is not None and view.sessao == sessao:
                with contextlib.suppress(KeyError, TypeError, ValueError):
                    view.pty.resize(int(msg["cols"]), int(msg["rows"]))
        elif kind == "term_pause":
            if view is not None and view.sessao == sessao:
                view.pty.pause(bool(msg.get("on")))
        elif kind == "term_open":
            result = await self.open(str(msg.get("pasta") or ""), bool(msg.get("claude")))
            await client.emit(events.terminal_opened(result))
        elif kind == "term_tab_open":
            await self.open_tab(sessao)
        elif kind == "term_tab_close":
            # a interface já confirmou com o Kaio quando o terminal ia acabar com algo rodando
            await self.close_tab(sessao)
        elif kind == "permission_answer":
            result = {"permitir": ALLOW, "negar": DENY}.get(str(msg.get("decisao")))
            pedido = str(msg.get("pedido") or "")
            if result is None or not pedido:
                return
            if not await self.permissions.resolve(pedido, result):
                await client.emit(events.terminal_resolved(pedido, "já respondido"))

    async def _attach(self, client: Client, sessao: str, msg: dict[str, Any]) -> None:
        if self._views.get(client) is not None:
            await self._close_view(client)
        if self.terminals.by_key(f"tmux:{sessao}") is None:
            return
        cols, rows = 120, 32
        with contextlib.suppress(KeyError, TypeError, ValueError):
            cols, rows = int(msg["cols"]), int(msg["rows"])
        view_ref: list[View] = []

        def on_exit() -> None:
            if view_ref and self._views.get(client) is view_ref[0]:
                del self._views[client]
                client.attached = None

        try:
            pty = self._pty_factory(
                self.tmux.attach_argv(sessao),
                minimal_env(),
                Path.home(),
                lambda data: self._on_output(client, sessao, data),
                on_exit,
                cols=cols,
                rows=rows,
            )
        except OSError:
            log.exception("não consegui anexar a aba %s", sessao)
            return
        view = View(sessao, pty)
        view_ref.append(view)
        self._views[client] = view
        client.attached = sessao

    async def _close_view(self, client: Any) -> None:
        view = self._views.pop(client, None)
        if view is not None:
            client.attached = None
            await view.pty.close()

    def detach(self, client: Client) -> None:
        self._clients.discard(client)
        if client in self._views:
            self._spawn(self._close_view(client))

    # --- saída das abas

    def _on_output(self, client: Any, sessao: str, data: bytes) -> None:
        client.backlog += len(data)
        view = self._views.get(client)
        if view is not None and client.backlog > HIGH_WATER and not view.pty.paused:
            view.pty.pause(True)
        self._spawn(self._deliver(client, frame(OUTPUT, sessao, data), len(data)))

    async def _deliver(self, client: Any, payload: bytes, size: int) -> None:
        try:
            await client.send_bytes(payload)
        finally:
            client.backlog -= size
            view = self._views.get(client)
            if view is not None and view.pty.paused and client.backlog < LOW_WATER:
                view.pty.pause(False)

    # --- pedidos de permissão

    async def on_hook(self, _auth: str, body: dict[str, Any]) -> dict[str, Any]:
        """Pedido vindo do hook síncrono (`claude_permission.py`): qual terminal, e espera."""
        painel = str(body.get("jarvis_painel") or "")
        key = self.terminals.pane_key(painel)
        if key is None:
            await self.refresh()  # terminal aberto há menos de 1 s
            key = self.terminals.pane_key(painel)
        if key is None:
            return {}
        return await self.permissions.handle(key, body)

    def _on_terminal_event(self, t: Terminal, evento: str) -> None:
        if t.tmux and t.pedido and evento in ANSWERED_EVENTS:
            self._spawn(self.permissions.resolve_session(t.chave, IN_TAB))

    async def _on_request(self, req: Request) -> None:
        tool = str(req.body.get("tool_name") or "")
        t = self.terminals.open_request(
            req.sid, req.pedido, tool, summary(tool, req.body.get("tool_input"))
        )
        if t is None:
            return
        await self.publish()
        await self.broadcast(events.terminal_alert(self.terminals.alert_for(t)))

    async def _on_resolved(self, req: Request, result: str) -> None:
        self.terminals.close_request(req.sid, req.pedido)
        await self.broadcast(events.terminal_resolved(req.pedido, result))
        await self.publish()

    async def shutdown(self) -> None:
        await self.permissions.close_all()
        for client in list(self._views):
            await self._close_view(client)
