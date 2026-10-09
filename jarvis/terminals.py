"""Gerenciador de terminais: sessões do Claude Code deste Mac, numeradas, com avisos.

Lê o arquivo que os hooks (`jarvis/hooks/claude_event.py`) preenchem. Um terminal é um
processo `claude` (o `session_id` muda com /clear e ao retomar). Não existe evento no momento
em que o Kaio aprova uma permissão: "pedindo permissão" vale até o próximo evento da sessão
ou 20 s (openspec/specs/jarvis-terminais).

Sessões abertas pelo Jarvis (`aba`) têm o pedido de permissão acompanhado pelo hook HTTP
(`jarvis/permissions.py`): para elas o aviso sai do pedido, com botões, e o prazo de 20 s não
vale enquanto o pedido estiver aberto.
"""

import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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
    aba: str = ""  # id da sessão aberta pelo Jarvis (vazio = sessão de fora)
    pedido: str = ""  # pedido de permissão aberto no hook HTTP

    def view(self) -> dict[str, Any]:
        out = asdict(self)
        for k in ("mudou", "visto", "fim"):
            out.pop(k)
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

    def apply(self, item: dict[str, Any]) -> dict[str, Any] | None:
        event = str(item.get("evento", ""))
        pid = item.get("pid") if isinstance(item.get("pid"), int) else None
        sessao = str(item.get("sessao", ""))
        key = f"pid:{pid}" if pid else f"s:{sessao}"
        now = float(item.get("t") or self._clock())
        t = self._by_key.get(key)
        if t is None:
            if event == "SessionEnd":
                return None
            t = Terminal(
                numero=self._free_number(),
                pasta=folder(str(item.get("pasta", ""))),
                desde=now,
                estado=WORKING,
                sessao=sessao,
                pid=pid,
            )
            self._by_key[key] = t
        t.visto = now
        t.sessao = sessao or t.sessao
        self.listener(t, event)
        if item.get("pasta"):
            t.pasta = folder(str(item["pasta"]))

        if event == "SessionStart":
            t.fim = None
            return self._set(t, WAITING, now)
        if event in ("UserPromptSubmit", "PostToolUse", "PostToolUseFailure"):
            return self._set(t, WORKING, now)
        if event == "PermissionRequest":
            t.ferramenta = str(item.get("ferramenta", ""))
            t.resumo = str(item.get("resumo", ""))
            self._set(t, PERMISSION, now)
            # sessão com aba: o aviso (com botões) sai do pedido HTTP, não daqui
            return None if t.aba else self._alert(t, "permissao")
        if event == "Notification" and item.get("tipo") == "idle_prompt":
            self._set(t, WAITING, now)
            return self._alert(t, "espera")
        if event == "Stop":
            self._set(t, DONE, now)
            return self._alert(t, "terminou")
        if event == "SessionEnd":
            if t.pid is None:
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
            gone = now - t.visto > STALE_AFTER
            if t.fim is not None and now - t.fim > END_GRACE and t.pid and not self._alive(t.pid):
                gone = True
            if gone:
                del self._by_key[key]
                changed = True
        if force_liveness or now - self._last_liveness > LIVENESS_EVERY:
            self._last_liveness = now
            for key, t in list(self._by_key.items()):
                if t.pid and not self._alive(t.pid):
                    del self._by_key[key]
                    changed = True
        return changed

    # --- sessões abertas pelo Jarvis

    def register(self, pid: int, cwd: str, aba: str) -> Terminal:
        """Sessão aberta agora pelo Jarvis: ganha o número já (antes do 1º evento dos hooks)."""
        key = f"pid:{pid}"
        t = self._by_key.get(key)
        if t is None:
            now = self._clock()
            t = Terminal(
                self._free_number(), folder(cwd), now, WAITING, "", pid, mudou=now, visto=now
            )
            self._by_key[key] = t
        t.aba = aba
        return t

    def forget(self, pid: int) -> None:
        self._by_key.pop(f"pid:{pid}", None)

    def by_pid(self, pid: int) -> Terminal | None:
        return self._by_key.get(f"pid:{pid}")

    def open_request(self, pid: int, pedido: str, ferramenta: str, resumo: str) -> Terminal | None:
        t = self.by_pid(pid)
        if t is None:
            return None
        t.pedido = pedido
        t.ferramenta, t.resumo = ferramenta, resumo
        t.estado, t.mudou = PERMISSION, self._clock()
        return t

    def close_request(self, pid: int, pedido: str) -> bool:
        """O pedido foi resolvido: volta a "trabalhando" se ainda estava pedindo."""
        t = self.by_pid(pid)
        if t is None or t.pedido != pedido:
            return False
        t.pedido = ""
        if t.estado == PERMISSION:
            self._set(t, WORKING, self._clock())
        return True

    def alert_for(self, t: Terminal) -> dict[str, Any]:
        return self._alert(t, "permissao") | {"pedido": t.pedido, "aba": t.aba}

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
