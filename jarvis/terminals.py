"""Gerenciador de terminais: sessões do Claude Code deste Mac, numeradas, com avisos.

Lê o arquivo que os hooks (`jarvis/hooks/claude_event.py`) preenchem. Um terminal é um
processo `claude` (o `session_id` muda com /clear e ao retomar). Não existe evento no momento
em que o Kaio aprova uma permissão: "pedindo permissão" vale até o próximo evento da sessão
ou 20 s (openspec/specs/jarvis-terminais).

Terminais compartilhados (sessões do tmux do Jarvis, `jarvis/tmux.py`) entram pela lista do
tmux (`sync_tmux`), com a chave `tmux:<session_id>`, e os eventos de um Claude Code rodando
dentro deles chegam pelo painel (`TMUX_PANE`) anotado pelo hook. Neles o pedido de permissão é
acompanhado pelo hook síncrono (`jarvis/permissions.py`): o aviso sai do pedido, com botões, e o
prazo de 20 s não vale enquanto o pedido estiver aberto.
"""

import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from jarvis.tmux import SHELLS

EVENTS_FILE = Path.home() / "Library/Application Support/Jarvis/claude-events.jsonl"
PERMISSION_TTL = 20.0
STALE_AFTER = 12 * 3600.0
LIVENESS_EVERY = 30.0
END_GRACE = 3.0  # depois de SessionEnd, espera o processo sair (ou um /clear recomeçar)
MAX_BYTES = 1_000_000
KEEP_LINES = 2_000

WORKING = "trabalhando"
PERMISSION = "pedindo permissão"
WAITING = "esperando você"
DONE = "terminou"
FREE = "livre"  # shell no prompt
RUNNING = "rodando"  # shell com um programa em primeiro plano
DEFER_FOR = 5.0  # evento de um painel do tmux ainda não listado: espera a próxima leitura

VERBS = {
    "Bash": "rodar",
    "Edit": "editar",
    "MultiEdit": "editar",
    "Write": "escrever",
    "NotebookEdit": "editar",
    "Read": "ler",
    "WebFetch": "acessar",
}


@dataclass
class Terminal:
    numero: int
    pasta: str
    desde: float
    estado: str
    sessao: str
    pid: int | None
    ferramenta: str = ""
    resumo: str = ""
    mudou: float = 0.0
    visto: float = 0.0
    fim: float | None = None
    chave: str = ""
    tipo: str = "claude"  # "claude" | "shell"
    tmux: str = ""  # session_id do tmux do Jarvis (vazio = sessão de fora)
    painel: str = ""
    origem: str = ""  # "terminal" (Terminal.app) | "jarvis"
    aba: bool = False  # aberto numa aba do Jarvis
    janela: bool = False  # aberto numa janela do Terminal.app
    comando: str = ""  # programa em primeiro plano no painel
    pedido: str = ""  # pedido de permissão aberto no hook

    @property
    def ocupado(self) -> bool:
        """Algo rodando: Claude Code trabalhando ou pedindo, ou programa no shell. Um `claude`
        sem eventos dos hooks aparece como programa (comando "2.1.296") e conta como ocupado."""
        if self.tipo == "claude":
            return self.estado in (WORKING, PERMISSION)
        return self.estado != FREE

    def view(self) -> dict[str, Any]:
        out = asdict(self)
        for k in ("mudou", "visto", "fim"):
            out.pop(k)
        out["ocupado"] = self.ocupado
        return out


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def folder(cwd: str) -> str:
    if not cwd:
        return "?"
    path = Path(cwd)
    return "~" if path == Path.home() else path.name


def alert_text(t: Terminal, kind: str) -> str:
    who = f"Terminal {t.numero} ({t.pasta})"
    if kind == "permissao":
        verb = VERBS.get(t.ferramenta)
        if verb and t.resumo:
            return f"{who} está pedindo para {verb} `{t.resumo}`"
        return f"{who} está pedindo permissão para usar {t.resumo or t.ferramenta}"
    if kind == "espera":
        return f"{who} está esperando você"
    return f"{who} terminou"


