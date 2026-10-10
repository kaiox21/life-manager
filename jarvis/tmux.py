"""Terminais compartilhados: o tmux do Jarvis (socket `jarvis`, configuração própria).

Cada terminal é uma sessão desse tmux. O Terminal.app e o Jarvis se conectam à mesma sessão
(openspec/changes/jarvis-terminais-controle, design, decisões 2 a 8). Só comandos fixos, com
argumentos em lista (nunca shell). O `tmux` é sempre chamado com ambiente mínimo: o processo que
inicia o servidor define o ambiente de todos os terminais, e segredos do cérebro não podem vazar.
"""

import asyncio
import contextlib
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

SOCKET = "jarvis"
CONF = Path.home() / "Library/Application Support/Jarvis/tmux.conf"
TMUX_CANDIDATES = ("/opt/homebrew/bin/tmux", "/usr/local/bin/tmux")
SHELLS = {"zsh", "-zsh", "bash", "-bash", "sh", "-sh", "fish", "-fish"}
SEP = "\x1f"  # separador de campos na saída do tmux (não aparece em caminhos)
FIELDS = (
    "session_id",
    "pane_id",
    "pane_pid",
    "pane_current_path",
    "pane_current_command",
    "session_attached",
    "session_created",
    "@jarvis_origem",
    "@jarvis_aba",
)


def find_tmux() -> str | None:
    for path in TMUX_CANDIDATES:
        if os.access(path, os.X_OK):
            return path
    return shutil.which("tmux")


def minimal_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: os.environ[k] for k in ("HOME", "USER", "LOGNAME", "TMPDIR") if os.environ.get(k)}
    env.setdefault("HOME", str(Path.home()))
    env["LANG"] = os.environ.get("LANG") or "pt_BR.UTF-8"
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    env["TERM"] = "xterm-256color"
    return env | (extra or {})


@dataclass(frozen=True)
class Pane:
    """Um terminal (sessão do tmux), pelo seu primeiro painel."""

    sessao: str  # session_id, ex.: "$3"
    painel: str  # pane_id, ex.: "%5"
    pid: int  # do shell do painel
    pasta: str
    comando: str  # pane_current_command ("zsh", "npm", "2.1.296" para o claude…)
    clientes: int  # clientes conectados (janelas do Terminal.app + abas do Jarvis visíveis)
    criada: float
    origem: str  # "terminal" | "jarvis" | ""
    aba: bool

    @property
    def shell_livre(self) -> bool:
        return self.comando in SHELLS


def parse_panes(out: str) -> list[Pane]:
    seen: dict[str, Pane] = {}
    for line in out.splitlines():
        parts = line.split(SEP)
        if len(parts) != len(FIELDS):
            continue
        sessao, painel, pid, pasta, comando, clientes, criada, origem, aba = parts
        if sessao in seen:  # vários painéis: vale o primeiro (o Jarvis não cria divisões)
            continue
        try:
            seen[sessao] = Pane(
                sessao,
                painel,
                int(pid),
                pasta,
                comando,
                int(clientes or 0),
                float(criada or 0),
                origem,
                aba == "1",
            )
        except ValueError:
            continue
    return list(seen.values())


class Tmux:
    def __init__(
        self,
        binary: str | None = None,
        socket: str = SOCKET,
        conf: Path | None = CONF,
    ) -> None:
        self.binary = find_tmux() if binary is None else binary  # "" = sem tmux
        self.socket = socket
        self.conf = conf

    @property
    def available(self) -> bool:
        return bool(self.binary)

    def base(self) -> list[str]:
        argv = [str(self.binary), "-L", self.socket]
        if self.conf is not None and self.conf.exists():
            argv += ["-f", str(self.conf)]
        return argv

    async def run(self, *args: str, stdin: bytes | None = None) -> tuple[int, str]:
        if not self.binary:
            return 127, ""
        proc = await asyncio.create_subprocess_exec(
            *self.base(),
            *args,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=minimal_env(),
        )
        try:
            out, _err = await asyncio.wait_for(proc.communicate(stdin), timeout=10)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            return 124, ""
        return proc.returncode or 0, out.decode(errors="replace")

    # --- leitura

    async def panes(self) -> list[Pane]:
        """Terminais do socket. Sem tmux ou sem servidor: lista vazia."""
        fmt = SEP.join("#{" + f + "}" for f in FIELDS)
        code, out = await self.run("list-panes", "-a", "-F", fmt)
        return parse_panes(out) if code == 0 else []

    # --- sessões

    async def new_session(self, pasta: Path, cols: int = 120, rows: int = 32) -> str | None:
        code, out = await self.run(
            "new-session",
            "-d",
            "-P",
            "-F",
            "#{session_id}",
            "-c",
            str(pasta),
            "-x",
            str(cols),
            "-y",
            str(rows),
        )
        sessao = out.strip()
        if code != 0 or not sessao:
            return None
        await self.set_option(sessao, "@jarvis_origem", "jarvis")
        return sessao

    async def set_option(self, sessao: str, name: str, value: str) -> bool:
        code, _ = await self.run("set-option", "-t", sessao, name, value)
        return code == 0

    async def unset_option(self, sessao: str, name: str) -> bool:
        code, _ = await self.run("set-option", "-u", "-t", sessao, name)
        return code == 0

    async def kill(self, sessao: str) -> bool:
        code, _ = await self.run("kill-session", "-t", sessao)
        return code == 0

    # --- escrever

    async def send_command(self, painel: str, command: str) -> bool:
        """Comando de uma linha num shell livre: apaga a linha pela metade (Ctrl+E, Ctrl+U),
        digita o texto literal e aperta Enter."""
        if "\n" in command or "\r" in command:
            return False
        c1, _ = await self.run("send-keys", "-t", painel, "C-e", "C-u")
        c2, _ = await self.run("send-keys", "-t", painel, "-l", command)
        c3, _ = await self.run("send-keys", "-t", painel, "Enter")
        return c1 == c2 == c3 == 0

    async def send_message(self, painel: str, text: str) -> bool:
        """Mensagem ao Claude Code: colagem (bracketed paste) e Enter."""
        buffer = "jarvis-" + painel.lstrip("%")
        c1, _ = await self.run("load-buffer", "-b", buffer, "-", stdin=text.encode())
        c2, _ = await self.run("paste-buffer", "-p", "-d", "-b", buffer, "-t", painel)
        await asyncio.sleep(0.15)  # o Claude Code processa a colagem antes do Enter
        c3, _ = await self.run("send-keys", "-t", painel, "Enter")
        return c1 == c2 == c3 == 0

    def attach_argv(self, sessao: str) -> list[str]:
        """Linha de comando do cliente de uma aba (roda num pty do cérebro)."""
        return [*self.base(), "attach-session", "-t", sessao]
