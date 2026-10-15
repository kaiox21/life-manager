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
import unicodedata
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
# rascunhos (jarvis-projetos): área de transferência + cartão + arquivo local; nunca enviados
MAX_DRAFT = 6000
DRAFTS_DIR = Path.home() / "Library/Application Support/Jarvis/rascunhos"
DRAFTS_KEEP = 50
DRAFT_REPLY = "Rascunho pronto no painel e na área de transferência, senhor."
DEFAULT_EDITOR = "Visual Studio Code"


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


class AbrirProjetoArgs(Args):
    nome: str = Field(
        min_length=1,
        max_length=200,
        description="Nome do projeto como o Kaio disse (ex.: 'NC Barber', 'life-manager')",
    )
    claude: bool = Field(
        default=False, description="true = o terminal já abre o Claude Code ('com um Claude Code')"
    )


class RascunhoArgs(Args):
    tipo: Literal["email", "mensagem", "texto"]
    para: str | None = Field(
        default=None,
        max_length=120,
        description="Destinatário como o Kaio disse (ex.: 'professor de redes', 'Netto')",
    )
    assunto: str | None = Field(default=None, max_length=200, description="Assunto (e-mail)")
    texto: str = Field(
        min_length=1,
        max_length=MAX_DRAFT,
        description="O texto completo, em nome do Kaio (primeira pessoa, pt-BR, assinado 'Kaio')",
    )


class TerminalControl(Protocol):
    def resolve(self, pasta: str) -> dict[str, Any]: ...
    async def open(self, pasta: str, claude: bool = False) -> dict[str, Any]: ...
    async def open_in(self, path: Path, claude: bool = False) -> dict[str, Any]: ...
    async def send(self, numero: int, texto: str, confirm: Confirm | None) -> dict[str, Any]: ...
    async def close(self, numero: int, confirm: Confirm | None) -> dict[str, Any]: ...


class SilenciarAvisosArgs(Args):
    acao: Literal["pausar", "pausar_ate_amanha", "retomar"]
    minutos: int | None = Field(
        default=None, ge=1, le=720, description="Para pausar: por quantos minutos (1 a 720)"
    )


class ModoEstudoArgs(Args):
    acao: Literal["iniciar", "parar", "status"]
    minutos: int | None = Field(
        default=None, ge=1, le=240, description="Para iniciar: duração do bloco (padrão 50)"
    )
    pausa: int | None = Field(
        default=None, ge=0, le=60, description="Para iniciar: minutos de pausa no fim (padrão 10)"
    )


class Study(Protocol):
    async def start(
        self, minutes: int | None = None, pause: int | None = None
    ) -> dict[str, Any]: ...
    async def stop(self, *, silent: bool = False) -> dict[str, Any]: ...
    def status(self) -> dict[str, Any] | None: ...
    def status_text(self) -> str: ...


class Notices(Protocol):
    def pause(self, minutes: int) -> dict[str, Any]: ...
    def pause_until_morning(self) -> dict[str, Any]: ...
    def resume(self) -> dict[str, Any]: ...
    def status(self) -> dict[str, Any]: ...


class ClipboardArgs(Args):
    acao: Literal["ler", "escrever"]
    texto: str | None = Field(default=None, max_length=MAX_CLIPBOARD)


SPOTIFY = {
    "tocar": 'tell application "Spotify" to play',
    "pausar": 'tell application "Spotify" to pause',
    "proxima": 'tell application "Spotify" to next track',
    "anterior": 'tell application "Spotify" to previous track',
}


