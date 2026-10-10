"""Spotify do Kaio: busca e player pela Web API (login PKCE, token no Keychain) e a música
baixa enquanto o Jarvis ouve e fala (AppleScript, sem login).

O token de renovação só existe no Keychain e na memória; o log registra método, caminho e
status, nunca token. Ver openspec/specs/ferramentas-locais ("Tocar o que o Kaio pedir",
"Conta Spotify do Kaio", "Música baixa enquanto o Jarvis ouve e fala").
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import unicodedata
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

log = logging.getLogger(__name__)

API = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = (
    "playlist-read-private playlist-read-collaborative "
    "user-read-playback-state user-modify-playback-state"
)
KEYCHAIN_SERVICE = "jarvis-spotify"
KEYCHAIN_ACCOUNT = "kaio"
LOGIN_COMMAND = "uv run python -m jarvis.spotify_login"
TIMEOUT = 5.0
PLAYLISTS_TTL = 600.0
MAX_PLAYLISTS = 500
DEVICE_WAIT = 10.0

SEARCH_TYPES = {"musica": "track", "artista": "artist", "album": "album", "playlist": "playlist"}


class SpotifyError(Exception):
    """Erro já em português, curto, para o modelo. `login`: é preciso autorizar de novo."""

    def __init__(self, message: str, login: bool = False) -> None:
        super().__init__(message)
        self.login = login


NEEDS_LOGIN = "Preciso que o senhor autorize o Spotify uma vez (o comando está na tela)."


# --- Keychain (pelo `security` do macOS, sem shell)

Run = Callable[[list[str], bytes | None], Awaitable[Any]]


async def keychain_read(run: Run) -> str | None:
    r = await run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
        None,
    )
    token = r.stdout.strip() if r.returncode == 0 else ""
    return token or None


async def keychain_write(run: Run, token: str) -> None:
    # -U atualiza o item existente; o token vai como argumento do `security` (sem shell)
    r = await run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            KEYCHAIN_ACCOUNT,
            "-w",
            token,
        ],
        None,
    )
    if r.returncode != 0:
        log.warning("spotify: não consegui gravar o token no Keychain")


# --- escolha da playlist do Kaio


def normalize(text: str) -> str:
    """Minúsculas, sem acento, sem emoji nem pontuação, espaços simples."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]|_", " ", text).split())


_FILLER = {"a", "o", "de", "da", "do", "minha", "meu", "playlist", "lista"}


