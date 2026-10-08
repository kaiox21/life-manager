"""Ferramentas locais do macOS. Comandos fixos, argumentos validados, nunca shell.

Nenhuma ferramenta apaga arquivos, envia mensagens ou executa comandos arbitrários.
"""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger(__name__)

CONFIG_FILE = Path.home() / "Library/Application Support/Jarvis/config.json"
SAFE_NAME = re.compile(r"^[\w .&'()+-]{1,60}$")
MAX_CLIPBOARD = 2000


@dataclass(frozen=True)
class Completed:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str], bytes | None], Awaitable[Completed]]
Confirm = Callable[[str], Awaitable[bool]]


async def run_command(argv: list[str], stdin: bytes | None = None) -> Completed:
    """Executa sem shell: argv é passado direto ao sistema."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(proc.communicate(stdin), timeout=20)
    return Completed(
        proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")
    )


def load_config(path: Path = CONFIG_FILE) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AbrirAppArgs(Args):
    nome: str = Field(description="Nome do app. Ex.: 'Safari', 'Spotify'")


class BuscarArquivoArgs(Args):
    texto: str = Field(min_length=2, max_length=100, description="O que procurar (Spotlight)")


class RodarAtalhoArgs(Args):
    nome: str = Field(description="Nome do atalho do app Atalhos (só os permitidos)")


class MusicaArgs(Args):
    acao: Literal["tocar", "pausar", "proxima", "anterior"]


class TimerArgs(Args):
    minutos: int = Field(ge=1, le=720)
    texto: str = Field(default="Tempo!", max_length=100)


class ClipboardArgs(Args):
    acao: Literal["ler", "escrever"]
    texto: str | None = Field(default=None, max_length=MAX_CLIPBOARD)


SPOTIFY = {
    "tocar": 'tell application "Spotify" to play',
    "pausar": 'tell application "Spotify" to pause',
    "proxima": 'tell application "Spotify" to next track',
    "anterior": 'tell application "Spotify" to previous track',
}
# Texto do usuário vai como argv do AppleScript, nunca concatenado no script.
NOTIFY = [
    "osascript",
    "-e",
    "on run argv",
    "-e",
    'display notification (item 1 of argv) with title "Jarvis" sound name "Glass"',
    "-e",
    "end run",
]


class LocalTools:
    def __init__(
        self,
        runner: Runner = run_command,
        confirm: Confirm | None = None,
        config: dict[str, Any] | None = None,
        home: Path | None = None,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._run = runner
        self._confirm = confirm
        self._config = config if config is not None else load_config()
        self._home = home or Path.home()
        self._now = now
        self._timers: set[asyncio.Task[None]] = set()

    def set_confirm(self, confirm: Confirm) -> None:
        self._confirm = confirm

    # --- ferramentas

    async def abrir_app(self, a: AbrirAppArgs) -> dict[str, Any]:
        if not SAFE_NAME.match(a.nome):
            return {"erro": f"Nome de app inválido: {a.nome!r}"}
        r = await self._run(["open", "-a", a.nome], None)
        if r.returncode != 0:
            return {"erro": f"Não encontrei o app {a.nome!r}."}
        return {"status": "aberto", "app": a.nome}

    async def buscar_arquivo(self, a: BuscarArquivoArgs) -> dict[str, Any]:
        r = await self._run(["mdfind", "-onlyin", str(self._home), a.texto], None)
        paths = [p for p in r.stdout.splitlines() if p.strip()]
        home = str(self._home)
        shown = [("~" + p[len(home) :]) if p.startswith(home) else p for p in paths[:20]]
        return {"arquivos": shown, "total": len(paths)}

    async def rodar_atalho(self, a: RodarAtalhoArgs) -> dict[str, Any]:
        allowed = list(self._config.get("atalhos_permitidos") or [])
        if a.nome not in allowed:
            return {
                "erro": f"O atalho {a.nome!r} não está na lista permitida.",
                "permitidos": allowed,
            }
        r = await self._run(["shortcuts", "run", a.nome], None)
        if r.returncode != 0:
            return {"erro": f"O atalho {a.nome!r} falhou."}
        return {"status": "executado", "atalho": a.nome, "saida": r.stdout.strip()[:500]}

    async def controlar_musica(self, a: MusicaArgs) -> dict[str, Any]:
        r = await self._run(["osascript", "-e", SPOTIFY[a.acao]], None)
        if r.returncode != 0:
            return {"erro": "Não consegui controlar o Spotify (está instalado e aberto?)."}
        return {"status": "ok", "acao": a.acao}

    async def timer(self, a: TimerArgs) -> dict[str, Any]:
        when = self._now() + timedelta(minutes=a.minutos)

        async def fire() -> None:
            await asyncio.sleep(a.minutos * 60)
            await self._run([*NOTIFY, a.texto], None)

        task = asyncio.create_task(fire())
        self._timers.add(task)
        task.add_done_callback(self._timers.discard)
        return {"status": "agendado", "hora": when.strftime("%H:%M"), "texto": a.texto}

    async def area_transferencia(self, a: ClipboardArgs) -> dict[str, Any]:
        if a.acao == "escrever":
            if not a.texto:
                return {"erro": "Nada para copiar."}
            await self._run(["pbcopy"], a.texto.encode())
            return {"status": "copiado", "caracteres": len(a.texto)}
        if self._confirm is None or not await self._confirm(
            "Deixar o Jarvis ler a área de transferência?"
        ):
            return {
                "status": "negado",
                "erro": "O usuário não permitiu ler a área de transferência.",
            }
        r = await self._run(["pbpaste"], None)
        text = r.stdout
        return {"conteudo": text[:MAX_CLIPBOARD], "cortado": len(text) > MAX_CLIPBOARD}

    # --- catálogo para o modelo

    def catalog(
        self,
    ) -> dict[str, tuple[str, type[Args], Callable[[Any], Awaitable[dict[str, Any]]]]]:
        return {
            "abrir_app": (
                "Abre um aplicativo do Mac pelo nome. Ex.: nome='Safari'.",
                AbrirAppArgs,
                self.abrir_app,
            ),
            "buscar_arquivo": (
                "Procura arquivos na pasta pessoal (Spotlight); até 20.",
                BuscarArquivoArgs,
                self.buscar_arquivo,
            ),
            "rodar_atalho": (
                "Roda um atalho do app Atalhos, só se estiver na lista permitida.",
                RodarAtalhoArgs,
                self.rodar_atalho,
            ),
            "controlar_musica": (
                "Controla o Spotify: tocar, pausar, proxima, anterior.",
                MusicaArgs,
                self.controlar_musica,
            ),
            "timer": ("Avisa com uma notificação daqui a N minutos.", TimerArgs, self.timer),
            "area_transferencia": (
                "Lê (pede permissão) ou escreve na área de transferência.",
                ClipboardArgs,
                self.area_transferencia,
            ),
        }

    def openai_tools(self) -> list[dict[str, Any]]:
        out = []
        for name, (desc, model, _) in self.catalog().items():
            schema = model.model_json_schema()
            schema.pop("title", None)
            out.append(
                {
                    "type": "function",
                    "function": {"name": name, "description": desc, "parameters": schema},
                }
            )
        return out

    async def call(self, name: str, raw: dict[str, Any]) -> tuple[bool, dict[str, Any] | str]:
        """(válido?, resultado). Inválido = erro de validação para o modelo corrigir."""
        entry = self.catalog().get(name)
        if entry is None:
            return False, f"ferramenta local '{name}' não existe"
        _, model, fn = entry
        try:
            args = model.model_validate(raw)
        except ValidationError as exc:
            return False, "; ".join(
                f"{'.'.join(map(str, e['loc'])) or 'args'}: {e['msg']}" for e in exc.errors()
            )
        log.info("ferramenta local %s", name)
        return True, await fn(args)
