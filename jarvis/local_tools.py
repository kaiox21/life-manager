"""Ferramentas locais do macOS. Comandos fixos, argumentos validados, nunca shell.

Nenhuma ferramenta apaga arquivos, envia mensagens ou executa comandos arbitrários. Única
exceção (openspec/specs/ferramentas-locais, "Sem shell livre"): as ferramentas de terminal
abrem o `claude` numa pasta permitida e escrevem TEXTO PURO numa sessão aberta pelo Jarvis,
com confirmação do Kaio. Nenhuma responde a pedidos de permissão (isso só por clique).
"""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jarvis.spotify import LOGIN_COMMAND, Ducker, Spotify, SpotifyError

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


class SemArgs(Args):
    pass


class AbrirAppArgs(Args):
    nome: str = Field(description="Nome do app. Ex.: 'Safari', 'Spotify'")


class BuscarArquivoArgs(Args):
    texto: str = Field(min_length=2, max_length=100, description="O que procurar (Spotlight)")


class RodarAtalhoArgs(Args):
    nome: str = Field(description="Nome do atalho do app Atalhos (só os permitidos)")


class MusicaArgs(Args):
    acao: Literal["tocar", "pausar", "proxima", "anterior", "aleatorio", "repetir", "volume"]
    ligado: bool = Field(default=True, description="Para aleatorio e repetir: ligar ou desligar")
    volume: int | None = Field(default=None, ge=0, le=100, description="Para volume: 0 a 100")


class TocarMusicaArgs(Args):
    pedido: str = Field(
        min_length=1,
        max_length=120,
        description="O que tocar, como o Kaio disse (pode incluir o artista para desambiguar)",
    )
    tipo: Literal["musica", "artista", "album", "playlist", "minha_playlist"] = Field(
        description="musica, artista, album, playlist (do catálogo) ou minha_playlist (do Kaio)"
    )


class TimerArgs(Args):
    minutos: int = Field(ge=1, le=720)
    texto: str = Field(default="Tempo!", max_length=100)


class AbrirTerminalArgs(Args):
    claude: bool = Field(
        default=False,
        description="true = já abre o Claude Code; false = só um terminal (shell)",
    )
    pasta: str = Field(
        min_length=1,
        max_length=200,
        description="Pasta do projeto (ex.: 'life-manager') ou caminho dentro das permitidas",
    )


class MandarTerminalArgs(Args):
    numero: int = Field(ge=1, le=99, description="Número do terminal (Terminal 2 -> 2)")
    texto: str = Field(min_length=1, max_length=4000, description="Mensagem para o Claude Code")


class FecharTerminalArgs(Args):
    numero: int = Field(ge=1, le=99)


class TerminalControl(Protocol):
    async def open(self, pasta: str, claude: bool = False) -> dict[str, Any]: ...
    async def send(self, numero: int, texto: str, confirm: Confirm | None) -> dict[str, Any]: ...
    async def close(self, numero: int, confirm: Confirm | None) -> dict[str, Any]: ...


class ClipboardArgs(Args):
    acao: Literal["ler", "escrever"]
    texto: str | None = Field(default=None, max_length=MAX_CLIPBOARD)


SPOTIFY = {
    "tocar": 'tell application "Spotify" to play',
    "pausar": 'tell application "Spotify" to pause',
    "proxima": 'tell application "Spotify" to next track',
    "anterior": 'tell application "Spotify" to previous track',
}


