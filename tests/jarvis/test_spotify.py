import asyncio
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from jarvis.local_tools import Completed, LocalTools
from jarvis.spotify import (
    KEYCHAIN_SERVICE,
    LOGIN_COMMAND,
    Ducker,
    Spotify,
    SpotifyError,
    normalize,
    pick_playlist,
)
from jarvis.spotify_login import authorize_url, exchange, login, pkce_pair

# --- executor falso (Keychain, scutil, open, osascript)


class Runner:
    def __init__(self, keychain="rt-1", volume="80"):
        self.keychain = keychain
        self.volume = volume
        self.calls: list[list[str]] = []

    async def __call__(self, argv, stdin):
        assert all(isinstance(a, str) for a in argv)
        self.calls.append(argv)
        if argv[:2] == ["security", "find-generic-password"]:
            return Completed(0 if self.keychain else 44, (self.keychain or "") + "\n", "")
        if argv[:2] == ["security", "add-generic-password"]:
            self.keychain = argv[argv.index("-w") + 1]
            return Completed(0, "", "")
        if argv[:2] == ["scutil", "--get"]:
            return Completed(0, "MacBook do Kaio\n", "")
        if argv[0] == "osascript" and "return -1" in argv:
            return Completed(0, self.volume + "\n", "")
        if argv[0] == "osascript" and argv[-1].isdigit():
            self.volume = argv[-1]
        return Completed(0, "", "")


# --- API falsa


class Api:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.token_status = 200
        self.devices = [
            {"id": "phone", "type": "Smartphone", "name": "iPhone"},
            {"id": "mac", "type": "Computer", "name": "MacBook do Kaio"},
        ]
        self.playlists = [
            {"name": "Rock nacional", "uri": "spotify:playlist:rock", "owner": {}},
            {"name": "Estudo 📚 foco", "uri": "spotify:playlist:estudo", "owner": {}},
        ]
        self.fail_once_401 = False
        self.play_status = 204

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        path = req.url.path
        if req.url.host == "accounts.spotify.com":
            form = parse_qs(req.content.decode())
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            assert form["grant_type"] == ["refresh_token"] and form["client_id"] == ["cid"]
            return httpx.Response(
                200, json={"access_token": "at", "expires_in": 3600, "refresh_token": "rt-2"}
            )
        if self.fail_once_401:
            self.fail_once_401 = False
            return httpx.Response(401, json={"error": {"status": 401}})
        assert req.headers["authorization"] == "Bearer at"
        if path == "/v1/search":
            kind = req.url.params["type"]
            assert req.url.params["limit"] == "5"
            if req.url.params["q"] == "nada":
                return httpx.Response(200, json={kind + "s": {"items": []}})
            items = {
                "track": [
                    {
                        "name": "Tempo Perdido",
                        "uri": "spotify:track:tp",
                        "artists": [{"name": "Legião Urbana"}],
                        "album": {"uri": "spotify:album:dois"},
                    }
                ],
                "artist": [{"name": "Legião Urbana", "uri": "spotify:artist:lu"}],
                "album": [
                    {"name": "Dois", "uri": "spotify:album:dois", "artists": [{"name": "LU"}]}
                ],
                "playlist": [None, {"name": "Top Brasil", "uri": "spotify:playlist:top"}],
            }[kind]
            return httpx.Response(200, json={kind + "s": {"items": items}})
        if path == "/v1/me/playlists":
            return httpx.Response(200, json={"items": self.playlists, "next": None})
        if path == "/v1/me/player/devices":
            return httpx.Response(200, json={"devices": self.devices})
        if path == "/v1/me/player/play":
            return httpx.Response(self.play_status, json={"error": {"reason": "PREMIUM_REQUIRED"}})
        if path.startswith("/v1/me/player/"):
            return httpx.Response(204)
        return httpx.Response(404)


async def _nosleep(_s):
    pass


def client(api=None, runner=None):
    api = api or Api()
    runner = runner or Runner()
    http = httpx.AsyncClient(transport=httpx.MockTransport(api))
    return Spotify("cid", runner, http=http, sleep=_nosleep), api, runner


def plays(api):
    return [
        json.loads(r.content) | dict(r.url.params)
        for r in api.requests
        if r.url.path.endswith("/play")
    ]


# --- escolha da playlist


def test_normaliza_sem_acento_emoji_e_pontuacao():
    assert normalize("Estudo 📚 FOCO!") == "estudo foco"
    assert normalize("Músicas p/ Correr") == "musicas p correr"


@pytest.mark.parametrize(
    ("pedido", "nome"),
    [
        ("minha playlist de estudo", "Estudo 📚 foco"),
        ("estudo foco", "Estudo 📚 foco"),
        ("rock nacional", "Rock nacional"),
        ("Rock", "Rock nacional"),
        ("pagode", None),
    ],
)
def test_escolhe_a_playlist_pelo_nome(pedido, nome):
    lists = [{"name": "Rock nacional"}, {"name": "Estudo 📚 foco"}, {"name": "Rock e estudo"}]
    got = pick_playlist(pedido, lists)
    assert (got or {}).get("name") == nome