class Terminals:
    def __init__(
        self,
        path: Path = EVENTS_FILE,
        clock: Callable[[], float] = time.time,
        alive: Callable[[int], bool] = pid_alive,
    ) -> None:
        self._path = path
        self._clock = clock
        self._alive = alive
        self._by_key: dict[str, Terminal] = {}
        self._offset = 0
        self._last_liveness = 0.0
        # chamado a cada evento de um terminal (o controle das abas resolve pedidos por aqui)
        self.listener: Callable[[Terminal, str], None] = lambda t, evento: None
        self.socket = "jarvis"  # socket do tmux do Jarvis (eventos de painéis dele)
        self._pane_session: dict[str, str] = {}
        self._deferred: list[tuple[float, dict[str, Any]]] = []

    # --- leitura do arquivo

    def load(self) -> None:
        """Na subida: reconstrói o estado com o que já está no arquivo, sem avisos."""
        self._compact()
        for item in self._read_new():
            self.apply(item)
        self.tick(force_liveness=True)

    def poll(self) -> tuple[bool, list[dict[str, Any]]]:
        """Eventos novos desde a última leitura: (mudou?, avisos)."""
        alerts: list[dict[str, Any]] = []
        changed = False
        for item in self._read_new():
            changed = True
            alert = self.apply(item)
            if alert:
                alerts.append(alert)
        changed = self.tick() or changed
        return changed, alerts

    def _read_new(self) -> list[dict[str, Any]]:
        try:
            size = self._path.stat().st_size
        except FileNotFoundError:
            return []
        if size < self._offset:  # arquivo reduzido ou recriado
            self._offset = 0
        if size == self._offset:
            return []
        with self._path.open("rb") as f:
            f.seek(self._offset)
            data = f.read()
        end = data.rfind(b"\n") + 1  # só linhas completas
        self._offset += end
        items = []
        for line in data[:end].splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                items.append(item)
        return items

    def _compact(self) -> None:
        try:
            if self._path.stat().st_size <= MAX_BYTES:
                return
            lines = self._path.read_bytes().splitlines(keepends=True)[-KEEP_LINES:]
            tmp = self._path.with_suffix(".tmp")
            tmp.write_bytes(b"".join(lines))
            os.chmod(tmp, 0o600)
            tmp.replace(self._path)
            self._offset = 0
        except FileNotFoundError:
            return

    # --- estado

    def _key_for(self, item: dict[str, Any]) -> str | None:
        painel = str(item.get("painel") or "")
        if item.get("socket") == self.socket and painel:
            sessao = self._pane_session.get(painel)
            return f"tmux:{sessao}" if sessao else None  # painel ainda não listado: adia
        pid = item.get("pid") if isinstance(item.get("pid"), int) else None
        return f"pid:{pid}" if pid else f"s:{item.get('sessao', '')}"

    def apply(self, item: dict[str, Any]) -> dict[str, Any] | None:
        event = str(item.get("evento", ""))
        pid = item.get("pid") if isinstance(item.get("pid"), int) else None
        sessao = str(item.get("sessao", ""))
        now = float(item.get("t") or self._clock())
        key = self._key_for(item)
        if key is None:
            self._deferred.append((self._clock(), item))
            return None
        t = self._by_key.get(key)
        if t is None:
            if event == "SessionEnd" or key.startswith("tmux:"):
                return None
            t = Terminal(
                numero=self._free_number(),
                pasta=folder(str(item.get("pasta", ""))),
                desde=now,
                estado=WORKING,
                sessao=sessao,
                pid=pid,
                chave=key,
            )
            self._by_key[key] = t
        t.visto = now
        t.sessao = sessao or t.sessao
        self.listener(t, event)
        if item.get("pasta") and not t.tmux:
            t.pasta = folder(str(item["pasta"]))
        if t.tmux and event != "SessionEnd":
            t.tipo, t.pid = "claude", pid or t.pid  # Claude Code rodando neste terminal

        if event == "SessionStart":
            t.fim = None
            return self._set(t, WAITING, now)
        if event in ("UserPromptSubmit", "PostToolUse", "PostToolUseFailure"):
            return self._set(t, WORKING, now)
        if event == "PermissionRequest":
            t.ferramenta = str(item.get("ferramenta", ""))
            t.resumo = str(item.get("resumo", ""))
            self._set(t, PERMISSION, now)
            # terminal compartilhado: o aviso (com botões) sai do pedido do hook, não daqui
            return None if t.tmux else self._alert(t, "permissao")
        if event == "Notification" and item.get("tipo") == "idle_prompt":
            self._set(t, WAITING, now)
            return self._alert(t, "espera")
        if event == "Stop":
            self._set(t, DONE, now)
            return self._alert(t, "terminou")
        if event == "SessionEnd":
            if t.tmux:  # o Claude Code saiu; o terminal continua, com o shell
                t.tipo, t.pid = "shell", None
                self._set(t, FREE if t.comando in SHELLS else RUNNING, now)
            elif t.pid is None:
                del self._by_key[key]
            else:
                t.fim = now
        return None

    def tick(self, force_liveness: bool = False) -> bool:
        now = self._clock()
        changed = False
        for key, t in list(self._by_key.items()):
            if t.estado == PERMISSION and not t.pedido and now - t.mudou > PERMISSION_TTL:
                self._set(t, WORKING, now)  # a permissão foi (provavelmente) respondida
                changed = True
            if t.tmux:  # some quando a sessão do tmux some (sync_tmux)
                if t.tipo == "claude" and t.pid and not self._alive(t.pid):
                    t.tipo, t.pid = "shell", None
                    self._set(t, FREE if t.comando in SHELLS else RUNNING, now)
                    changed = True
                continue
            gone = now - t.visto > STALE_AFTER
            if t.fim is not None and now - t.fim > END_GRACE and t.pid and not self._alive(t.pid):
                gone = True
            if gone:
                del self._by_key[key]
                changed = True
        if force_liveness or now - self._last_liveness > LIVENESS_EVERY:
            self._last_liveness = now
            for key, t in list(self._by_key.items()):
                if not t.tmux and t.pid and not self._alive(t.pid):
                    del self._by_key[key]
                    changed = True
        return changed

    # --- terminais compartilhados (tmux)

    def sync_tmux(
        self, panes: list[Any], own_clients: dict[str, int] | None = None
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Atualiza pela lista do tmux. `own_clients`: clientes que são abas do Jarvis visíveis
        (o resto dos clientes conectados são janelas do Terminal.app). Devolve (mudou?, avisos
        dos eventos que esperavam o painel aparecer)."""
        own = own_clients or {}
        now = self._clock()
        changed = False
        alive = set()
        self._pane_session = {p.painel: p.sessao for p in panes}
        for p in panes:
            key = f"tmux:{p.sessao}"
            alive.add(key)
            t = self._by_key.get(key)
            if t is None:
                t = Terminal(
                    numero=self._free_number(),
                    pasta=folder(p.pasta),
                    desde=p.criada or now,
                    estado=FREE,
                    sessao="",
                    pid=None,
                    chave=key,
                    tipo="shell",
                    tmux=p.sessao,
                    mudou=now,
                    visto=now,
                )
                self._by_key[key] = t
                changed = True
            before = (t.pasta, t.comando, t.origem, t.aba, t.janela, t.estado, t.painel)
            t.painel, t.origem, t.aba, t.comando = p.painel, p.origem, p.aba, p.comando
            t.pasta = folder(p.pasta)
            t.janela = p.clientes - own.get(p.sessao, 0) > 0
            t.visto = now
            if t.tipo == "shell":
                t.estado = FREE if p.shell_livre else RUNNING
            if before != (t.pasta, t.comando, t.origem, t.aba, t.janela, t.estado, t.painel):
                changed = True
        for key in [k for k, t in self._by_key.items() if t.tmux and k not in alive]:
            del self._by_key[key]
            changed = True
        alerts: list[dict[str, Any]] = []
        deferred, self._deferred = self._deferred, []
        for at, item in deferred:
            if now - at > DEFER_FOR:
                continue
            changed = True
            alert = self.apply(item)
            if alert:
                alerts.append(alert)
        return changed, alerts

    def pane_key(self, painel: str) -> str | None:
        """Chave do terminal compartilhado de um painel do tmux (pela última leitura)."""
        sessao = self._pane_session.get(painel)
        return f"tmux:{sessao}" if sessao else None

    def by_key(self, key: str) -> Terminal | None:
        return self._by_key.get(key)

    def by_numero(self, numero: int) -> Terminal | None:
        return next((t for t in self._by_key.values() if t.numero == numero), None)

    def claude_count(self) -> int:
        """Claude Code rodando nos terminais compartilhados (para o limite)."""
        return sum(1 for t in self._by_key.values() if t.tmux and t.tipo == "claude")

    def open_request(self, key: str, pedido: str, ferramenta: str, resumo: str) -> Terminal | None:
        t = self._by_key.get(key)
        if t is None:
            return None
        t.pedido = pedido
        t.tipo = "claude"
        t.ferramenta, t.resumo = ferramenta, resumo
        t.estado, t.mudou = PERMISSION, self._clock()
        return t

    def close_request(self, key: str, pedido: str) -> bool:
        """O pedido foi resolvido: volta a "trabalhando" se ainda estava pedindo."""
        t = self._by_key.get(key)
        if t is None or t.pedido != pedido:
            return False
        t.pedido = ""
        if t.estado == PERMISSION:
            self._set(t, WORKING, self._clock())
        return True

    def alert_for(self, t: Terminal) -> dict[str, Any]:
        return self._alert(t, "permissao") | {"pedido": t.pedido, "chave": t.chave}

    def snapshot(self) -> list[dict[str, Any]]:
        return [t.view() for t in sorted(self._by_key.values(), key=lambda t: t.numero)]

    def _free_number(self) -> int:
        used = {t.numero for t in self._by_key.values()}
        n = 1
        while n in used:
            n += 1
        return n

    def _set(self, t: Terminal, estado: str, now: float) -> None:
        if estado != PERMISSION:
            t.ferramenta = t.resumo = ""
        t.estado = estado
        t.mudou = now

    def _alert(self, t: Terminal, kind: str) -> dict[str, Any]:
        return {
            "tipo": kind,
            "numero": t.numero,
            "pasta": t.pasta,
            "ferramenta": t.ferramenta,
            "resumo": t.resumo,
            "texto": alert_text(t, kind),
        }
