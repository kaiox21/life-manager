import asyncio
import json

import pytest

from jarvis.permissions import (
    ALLOW,
    DENY,
    DENY_MESSAGE,
    EXPIRED,
    IN_TAB,
    HookServer,
    Permissions,
    decision,
    hook_settings,
)
from tests.jarvis.test_sessions import wait_for

BODY = {
    "hook_event_name": "PermissionRequest",
    "tool_name": "Bash",
    "tool_input": {"command": "npm test"},
}


async def post(
    port: int,
    body: bytes,
    token: str | None = "tk-1",
    path: str = "/permissao",
    method: str = "POST",
):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    head = f"{method} {path} HTTP/1.1\r\nHost: x\r\nContent-Length: {len(body)}\r\n"
    if token is not None:
        head += f"Authorization: Bearer {token}\r\n"
    writer.write(head.encode() + b"\r\n" + body)
    await writer.drain()
    raw = await asyncio.wait_for(reader.read(), 5)
    writer.close()
    status = int(raw.split(b" ", 2)[1])
    payload = raw.split(b"\r\n\r\n", 1)[1]
    return status, json.loads(payload or b"{}")


def make_server(perms: Permissions) -> HookServer:
    return HookServer(lambda tk: "s1" if tk == "tk-1" else None, perms.handle)


async def opened(perms: Permissions) -> list:
    got: list = []

    async def on_open(req):
        got.append(req)

    perms.on_open = on_open
    return got


def test_settings_do_hook():
    s = json.loads(hook_settings(4321))
    h = s["hooks"]["PermissionRequest"][0]["hooks"][0]
    assert h["type"] == "http" and h["url"] == "http://127.0.0.1:4321/permissao"
    assert h["headers"] == {"Authorization": "Bearer $JARVIS_HOOK_TOKEN"}
    assert h["allowedEnvVars"] == ["JARVIS_HOOK_TOKEN"]
    assert "JARVIS_HOOK_TOKEN=" not in hook_settings(4321)  # o token nunca vai no JSON


def test_decisoes():
    assert decision(ALLOW)["hookSpecificOutput"]["decision"] == {"behavior": "allow"}
    assert decision(DENY)["hookSpecificOutput"]["decision"] == {
        "behavior": "deny",
        "message": DENY_MESSAGE,
    }
    for r in (IN_TAB, EXPIRED):
        assert decision(r) == {}
    for r in (ALLOW, DENY):  # nunca "sempre permitir", nem trocar o comando, nem interromper
        d = decision(r)["hookSpecificOutput"]["decision"]
        assert not {"updatedPermissions", "updatedInput", "interrupt"} & d.keys()


async def test_permitir_pelo_clique():
    perms = Permissions()
    got = await opened(perms)
    async with make_server(perms).run() as port:
        task = asyncio.create_task(post(port, json.dumps(BODY).encode()))
        await wait_for(lambda: got)
        assert got[0].sid == "s1" and got[0].body["tool_name"] == "Bash"
        assert await perms.resolve(got[0].pedido, ALLOW)
        status, payload = await task
    assert status == 200 and payload == decision(ALLOW)


async def test_negar_e_clique_atrasado():
    perms = Permissions()
    got = await opened(perms)
    closed: list = []

    async def on_close(req, result):
        closed.append(result)

    perms.on_close = on_close
    async with make_server(perms).run() as port:
        task = asyncio.create_task(post(port, json.dumps(BODY).encode()))
        await wait_for(lambda: got)
        assert await perms.resolve(got[0].pedido, DENY)
        assert not await perms.resolve(got[0].pedido, ALLOW)  # já respondido
        _, payload = await task
    assert payload == decision(DENY) and closed == [DENY]


async def test_resposta_na_aba_devolve_vazio():
    perms = Permissions()
    got = await opened(perms)
    async with make_server(perms).run() as port:
        task = asyncio.create_task(post(port, json.dumps(BODY).encode()))
        await wait_for(lambda: got)
        await perms.resolve_session("s1", IN_TAB)
        _, payload = await task
    assert payload == {}
    assert perms.pending_for("s1") is None


async def test_pedido_novo_encerra_o_anterior():
    perms = Permissions()
    got = await opened(perms)
    async with make_server(perms).run() as port:
        first = asyncio.create_task(post(port, json.dumps(BODY).encode()))
        await wait_for(lambda: got)
        second = asyncio.create_task(post(port, json.dumps(BODY).encode()))
        _, payload1 = await first
        assert payload1 == {}
        await wait_for(lambda: len(got) >= 2)
        await perms.resolve(got[1].pedido, ALLOW)
        _, payload2 = await second
    assert payload2 == decision(ALLOW)


async def test_prazo_esgotado():
    perms = Permissions(timeout=0.2)
    async with make_server(perms).run() as port:
        status, payload = await post(port, json.dumps(BODY).encode())
    assert status == 200 and payload == {}
    assert perms.pending_for("s1") is None


@pytest.mark.parametrize(
    ("kw", "status"),
    [
        ({"token": "errado"}, 401),
        ({"token": None}, 401),
        ({"path": "/outra"}, 404),
        ({"method": "GET"}, 404),
    ],
)
async def test_recusas(kw, status):
    perms = Permissions()
    async with make_server(perms).run() as port:
        got, _ = await post(port, json.dumps(BODY).encode(), **kw)
    assert got == status


async def test_corpo_grande_recusado():
    perms = Permissions()
    async with make_server(perms).run() as port:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            b"POST /permissao HTTP/1.1\r\nAuthorization: Bearer tk-1\r\n"
            b"Content-Length: 999999\r\n\r\n"
        )
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(), 5)
        writer.close()
    assert raw.startswith(b"HTTP/1.1 413")


async def test_outro_evento_e_ignorado():
    perms = Permissions()
    async with make_server(perms).run() as port:
        status, payload = await post(port, json.dumps({"hook_event_name": "Stop"}).encode())
    assert status == 200 and payload == {}