def test_nome_igual_ganha_de_quem_so_contem():
    lists = [{"name": "Estudo pesado"}, {"name": "Estudo"}]
    assert pick_playlist("estudo", lists)["name"] == "Estudo"


# --- cliente


async def test_musica_toca_no_album_a_partir_dela_no_mac():
    sp, api, runner = client()
    found = await sp.search("musica", "Tempo Perdido")
    assert found["nome"] == "Tempo Perdido" and found["artista"] == "Legião Urbana"
    await sp.play(found)
    assert plays(api) == [
        {
            "context_uri": "spotify:album:dois",
            "offset": {"uri": "spotify:track:tp"},
            "device_id": "mac",
        }
    ]
    assert runner.keychain == "rt-2"  # o token de renovação novo foi para o Keychain


async def test_artista_album_playlist_e_minha_playlist():
    sp, api, _ = client()
    assert (await sp.search("artista", "Legião"))["contexto"] == "spotify:artist:lu"
    assert (await sp.search("album", "Dois"))["artista"] == "LU"
    assert (await sp.search("playlist", "top"))["contexto"] == "spotify:playlist:top"
    mine = await sp.search("minha_playlist", "minha playlist de estudo")
    assert mine["contexto"] == "spotify:playlist:estudo"
    await sp.search("minha_playlist", "rock")
    assert sum(r.url.path == "/v1/me/playlists" for r in api.requests) == 1  # cache de 10 min


async def test_nao_encontrou():
    sp, _, _ = client()
    assert await sp.search("musica", "nada") is None
    assert await sp.search("minha_playlist", "pagode") is None


async def test_sem_login_e_login_revogado():
    sp, _, _ = client(runner=Runner(keychain=None))
    with pytest.raises(SpotifyError) as e:
        await sp.search("musica", "x")
    assert e.value.login
    api = Api()
    api.token_status = 400  # invalid_grant
    sp, _, _ = client(api=api)
    with pytest.raises(SpotifyError) as e:
        await sp.search("musica", "x")
    assert e.value.login and "autorize" in str(e.value)


async def test_401_renova_e_tenta_de_novo():
    sp, api, _ = client()
    await sp.search("artista", "x")
    api.fail_once_401 = True
    assert (await sp.search("artista", "x"))["nome"] == "Legião Urbana"


async def test_spotify_fechado_abre_e_espera():
    api = Api()
    api.devices = []
    sp, _, runner = client(api=api)

    async def appears(_s):
        api.devices = [{"id": "mac", "type": "Computer", "name": "MacBook do Kaio"}]

    sp._sleep = appears
    assert await sp.device() == "mac"
    assert ["open", "-a", "Spotify"] in runner.calls


async def test_spotify_nao_fica_pronto():
    api = Api()
    api.devices = []
    sp, _, _ = client(api=api)
    with pytest.raises(SpotifyError, match="não ficou pronto"):
        await sp.device()


async def test_premium_e_rede():
    api = Api()
    api.play_status = 403
    sp, _, _ = client(api=api)
    with pytest.raises(SpotifyError, match="Premium"):
        await sp.play({"contexto": "spotify:artist:lu"})

    def down(_req):
        raise httpx.ConnectError("sem rede")

    sp = Spotify("cid", Runner(), http=httpx.AsyncClient(transport=httpx.MockTransport(down)))
    with pytest.raises(SpotifyError, match="Sem conexão"):
        await sp.search("musica", "x")


async def test_log_sem_token(caplog):
    sp, _, _ = client()
    with caplog.at_level("INFO"):
        await sp.search("artista", "x")
    assert "rt-" not in caplog.text and "Bearer" not in caplog.text and "at\n" not in caplog.text


# --- ferramentas


def tools(sp=None, ducker=None, runner=None):
    return LocalTools(runner=runner or Runner(), config={}, spotify=sp, ducker=ducker)


async def test_tocar_musica_diz_o_que_tocou():
    sp, _, _ = client()
    ok, out = await tools(sp).call("tocar_musica", {"pedido": "Tempo Perdido", "tipo": "musica"})
    assert ok and out == {
        "status": "tocando",
        "tipo": "musica",
        "nome": "Tempo Perdido",
        "artista": "Legião Urbana",
    }


async def test_tocar_musica_nao_encontrou_nao_toca():
    sp, api, _ = client()
    _, out = await tools(sp).call("tocar_musica", {"pedido": "pagode", "tipo": "minha_playlist"})
    assert "Não encontrei essa playlist" in out["erro"] and plays(api) == []


