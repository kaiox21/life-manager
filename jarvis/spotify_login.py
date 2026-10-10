"""Autoriza o Jarvis na conta Spotify do Kaio, uma vez (PKCE, sem segredo de cliente).

    uv run python -m jarvis.spotify_login

Abre o navegador, recebe o retorno em http://127.0.0.1:8888/callback (o endereço cadastrado
no app do Spotify) e guarda o token de renovação no Keychain do macOS. Nada vai para o log.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import sys
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from jarvis.local_tools import run_command
from jarvis.spotify import (
    AUTHORIZE_URL,
    REDIRECT_URI,
    SCOPES,
    TOKEN_URL,
    Run,
    keychain_write,
)

PORT = 8888


def _open(url: str) -> None:
    """`open` do macOS (mais confiável que o webbrowser fora de um terminal)."""
    import subprocess

    if subprocess.run(["open", url], check=False).returncode != 0:
        webbrowser.open(url)


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def authorize_url(client_id: str, challenge: str, state: str) -> str:
    return (
        AUTHORIZE_URL
        + "?"
        + urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
                "scope": SCOPES,
                "state": state,
            }
        )
    )


def wait_for_code(state: str, port: int = PORT, timeout: float = 300) -> str:
    """Um retorno só: confere o `state` e devolve o código (ou levanta com o motivo)."""
    got: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (nome do http.server)
            query = parse_qs(urlparse(self.path).query)
            if urlparse(self.path).path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            if query.get("state", [""])[0] != state:
                got["erro"] = "state diferente (pedido que não veio deste login)"
            elif "error" in query:
                got["erro"] = query["error"][0]
            else:
                got["code"] = query.get("code", [""])[0]
            ok = "code" in got
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = (
                "Pronto, o Jarvis já pode tocar suas músicas. Pode fechar esta aba."
                if ok
                else ("Não deu certo: " + got.get("erro", ""))
            )
            self.wfile.write(f"<p style='font:18px sans-serif'>{msg}</p>".encode())

        def log_message(self, *_args: object) -> None:  # sem log (a URL tem o código)
            pass

    try:
        server = HTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        raise SystemExit(f"A porta {port} está ocupada; feche o que usa e tente de novo.") from e
    server.timeout = timeout
    with server:
        while not got:
            server.handle_request()
            if not got:
                raise SystemExit("O navegador não voltou a tempo; rode o login de novo.")
    if "code" not in got:
        raise SystemExit("O Spotify não autorizou: " + got.get("erro", ""))
    return got["code"]


async def exchange(
    client_id: str, code: str, verifier: str, http: httpx.AsyncClient | None = None
) -> dict[str, str]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    if http is None:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(TOKEN_URL, data=data)
    else:
        r = await http.post(TOKEN_URL, data=data)
    if r.status_code != 200:
        raise SystemExit(f"O Spotify recusou a troca do código ({r.status_code}).")
    return r.json()


async def login(
    client_id: str,
    run: Run = run_command,
    open_browser: Callable[[str], object] = lambda url: _open(url),
    wait: Callable[[str], str] = wait_for_code,
    http: httpx.AsyncClient | None = None,
) -> None:
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    url = authorize_url(client_id, challenge, state)
    print("Se o navegador não abrir, abra este link:\n" + url, flush=True)
    open_browser(url)
    code = await asyncio.to_thread(wait, state)
    tokens = await exchange(client_id, code, verifier, http)
    await keychain_write(run, tokens["refresh_token"])


def main() -> None:
    import os

    from dotenv import dotenv_values

    client_id = os.environ.get("SPOTIFY_CLIENT_ID") or dotenv_values(".env").get(
        "SPOTIFY_CLIENT_ID"
    )
    if not client_id:
        sys.exit("Falta SPOTIFY_CLIENT_ID no .env (Client ID do app em developer.spotify.com).")
    print("Abrindo o navegador para autorizar o Jarvis no Spotify…", flush=True)
    asyncio.run(login(client_id))
    print("Pronto: o token ficou no Keychain (jarvis-spotify). Reinicie o Jarvis.")


if __name__ == "__main__":
    main()