def _spotify_error(e: SpotifyError) -> dict[str, Any]:
    out: dict[str, Any] = {"erro": str(e)}
    if e.login:  # o comando vai só para o cartão da tela (for_model tira as opções)
        out["opcoes"] = [LOGIN_COMMAND]
    return out


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
        terminals: Callable[[], list[dict[str, Any]]] | None = None,
        control: TerminalControl | None = None,
        spotify: Spotify | None = None,
        ducker: Ducker | None = None,
    ) -> None:
        self._run = runner
        self._confirm = confirm
        self._config = config if config is not None else load_config()
        self._home = home or Path.home()
        self._now = now
        self._timers: set[asyncio.Task[None]] = set()
        self._terminals = terminals or (lambda: [])
        self._control = control
        self._spotify = spotify
        self._ducker = ducker

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
        if a.acao in SPOTIFY:  # AppleScript: funciona sem o login e sem rede
            r = await self._run(["osascript", "-e", SPOTIFY[a.acao]], None)
            if r.returncode != 0:
                return {"erro": "Não consegui controlar o Spotify (está instalado e aberto?)."}
            return {"status": "ok", "acao": a.acao}
        if a.acao == "volume" and a.volume is None:
            return {"erro": "Diga o volume, de 0 a 100."}
        if self._spotify is None:
            return {"erro": "O Spotify não está configurado (falta SPOTIFY_CLIENT_ID no .env)."}
        try:
            if a.acao == "aleatorio":
                await self._spotify.shuffle(a.ligado)
            elif a.acao == "repetir":
                await self._spotify.repeat(a.ligado)
            else:
                assert a.volume is not None
                await self._spotify.volume(a.volume)
                if self._ducker is not None:
                    self._ducker.requested_volume(a.volume)
        except SpotifyError as e:
            return _spotify_error(e)
        out: dict[str, Any] = {"status": "ok", "acao": a.acao}
        out |= {"volume": a.volume} if a.acao == "volume" else {"ligado": a.ligado}
        return out

    async def tocar_musica(self, a: TocarMusicaArgs) -> dict[str, Any]:
        if self._spotify is None:
            return {"erro": "O Spotify não está configurado (falta SPOTIFY_CLIENT_ID no .env)."}
        try:
            found = await self._spotify.search(a.tipo, a.pedido)
            if found is None:
                what = "essa playlist entre as suas" if a.tipo == "minha_playlist" else "isso"
                return {"erro": f"Não encontrei {what} no Spotify: {a.pedido!r}."}
            await self._spotify.play(found)
        except SpotifyError as e:
            return _spotify_error(e)
        out = {"status": "tocando", "tipo": a.tipo, "nome": found["nome"]}
        if found.get("artista") and a.tipo in ("musica", "album"):
            out["artista"] = found["artista"]
        return out

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

    async def listar_terminais(self, _a: "SemArgs") -> dict[str, Any]:
        return {"terminais": self._terminals()}

    async def abrir_terminal(self, a: AbrirTerminalArgs) -> dict[str, Any]:
        if self._control is None:
            return {"erro": "As abas de terminal não estão disponíveis."}
        result = await self._control.open(a.pasta, a.claude)
        result.pop("sessao", None)
        return result

    async def mandar_terminal(self, a: MandarTerminalArgs) -> dict[str, Any]:
        if self._control is None:
            return {"erro": "As abas de terminal não estão disponíveis."}
        return await self._control.send(a.numero, a.texto, self._confirm)

    async def fechar_terminal(self, a: FecharTerminalArgs) -> dict[str, Any]:
        if self._control is None:
            return {"erro": "As abas de terminal não estão disponíveis."}
        return await self._control.close(a.numero, self._confirm)

    def for_model(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """O que o modelo recebe. Os resumos dos pedidos de permissão (comandos podem ter
        segredos) ficam só no cartão da tela."""
        if name in ("tocar_musica", "controlar_musica") and "opcoes" in data:
            return {k: v for k, v in data.items() if k != "opcoes"}
        if name == "listar_terminais":
            keep = ("numero", "pasta", "tipo", "estado", "ferramenta")
            return {"terminais": [{k: t.get(k) for k in keep} for t in data["terminais"]]}
        return data

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
                "Controla o Spotify: tocar (retomar), pausar, proxima, anterior, aleatorio e "
                "repetir (ligado=true/false) e volume (0 a 100). Para tocar algo pelo nome, use "
                "tocar_musica.",
                MusicaArgs,
                self.controlar_musica,
            ),
            "tocar_musica": (
                "Busca e toca no Spotify deste Mac algo pelo nome: tipo=musica ('toca Tempo "
                "Perdido'), artista ('toca Legião Urbana'), album ('toca o álbum Dois'), playlist "
                "(do catálogo) ou minha_playlist ('toca minha playlist de estudo'). Diga depois o "
                "que começou a tocar. Para pausar e pular, use controlar_musica.",
                TocarMusicaArgs,
                self.tocar_musica,
            ),
            "timer": ("Avisa com uma notificação daqui a N minutos.", TimerArgs, self.timer),
            "listar_terminais": (
                "Lista os terminais do Claude Code abertos neste Mac (número, pasta, estado). "
                "Use para 'como estão meus terminais/sessões?'.",
                SemArgs,
                self.listar_terminais,
            ),
            "abrir_terminal": (
                "Abre um terminal numa aba do painel, numa pasta de projeto (ex.: "
                "pasta='life-manager'); claude=true já abre o Claude Code ('abre um Claude Code "
                "no X'), claude=false só o terminal ('abre um terminal no X'). Se vier 'opcoes', "
                "pergunte qual.",
                AbrirTerminalArgs,
                self.abrir_terminal,
            ),
            "mandar_terminal": (
                "Manda texto para um terminal: num Claude Code vai como mensagem ('Terminal 2, "
                "roda os testes' -> numero=2, texto='roda os testes'); num terminal comum vai "
                "como comando de uma linha ('Terminal 3, roda npm test' -> texto='npm test'). "
                "O Kaio confirma antes. Não serve para aprovar ou negar permissões.",
                MandarTerminalArgs,
                self.mandar_terminal,
            ),
            "fechar_terminal": (
                "Fecha (encerra) um terminal; pede confirmação se houver algo rodando ou se ele "
                "estiver aberto no Terminal.app.",
                FecharTerminalArgs,
                self.fechar_terminal,
            ),
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
