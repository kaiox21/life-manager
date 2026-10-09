"""Sessões do Claude Code abertas pelo Jarvis, cada uma num terminal real (pty).

O `claude` sobe por `zsh -l -i -c 'exec ...'`: o shell de login dá o PATH do Kaio (sem ele,
os hooks dos plugins que chamam `node` quebram), e o `exec` faz o filho do pty ser o próprio
`claude`, o mesmo pid que os hooks globais anotam (openspec/changes/jarvis-terminais-controle,
design, decisão 3). O ambiente é mínimo de propósito: segredos do cérebro (chaves de API) não
vão para a sessão, que usa o login do próprio Claude Code.
"""

import asyncio
import contextlib
import fcntl
import json
import logging
import os
import re
import secrets
import signal
import struct
import subprocess
import termios
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

TABS_FILE = Path.home() / "Library/Application Support/Jarvis/abas.json"
BUFFER_BYTES = 512 * 1024
MAX_TEXT = 4000
PASTE_START, PASTE_END = b"\x1b[200~", b"\x1b[201~"
DEFAULT_ROOTS = ("~/Projetos pessoais", "~/AmicusIA", "~/Faculdade")
MAX_DEPTH = 2
SKIP_DIRS = {"node_modules", "__pycache__", "Library", "target", "dist", "build"}
# Controles fora: tudo < 0x20 menos \t e \n, o DEL e os controles C1 (0x80–0x9f).
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")

Spawn = Callable[[list[str], Path, dict[str, str], int], subprocess.Popen[bytes]]


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


def login_command(claude: str, args: list[str]) -> list[str]:
    return ["/bin/zsh", "-l", "-i", "-c", 'exec "$0" "$@"', claude, *args]


