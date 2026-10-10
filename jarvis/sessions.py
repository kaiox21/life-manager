"""Abas de terminal: pastas permitidas, limite de memória, limpeza de texto e o cliente da aba.

O cliente de uma aba é um pty do cérebro rodando `tmux attach` na sessão daquele terminal
(openspec/changes/jarvis-terminais-controle, design, decisão 5). O tmux redesenha a tela ao
conectar: não há tela guardada nem reprodução (a reprodução fazia o xterm responder de novo às
perguntas do terminal, e a resposta chegava como Esc).
"""

import asyncio
import contextlib
import fcntl
import logging
import os
import re
import signal
import struct
import subprocess
import termios
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MAX_TEXT = 4000
DEFAULT_ROOTS = ("~/Projetos pessoais", "~/AmicusIA", "~/Faculdade")
MAX_DEPTH = 2
SKIP_DIRS = {"node_modules", "__pycache__", "Library", "target", "dist", "build"}
# Controles fora: tudo < 0x20 menos \t e \n, o DEL e os controles C1 (0x80–0x9f).
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def clean_text(text: str) -> str:
    """Texto puro para mandar a uma sessão: sem teclas de controle, até 4.000 caracteres."""
    return _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))[:MAX_TEXT].strip()


def memory_level() -> int | None:
    """% de memória livre segundo o macOS (`kern.memorystatus_level`); None se não der."""
    try:
        out = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "kern.memorystatus_level"],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
        return int(out.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _make_controlling_tty() -> None:  # roda no filho, depois do setsid
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


def spawn_pty(
    argv: list[str], cwd: Path, env: dict[str, str], slave: int
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        argv,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=cwd,
        env=env,
        start_new_session=True,
        preexec_fn=_make_controlling_tty,
        close_fds=True,
    )


def set_size(fd: int, cols: int, rows: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class Folders:
    """Pastas onde o Jarvis pode abrir uma sessão: as raízes e até 2 níveis abaixo."""

    def __init__(self, roots: list[Path]) -> None:
        self.roots = [Path(os.path.realpath(r.expanduser())) for r in roots]

    @classmethod
    def from_env(cls, value: str) -> "Folders":
        parts = [p for p in (value.split(os.pathsep) if value else DEFAULT_ROOTS) if p.strip()]
        return cls([Path(p.strip()) for p in parts])

    def allowed(self, path: Path) -> bool:
        real = Path(os.path.realpath(path))
        for root in self.roots:
            if real == root or root in real.parents:
                depth = len(real.relative_to(root).parts)
                return depth <= MAX_DEPTH and real.is_dir()
        return False

    def resolve(self, name: str) -> dict[str, Any]:
        """{"pasta": Path} | {"opcoes": [...]} | {"erro": "..."}"""
        name = name.strip()
        if not name:
            return {"erro": "Diga a pasta onde abrir a sessão."}
        if name.startswith(("/", "~")):
            path = Path(os.path.realpath(Path(name).expanduser()))
            if self.allowed(path):
                return {"pasta": path}
            return {"erro": f"{name} está fora das pastas permitidas.", "permitidas": self.shown()}
        found = [p for p in self._walk() if p.name.casefold() == name.casefold()]
        found = [p for p in found if self.allowed(p)]
        if len(found) == 1:
            return {"pasta": found[0]}
        if found:
            return {"opcoes": [self.short(p) for p in found]}
        return {
            "erro": f"Não achei a pasta {name!r} nas pastas permitidas.",
            "permitidas": self.shown(),
        }

    def _walk(self) -> list[Path]:
        out: list[Path] = []
        level = [r for r in self.roots if r.is_dir()]
        out += level
        for _ in range(MAX_DEPTH):
            nxt: list[Path] = []
            for d in level:
                with contextlib.suppress(OSError):
                    nxt += [
                        c
                        for c in d.iterdir()
                        if c.is_dir() and not c.name.startswith(".") and c.name not in SKIP_DIRS
                    ]
            out += nxt
            level = nxt
        return out

    def shown(self) -> list[str]:
        return [self.short(r) for r in self.roots]

    @staticmethod
    def short(path: Path) -> str:
        home = Path.home()
        return "~/" + str(path.relative_to(home)) if home in path.parents else str(path)


class PtyClient:
    """Um processo num pty, com a saída entregue a `on_output` e o fim a `on_exit`.

    Usado para o cliente `tmux attach` de uma aba: abre ao anexar, fecha ao desanexar.
    """

    def __init__(
        self,
        argv: list[str],
        env: dict[str, str],
        cwd: Path,
        on_output: Callable[[bytes], None],
        on_exit: Callable[[], None],
        cols: int = 120,
        rows: int = 32,
        spawn: Callable[..., subprocess.Popen[bytes]] = spawn_pty,
    ) -> None:
        self._on_output = on_output
        self._on_exit = on_exit
        self.paused = False
        self.closed = False
        master, slave = os.openpty()
        try:
            set_size(slave, cols, rows)
            self.proc = spawn(argv, cwd, env, slave)
        except Exception:
            os.close(master)
            raise
        finally:
            os.close(slave)
        os.set_blocking(master, False)
        self.fd = master
        asyncio.get_running_loop().add_reader(master, self._readable)

    @property
    def pid(self) -> int:
        return self.proc.pid

    def _readable(self) -> None:
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return
        except OSError:  # EIO: o processo saiu
            data = b""
        if not data:
            self._finish()
            return
        self._on_output(data)

    def write(self, data: bytes) -> bool:
        if self.closed:
            return False
        try:
            os.write(self.fd, data)
        except BlockingIOError:
            asyncio.get_running_loop().call_later(0.05, self.write, data)
        except OSError:
            return False
        return True

    def resize(self, cols: int, rows: int) -> None:
        if self.closed or not (2 <= cols <= 1000 and 2 <= rows <= 500):
            return
        with contextlib.suppress(OSError):
            set_size(self.fd, cols, rows)

    def pause(self, on: bool) -> None:
        """Controle de fluxo: a interface está atrasada (pausa) ou alcançou (retoma)."""
        if self.closed or self.paused == on:
            return
        loop = asyncio.get_running_loop()
        self.paused = on
        if on:
            loop.remove_reader(self.fd)
        else:
            loop.add_reader(self.fd, self._readable)

    async def close(self, grace: float = 2.0) -> None:
        if self.closed:
            return
        with contextlib.suppress(OSError):
            os.killpg(self.proc.pid, signal.SIGHUP)  # o cliente do tmux desconecta e sai
        for _ in range(int(grace * 10)):
            if self.proc.poll() is not None:
                break
            await asyncio.sleep(0.1)
        if self.proc.poll() is None:
            with contextlib.suppress(OSError):
                os.killpg(self.proc.pid, signal.SIGKILL)
        self._finish()

    def _finish(self) -> None:
        if self.closed:
            return
        self.closed = True
        if not self.paused:
            asyncio.get_running_loop().remove_reader(self.fd)
        with contextlib.suppress(OSError):
            os.close(self.fd)
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.proc.wait(timeout=1)
        self._on_exit()