def pick_playlist(query: str, playlists: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Igual > contém o pedido > mais palavras do pedido no nome; empate fica com a primeira."""
    q = normalize(query)
    words = [w for w in q.split() if w not in _FILLER] or q.split()
    core = " ".join(words)
    best, best_rank = None, (0, 0)
    for p in playlists:
        name = normalize(p.get("name") or "")
        if not name:
            continue
        if name in (q, core):
            rank = (3, 0)
        elif core and core in name:
            rank = (2, 0)
        else:
            hits = sum(1 for w in words if w in name.split())
            rank = (1, hits) if hits else (0, 0)
        if rank > best_rank:
            best, best_rank = p, rank
    return best


def _artists(item: dict[str, Any]) -> str:
    return ", ".join(a.get("name", "") for a in item.get("artists") or [] if a.get("name"))


# --- cliente da Web API


class Spotify:
    def __init__(
        self,
        client_id: str,
        run: Run,
        http: httpx.AsyncClient | None = None,
        computer_name: Callable[[], Awaitable[str]] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client_id = client_id
        self._run = run
        self._http = http or httpx.AsyncClient(timeout=TIMEOUT)
        self._computer_name = computer_name or self._scutil_name
        self._sleep = sleep
        self._clock = clock
        self._access: str | None = None
        self._expires = 0.0
        self._refresh: str | None = None
        self._playlists: list[dict[str, Any]] | None = None
        self._playlists_at = 0.0

    # tokens

    async def _scutil_name(self) -> str:
        r = await self._run(["scutil", "--get", "ComputerName"], None)
        return r.stdout.strip() if r.returncode == 0 else ""

    async def _token(self, force: bool = False) -> str:
        if not force and self._access and self._clock() < self._expires - 60:
            return self._access
        if self._refresh is None:
            self._refresh = await keychain_read(self._run)
        if not self._refresh:
            raise SpotifyError(NEEDS_LOGIN, login=True)
        try:
            r = await self._http.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh,
                    "client_id": self._client_id,
                },
                timeout=TIMEOUT,
            )
        except httpx.HTTPError as e:
            raise SpotifyError("Sem conexão com o Spotify.") from e
        log.info("spotify: POST /api/token %d", r.status_code)
        if r.status_code in (400, 401):  # invalid_grant: revogado ou expirado
            self._refresh, self._access = None, None
            raise SpotifyError(NEEDS_LOGIN, login=True)
        if r.status_code != 200:
            raise SpotifyError("O Spotify não respondeu agora.")
        data = r.json()
        self._access = data["access_token"]
        self._expires = self._clock() + float(data.get("expires_in", 3600))
        new = data.get("refresh_token")
        if new and new != self._refresh:
            self._refresh = new
            await keychain_write(self._run, new)
        return self._access

    async def _api(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        for attempt in (0, 1):
            token = await self._token(force=attempt == 1)
            try:
                r = await self._http.request(
                    method,
                    API + path,
                    params=params,
                    json=json,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=TIMEOUT,
                )
            except httpx.HTTPError as e:
                raise SpotifyError("Sem conexão com o Spotify.") from e
            log.info("spotify: %s %s %d", method, path, r.status_code)
            if r.status_code == 401 and attempt == 0:
                continue
            if r.status_code in (200, 201):
                return r.json() if r.content else None
            if r.status_code in (202, 204):
                return None
            raise self._error(r)
        raise SpotifyError(NEEDS_LOGIN, login=True)

    @staticmethod
    def _error(r: httpx.Response) -> SpotifyError:
        try:
            reason = str(r.json().get("error", {}).get("reason", ""))
        except (ValueError, AttributeError):
            reason = ""
        if r.status_code == 403 and "PREMIUM" in reason:
            return SpotifyError("O Spotify exige Premium para isso.")
        if r.status_code == 404:
            return SpotifyError("O Spotify deste Mac não está pronto.")
        if r.status_code == 429:
            return SpotifyError("O Spotify pediu para esperar um pouco.")
        if r.status_code == 401:
            return SpotifyError(NEEDS_LOGIN, login=True)
        return SpotifyError("O Spotify recusou o pedido.")

    # busca

    async def search(self, tipo: str, query: str) -> dict[str, Any] | None:
        """Primeiro resultado: {nome, artista, uri, contexto, offset}."""
        if tipo == "minha_playlist":
            p = pick_playlist(query, await self.my_playlists())
            if p is None:
                return None
            owner = (p.get("owner") or {}).get("display_name") or ""
            return {"nome": p["name"], "artista": owner, "contexto": p["uri"], "tipo": tipo}
        kind = SEARCH_TYPES[tipo]
        data = await self._api(
            "GET", "/search", params={"q": query, "type": kind, "limit": 5, "market": "from_token"}
        )
        items = [i for i in (data or {}).get(kind + "s", {}).get("items") or [] if i]
        if not items:
            return None
        it = items[0]
        out: dict[str, Any] = {"nome": it.get("name", ""), "tipo": tipo}
        if tipo == "musica":
            # dentro do álbum, a partir dela: a reprodução segue quando a música acaba
            out |= {
                "artista": _artists(it),
                "contexto": (it.get("album") or {}).get("uri"),
                "offset": it["uri"],
            }
            if not out["contexto"]:
                out |= {"contexto": None, "uris": [it["uri"]]}
        elif tipo == "album":
            out |= {"artista": _artists(it), "contexto": it["uri"]}
        else:
            out |= {"contexto": it["uri"]}
        return out

    async def my_playlists(self) -> list[dict[str, Any]]:
        if self._playlists is not None and self._clock() - self._playlists_at < PLAYLISTS_TTL:
            return self._playlists
        out: list[dict[str, Any]] = []
        offset = 0
        while offset < MAX_PLAYLISTS:
            page = await self._api("GET", "/me/playlists", params={"limit": 50, "offset": offset})
            items = [i for i in (page or {}).get("items") or [] if i]
            out += items
            if not (page or {}).get("next") or not items:
                break
            offset += 50
        self._playlists, self._playlists_at = out, self._clock()
        return out

    # player

    async def device(self) -> str:
        """Dispositivo deste Mac; com o Spotify fechado, abre o app e espera até ~10 s."""
        name = await self._computer_name()
        waited, opened = 0.0, False
        while True:
            data = await self._api("GET", "/me/player/devices")
            computers = [
                d for d in (data or {}).get("devices") or [] if d.get("type") == "Computer"
            ]
            mine = [d for d in computers if name and d.get("name") == name] or computers
            if mine and mine[0].get("id"):
                return str(mine[0]["id"])
            if not opened:
                await self._run(["open", "-a", "Spotify"], None)
                opened = True
            if waited >= DEVICE_WAIT:
                raise SpotifyError("Abri o Spotify, mas ele não ficou pronto a tempo.")
            await self._sleep(1.0)
            waited += 1.0

    async def play(self, found: dict[str, Any]) -> None:
        device = await self.device()
        body: dict[str, Any] = {}
        if found.get("contexto"):
            body["context_uri"] = found["contexto"]
            if found.get("offset"):
                body["offset"] = {"uri": found["offset"]}
        else:
            body["uris"] = found["uris"]
        await self._api("PUT", "/me/player/play", params={"device_id": device}, json=body)

    async def shuffle(self, on: bool) -> None:
        await self._api("PUT", "/me/player/shuffle", params={"state": str(on).lower()})

    async def repeat(self, on: bool) -> None:
        await self._api("PUT", "/me/player/repeat", params={"state": "context" if on else "off"})

    async def volume(self, percent: int) -> None:
        await self._api("PUT", "/me/player/volume", params={"volume_percent": percent})


# --- música baixa enquanto o Jarvis ouve e fala (AppleScript; não abre o Spotify)

_GET_PLAYING_VOLUME = [
    "osascript",
    "-e",
    'if application "Spotify" is running then',
    "-e",
    'tell application "Spotify" to if player state is playing then return sound volume',
    "-e",
    "end if",
    "-e",
    "return -1",
]


def _set_volume_argv(volume: int) -> list[str]:
    return [
        "osascript",
        "-e",
        "on run argv",
        "-e",
        'if application "Spotify" is running then '
        'tell application "Spotify" to set sound volume to (item 1 of argv as integer)',
        "-e",
        "end run",
        str(int(volume)),
    ]


DUCK_FACTOR = 0.25
DUCK_MIN = 10
RESTORE_DELAY = 1.5
DUCK_TIMEOUT = 3.0  # nunca segurar a fala esperando o AppleScript


class Ducker:
    """Abaixa o Spotify enquanto houver um motivo (ouvindo, falando, turno) e volta ao volume
    guardado 1,5 s depois do último motivo sair (as pausas entre ouvir, pensar e falar)."""

    def __init__(self, run: Run, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._run = run
        self._sleep = sleep
        self._reasons: set[str] = set()
        self._saved: int | None = None
        self._lock = asyncio.Lock()
        self._restore_task: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def ducked(self) -> bool:
        return self._saved is not None

    def hold(self, reason: str, on: bool) -> None:
        """Chamado na thread do asyncio, sem esperar (a fala não pode atrasar)."""
        before = bool(self._reasons)
        if on:
            self._reasons.add(reason)
        else:
            self._reasons.discard(reason)
        if self._reasons and not before:
            if self._restore_task is not None:
                self._restore_task.cancel()
                self._restore_task = None
            self._spawn(self._duck())
        elif not self._reasons and before:
            self._restore_task = self._spawn(self._restore_later())

    def requested_volume(self, volume: int) -> None:
        """O Kaio pediu um volume durante a música baixa: ele vale no fim."""
        if self._saved is not None:
            self._saved = volume

    def _spawn(self, coro: Awaitable[None]) -> asyncio.Task[None]:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _duck(self) -> None:
        async with self._lock:
            if self._saved is not None or not self._reasons:
                return
            try:
                r = await asyncio.wait_for(self._run(_GET_PLAYING_VOLUME, None), DUCK_TIMEOUT)
                current = int(r.stdout.strip()) if r.returncode == 0 else -1
            except (ValueError, OSError, TimeoutError):
                return
            target = max(DUCK_MIN, round(current * DUCK_FACTOR))
            if current < 0 or target >= current:
                return  # Spotify fechado, parado ou já baixo
            self._saved = current
            await self._set(target)

    async def _restore_later(self) -> None:
        await self._sleep(RESTORE_DELAY)
        async with self._lock:
            if self._reasons or self._saved is None:
                return
            saved, self._saved = self._saved, None
            await self._set(saved)

    async def _set(self, volume: int) -> None:
        try:
            await asyncio.wait_for(self._run(_set_volume_argv(volume), None), DUCK_TIMEOUT)
        except (OSError, TimeoutError):
            log.info("música baixa: o Spotify não respondeu")