def base_env(extra: dict[str, str]) -> dict[str, str]:
    env = {
        k: os.environ[k]
        for k in ("HOME", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL")
        if os.environ.get(k)
    }
    env.setdefault("HOME", str(Path.home()))
    env.setdefault("LANG", "pt_BR.UTF-8")
    env |= {
        "SHELL": "/bin/zsh",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
    }
    return env | extra


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


@dataclass
class Session:
    sid: str
    pasta: Path
    pid: int
    fd: int
    proc: subprocess.Popen[bytes]
    hook_token: str
    numero: int = 0
    sessao: str = ""  # session_id do Claude Code (vem dos hooks globais)
    criada: float = field(default_factory=time.time)
    buffer: bytearray = field(default_factory=bytearray)
    paused: bool = False
    closing: bool = False

    def remember(self, data: bytes) -> None:
        self.buffer += data
        if len(self.buffer) > BUFFER_BYTES:
            del self.buffer[: len(self.buffer) - BUFFER_BYTES]


@dataclass
class Closed:
    """Aba de uma sessão que acabou (reinício do cérebro ou o `claude` saiu): pode retomar."""

    sid: str
    pasta: Path
    numero: int
    sessao: str


class Sessions:
    def __init__(
        self,
        folders: Folders,
        *,
        claude: str = str(Path.home() / ".local/bin/claude"),
        command: Callable[[str, list[str]], list[str]] = login_command,
        spawn: Spawn = spawn_pty,
        max_sessions: int = 4,
        min_memory: int = 20,
        memory: Callable[[], int | None] = memory_level,
        tabs_file: Path | None = TABS_FILE,
        claude_args: list[str] | None = None,
    ) -> None:
        self.folders = folders
        self._claude = claude
        self._command = command
        self._spawn = spawn
        self.max_sessions = max_sessions
        self.min_memory = min_memory
        self._memory = memory
        self._tabs_file = tabs_file
        self._claude_args = list(claude_args or [])
        self.open: dict[str, Session] = {}
        self.closed: dict[str, Closed] = {}
        # callbacks ligados pelo controle
        self.on_output: Callable[[Session, bytes], None] = lambda s, d: None
        self.on_exit: Callable[[Session], None] = lambda s: None

    # --- abrir

    def can_open(self) -> str | None:
        """Motivo para recusar uma sessão nova, ou None."""
        if len(self.open) >= self.max_sessions:
            return (
                f"Já há {len(self.open)} sessões abertas pelo Jarvis (o limite é "
                f"{self.max_sessions}). Feche uma aba antes."
            )
        level = self._memory()
        if level is not None and level < self.min_memory:
            return (
                f"O Mac está com pouca memória livre ({level}%). Feche algo antes de abrir "
                "outra sessão."
            )
        return None

    def start(
        self,
        pasta: Path,
        settings: Callable[[str], str],
        resume: str | None = None,
        cont: bool = False,
    ) -> Session:
        """Abre o `claude` num pty. `settings(token)` devolve o JSON do `--settings`."""
        refusal = self.can_open()
        if refusal:
            raise RuntimeError(refusal)
        if not self.folders.allowed(pasta):
            raise RuntimeError(f"{pasta} está fora das pastas permitidas.")
        sid = secrets.token_hex(4)
        token = secrets.token_urlsafe(24)
        args = [*self._claude_args, "--settings", settings(token)]
        if resume:
            args += ["--resume", resume]
        elif cont:
            args.append("--continue")
        master, slave = os.openpty()
        try:
            set_size(slave, 120, 32)
            env = base_env({"JARVIS_TERMINAL": sid, "JARVIS_HOOK_TOKEN": token})
            proc = self._spawn(self._command(self._claude, args), pasta, env, slave)
        except Exception:
            os.close(master)
            raise
        finally:
            os.close(slave)
        os.set_blocking(master, False)
        session = Session(
            sid=sid, pasta=pasta, pid=proc.pid, fd=master, proc=proc, hook_token=token
        )
        self.open[sid] = session
        asyncio.get_running_loop().add_reader(master, self._readable, session)
        log.info("sessão %s aberta em %s (pid %d)", sid, pasta, proc.pid)
        return session

    # --- entrada e saída

    def _readable(self, s: Session) -> None:
        try:
            data = os.read(s.fd, 65536)
        except BlockingIOError:
            return
        except OSError:  # EIO: o outro lado do pty fechou
            data = b""
        if not data:
            self._finish(s)
            return
        s.remember(data)
        self.on_output(s, data)

    def pause(self, sid: str, on: bool) -> None:
        """Controle de fluxo: a interface está atrasada (pausa) ou alcançou (retoma)."""
        s = self.open.get(sid)
        if s is None or s.paused == on:
            return
        loop = asyncio.get_running_loop()
        s.paused = on
        if on:
            loop.remove_reader(s.fd)
        else:
            loop.add_reader(s.fd, self._readable, s)

    def write(self, sid: str, data: bytes) -> bool:
        s = self.open.get(sid)
        if s is None:
            return False
        try:
            os.write(s.fd, data)
        except BlockingIOError:
            # pty cheio (raro: teclas e textos curtos); tenta de novo daqui a pouco
            asyncio.get_running_loop().call_later(0.05, self.write, sid, data)
        except OSError:
            return False
        return True

    async def send_text(self, sid: str, text: str) -> str:
        """Cola o texto (bracketed paste) e aperta Enter. Devolve o texto enviado."""
        clean = clean_text(text)
        if not clean or not self.write(sid, PASTE_START + clean.encode() + PASTE_END):
            return ""
        await asyncio.sleep(0.15)  # o Claude Code processa a colagem antes do Enter
        self.write(sid, b"\r")
        return clean

    def resize(self, sid: str, cols: int, rows: int) -> None:
        s = self.open.get(sid)
        if s is None or not (2 <= cols <= 1000 and 2 <= rows <= 500):
            return
        with contextlib.suppress(OSError):
            set_size(s.fd, cols, rows)

    def redraw(self, sid: str) -> None:
        """Pede ao `claude` para redesenhar a tela (SIGWINCH), ao anexar uma aba."""
        s = self.open.get(sid)
        if s is not None:
            with contextlib.suppress(OSError):
                os.killpg(s.pid, signal.SIGWINCH)

    # --- fechar

    async def close(self, sid: str, grace: float = 5.0) -> bool:
        s = self.open.get(sid)
        if s is None:
            return self.closed.pop(sid, None) is not None
        s.closing = True
        with contextlib.suppress(OSError):
            os.killpg(s.pid, signal.SIGHUP)
        for _ in range(int(grace * 10)):
            if s.proc.poll() is not None:
                break
            await asyncio.sleep(0.1)
        if s.proc.poll() is None:
            with contextlib.suppress(OSError):
                os.killpg(s.pid, signal.SIGKILL)
        self._finish(s)
        return True

    def _finish(self, s: Session) -> None:
        if self.open.pop(s.sid, None) is None:
            return
        loop = asyncio.get_running_loop()
        if not s.paused:
            loop.remove_reader(s.fd)
        with contextlib.suppress(OSError):
            os.close(s.fd)
        with contextlib.suppress(subprocess.TimeoutExpired):
            s.proc.wait(timeout=1)
        if not s.closing:  # o `claude` saiu sozinho: a aba fica, com "Retomar"
            self.closed[s.sid] = Closed(s.sid, s.pasta, s.numero, s.sessao)
        log.info("sessão %s encerrada", s.sid)
        self.save()
        self.on_exit(s)

    async def shutdown(self) -> None:
        """Cérebro parando: grava as abas (para "Retomar") e encerra as sessões."""
        self.save(including_open=True)
        for sid in list(self.open):
            s = self.open[sid]
            s.closing = True
            with contextlib.suppress(OSError):
                os.killpg(s.pid, signal.SIGHUP)
        await asyncio.sleep(0)

    # --- abas da execução anterior

    def save(self, including_open: bool = True) -> None:
        if self._tabs_file is None:
            return
        items = [
            {"numero": c.numero, "pasta": str(c.pasta), "sessao": c.sessao}
            for c in self.closed.values()
        ]
        if including_open:
            items += [
                {"numero": s.numero, "pasta": str(s.pasta), "sessao": s.sessao}
                for s in self.open.values()
            ]
        self._tabs_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._tabs_file.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(items, f, ensure_ascii=False)
        tmp.replace(self._tabs_file)

    def load_previous(self) -> None:
        """Na subida: as abas que estavam abertas viram "encerradas", com "Retomar"."""
        if self._tabs_file is None:
            return
        try:
            items = json.loads(self._tabs_file.read_text())
        except (OSError, ValueError):
            return
        for item in items if isinstance(items, list) else []:
            try:
                pasta = Path(str(item["pasta"]))
            except (KeyError, TypeError):
                continue
            if not self.folders.allowed(pasta):
                continue
            sid = secrets.token_hex(4)
            self.closed[sid] = Closed(
                sid, pasta, int(item.get("numero") or 0), str(item.get("sessao") or "")
            )
        self.save()

    # --- vista para a interface

    def tabs(self) -> list[dict[str, Any]]:
        out = [
            {"sid": s.sid, "numero": s.numero, "pasta": s.pasta.name, "aberta": True, "pid": s.pid}
            for s in self.open.values()
        ]
        out += [
            {"sid": c.sid, "numero": c.numero, "pasta": c.pasta.name, "aberta": False}
            for c in self.closed.values()
        ]
        return sorted(out, key=lambda t: (not t["aberta"], t["numero"]))

    def by_token(self, token: str) -> Session | None:
        for s in self.open.values():
            if secrets.compare_digest(s.hook_token, token):
                return s
        return None

    def by_pid(self, pid: int) -> Session | None:
        return next((s for s in self.open.values() if s.pid == pid), None)

    def by_numero(self, numero: int) -> Session | None:
        return next((s for s in self.open.values() if s.numero == numero), None)