def _ascii(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def _short(path: Path, home: Path) -> str:
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


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
        editor: str = DEFAULT_EDITOR,
        drafts_dir: Path = DRAFTS_DIR,
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
        self._editor = editor.strip()
        self._drafts_dir = drafts_dir
        self.notices: Notices | None = None  # avisos falados (jarvis/proactive.py)
        self.study: Study | None = None  # modo estudo (jarvis/study.py)

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

    async def musica_alternar(self) -> dict[str, Any]:
        """Botão Música do painel (não é ferramenta do modelo): pausa ou retoma o Spotify."""
        r = await self._run(["osascript", "-e", 'tell application "Spotify" to playpause'], None)
        return {"status": "ok"} if r.returncode == 0 else {"erro": "Spotify indisponível."}

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

    async def silenciar_avisos(self, a: SilenciarAvisosArgs) -> dict[str, Any]:
        """Só controla a voz do próprio Jarvis (o WhatsApp segue recebendo): sem confirmação."""
        if self.notices is None:
            return {"erro": "Os avisos falados não estão ligados."}
        if a.acao == "retomar":
            return self.notices.resume()
        if a.acao == "pausar_ate_amanha":
            return self.notices.pause_until_morning()
        return self.notices.pause(a.minutos or 60)

    async def modo_estudo(self, a: ModoEstudoArgs) -> dict[str, Any]:
        """Foco, playlist e avisos retidos: só mexe no próprio Mac do Kaio, sem confirmação."""
        if self.study is None:
            return {"erro": "O modo estudo não está disponível."}
        if a.acao == "iniciar":
            return await self.study.start(a.minutos, a.pausa)
        if a.acao == "parar":
            return await self.study.stop()
        return {"status": self.study.status() or "sem_modo", "texto": self.study.status_text()}

    # --- projetos e rascunhos (jarvis-projetos)

    async def abrir_projeto(self, a: AbrirProjetoArgs) -> dict[str, Any]:
        """Editor na pasta + terminal do Jarvis nela (shell livre reaproveitado). Só pastas da
        lista permitida; nenhum comando além do editor, do terminal e do `claude` pedido."""
        if self._control is None:
            return {"erro": "As abas de terminal não estão disponíveis."}
        target = self._control.resolve(a.nome)
        if "pasta" not in target:
            return target
        path: Path = target["pasta"]
        editor_error: str | None = None
        if not self._editor:
            editor_error = "nenhum editor configurado"
        else:
            r = await self._run(["open", "-a", self._editor, str(path)], None)
            if r.returncode != 0:
                editor_error = f"não encontrei o app {self._editor!r}"
        term = await self._control.open_in(path, a.claude)
        if "erro" in term:
            out = dict(term)
            out["editor"] = "aberto" if editor_error is None else editor_error
            return out
        n = term.get("numero")
        existing = term.get("status") == "existente"
        if editor_error is None:
            fala = f"{path.name} aberto no {self._editor}, senhor. Terminal {n}."
        else:
            fala = f"{path.name} aberto no Terminal {n}, senhor. Não encontrei o {self._editor}."
        log.info("projeto: %s (terminal %s%s)", path.name, n, ", já aberto" if existing else "")
        return {
            "status": "aberto",
            "pasta": path.name,
            "editor": "aberto" if editor_error is None else editor_error,
            "terminal": {"numero": n, "tipo": term.get("tipo"), "existente": existing},
            "_fala": fala,
            "_painel_fechar": True,
        }

    async def rascunho(self, a: RascunhoArgs) -> dict[str, Any]:
        """O texto vai para a área de transferência, para o cartão e para um arquivo local.
        Nunca é enviado nem logado (só tipo, destinatário e tamanho)."""
        await self._run(["pbcopy"], a.texto.encode())
        path = self._save_draft(a)
        log.info("rascunho: %s para %s (%d caracteres)", a.tipo, a.para or "-", len(a.texto))
        return {
            "status": "pronto",
            "tipo": a.tipo,
            "para": a.para,
            "assunto": a.assunto,
            "caracteres": len(a.texto),
            "arquivo": _short(path, self._home) if path else None,
            "texto": a.texto,  # só para o cartão: for_model tira
            "_fala": DRAFT_REPLY,
        }

    def _save_draft(self, a: RascunhoArgs) -> Path | None:
        label = a.assunto or a.para or a.tipo
        slug = re.sub(r"[^a-z0-9]+", "-", _ascii(label).lower()).strip("-")[:40] or a.tipo
        name = f"{self._now():%Y-%m-%d-%H%M%S}-{slug}.md"
        head = [f"# {a.tipo}"]
        if a.para:
            head.append(f"para: {a.para}")
        if a.assunto:
            head.append(f"assunto: {a.assunto}")
        try:
            self._drafts_dir.mkdir(parents=True, exist_ok=True)
            path = self._drafts_dir / name
            path.write_text("\n".join(head) + "\n\n" + a.texto + "\n")
            for old in sorted(self._drafts_dir.glob("*.md"))[:-DRAFTS_KEEP]:
                old.unlink()
        except OSError:
            log.warning("rascunho: não consegui gravar o arquivo")
            return None
        return path

    async def rascunho_copiar(self, texto: str) -> None:
        """Botão Copiar do cartão (não é ferramenta do modelo)."""
        if 0 < len(texto) <= MAX_DRAFT:
            await self._run(["pbcopy"], texto.encode())

    def for_model(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """O que o modelo recebe. Os resumos dos pedidos de permissão (comandos podem ter
        segredos) ficam só no cartão da tela; o texto do rascunho e as marcas internas
        (`_fala`, `_painel_fechar`) também não voltam ao modelo."""
        if name in ("tocar_musica", "controlar_musica") and "opcoes" in data:
            return {k: v for k, v in data.items() if k != "opcoes"}
        if name == "listar_terminais":
            keep = ("numero", "pasta", "tipo", "estado", "ferramenta")
            return {"terminais": [{k: t.get(k) for k in keep} for t in data["terminais"]]}
        hidden = {"_fala", "_painel_fechar"} | ({"texto"} if name == "rascunho" else set())
        if hidden & data.keys():
            return {k: v for k, v in data.items() if k not in hidden}
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
            "silenciar_avisos": (
                "Pausa os avisos falados do Jarvis (lembretes, terminais, pergunta dos gastos): "
                "'silencia os avisos por uma hora' -> acao=pausar, minutos=60; 'até amanhã' -> "
                "pausar_ate_amanha; 'volta a avisar' -> retomar. O WhatsApp continua recebendo.",
                SilenciarAvisosArgs,
                self.silenciar_avisos,
            ),
            "modo_estudo": (
                "Modo estudo: 'modo estudo por 50 minutos' -> acao=iniciar, minutos=50 (pausa "
                "opcional: 'com pausa de 5' -> pausa=5); liga o Foco do Mac, toca a playlist de "
                "estudo e silencia os avisos até o fim. 'para o estudo' -> parar; 'quanto falta "
                "do estudo' -> status. Diga ao Kaio o que ligou e o que não ligou.",
                ModoEstudoArgs,
                self.modo_estudo,
            ),
            "area_transferencia": (
                "Lê (pede permissão) ou escreve na área de transferência.",
                ClipboardArgs,
                self.area_transferencia,
            ),
            "abrir_projeto": (
                "Abre um projeto: a pasta no editor (VS Code) e um terminal do Jarvis nela "
                "('abre o NC Barber' -> nome='NC Barber'); claude=true quando o Kaio pedir 'com "
                "um Claude Code'. Só pastas permitidas; se vier 'opcoes', pergunte qual. A "
                "resposta ao Kaio é fixa: não escreva nada depois.",
                AbrirProjetoArgs,
                self.abrir_projeto,
            ),
            "rascunho": (
                "Escreve um rascunho em nome do Kaio e o deixa na área de transferência e no "
                "painel, sem enviar: 'escreve um e-mail pro professor pedindo X' -> tipo=email, "
                "para='professor', assunto=..., texto=o e-mail completo (primeira pessoa, pt-BR, "
                "assinado 'Kaio', sem 'senhor'). Mensagem de WhatsApp: tipo=mensagem, sem assunto. "
                "A resposta ao Kaio é fixa: não repita o texto.",
                RascunhoArgs,
                self.rascunho,
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