async def test_sem_login_comando_so_no_cartao():
    sp, _, _ = client(runner=Runner(keychain=None))
    t = tools(sp)
    _, out = await t.call("tocar_musica", {"pedido": "x", "tipo": "musica"})
    assert out["opcoes"] == [LOGIN_COMMAND]
    assert "opcoes" not in t.for_model("tocar_musica", out)
    runner = Runner(keychain=None)
    ok, out = await tools(sp, runner=runner).call("controlar_musica", {"acao": "pausar"})
    assert ok and out == {"status": "ok", "acao": "pausar"}  # AppleScript, sem login


async def test_sem_client_id():
    _, out = await tools(None).call("tocar_musica", {"pedido": "x", "tipo": "musica"})
    assert "SPOTIFY_CLIENT_ID" in out["erro"]


async def test_volume_aleatorio_repetir_pela_api():
    sp, api, _ = client()
    t = tools(sp)
    ok, _ = await t.call("controlar_musica", {"acao": "volume", "volume": 150})
    assert not ok  # fora da faixa: volta ao modelo
    assert (await t.call("controlar_musica", {"acao": "volume", "volume": 30}))[1]["volume"] == 30
    await t.call("controlar_musica", {"acao": "aleatorio", "ligado": True})
    await t.call("controlar_musica", {"acao": "repetir", "ligado": False})
    got = [(r.url.path, dict(r.url.params)) for r in api.requests if "/me/player/" in r.url.path]
    assert got == [
        ("/v1/me/player/volume", {"volume_percent": "30"}),
        ("/v1/me/player/shuffle", {"state": "true"}),
        ("/v1/me/player/repeat", {"state": "off"}),
    ]


# --- música baixa


async def test_abaixa_e_volta_ao_volume_de_antes():
    runner = Runner(volume="80")
    d = Ducker(runner, sleep=_nosleep)
    d.hold("palavra", True)
    await asyncio.sleep(0.01)
    assert runner.volume == "20" and d.ducked
    d.hold("falando", True)
    d.hold("palavra", False)
    await asyncio.sleep(0.01)
    assert runner.volume == "20"  # ainda falando
    d.hold("falando", False)
    await asyncio.sleep(0.01)
    assert runner.volume == "80" and not d.ducked


async def test_volume_pedido_no_meio_vale_no_fim():
    runner = Runner(volume="80")
    d = Ducker(runner, sleep=_nosleep)
    d.hold("turno", True)
    await asyncio.sleep(0.01)
    d.requested_volume(30)
    d.hold("turno", False)
    await asyncio.sleep(0.01)
    assert runner.volume == "30"


async def test_spotify_parado_ou_fechado_nao_mexe():
    runner = Runner(volume="-1")
    d = Ducker(runner, sleep=_nosleep)
    d.hold("ouvindo", True)
    await asyncio.sleep(0.01)
    d.hold("ouvindo", False)
    await asyncio.sleep(0.01)
    assert not any(c[-1].isdigit() for c in runner.calls if c[0] == "osascript")


async def test_motivo_novo_antes_de_voltar_cancela_a_volta():
    runner = Runner(volume="80")
    gate = asyncio.Event()

    async def slow(_s):
        await gate.wait()

    d = Ducker(runner, sleep=slow)
    d.hold("turno", True)
    await asyncio.sleep(0.01)
    d.hold("turno", False)
    d.hold("falando", True)
    gate.set()
    await asyncio.sleep(0.01)
    assert runner.volume == "20"


# --- login


def test_url_de_autorizacao_pkce():
    verifier, challenge = pkce_pair()
    assert 43 <= len(verifier) <= 128 and "=" not in challenge
    q = parse_qs(urlparse(authorize_url("cid", challenge, "st")).query)
    assert q["redirect_uri"] == ["http://127.0.0.1:8888/callback"]
    assert q["code_challenge_method"] == ["S256"] and q["state"] == ["st"]
    assert set(q["scope"][0].split()) == {
        "playlist-read-private",
        "playlist-read-collaborative",
        "user-read-playback-state",
        "user-modify-playback-state",
    }


async def test_login_troca_o_codigo_e_grava_no_keychain():
    seen = {}

    def token(req):
        seen.update(parse_qs(req.content.decode()))
        return httpx.Response(200, json={"access_token": "at", "refresh_token": "rt-novo"})

    runner = Runner(keychain=None)
    opened = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(token))
    await login("cid", runner, opened.append, lambda state: "code-1", http)
    assert opened and seen["code"] == ["code-1"] and seen["code_verifier"]
    assert runner.keychain == "rt-novo"
    add = next(c for c in runner.calls if c[1] == "add-generic-password")
    assert add[add.index("-s") + 1] == KEYCHAIN_SERVICE


async def test_troca_recusada():
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(400)))
    with pytest.raises(SystemExit):
        await exchange("cid", "c", "v", http)
