import asyncio
import contextlib

import pytest

from jarvis.mcp_client import CoreUnavailable, ResilientCore, ToolResult


class FakeClient:
    async def openai_tools(self):
        return [{"type": "function", "function": {"name": "painel"}}]

    async def call(self, name, args):
        return ToolResult(True, {"ok": name})


def connector(script):
    """Cada tentativa: "falha" (não conecta) ou "fica" (conecta e segue)."""
    attempts = []

    @contextlib.asynccontextmanager
    async def connect(url, token):
        step = script[min(len(attempts), len(script) - 1)]
        attempts.append(step)
        if step == "falha":
            raise ConnectionError("All connection attempts failed")
        yield FakeClient()

    return connect, attempts


async def test_sem_nucleo_sobe_e_reconecta_quando_ele_volta():
    connect, attempts = connector(["falha", "falha", "fica"])
    core = ResilientCore("u", "t", retry=0.01, connect=connect)
    task = asyncio.create_task(core.run())
    with pytest.raises(CoreUnavailable):
        await core.call("painel", {})
    assert await core.openai_tools() == []
    await asyncio.wait_for(core.ready.wait(), 1)
    assert core.online and (await core.call("painel", {})).data == {"ok": "painel"}
    assert len(await core.openai_tools()) == 1 and attempts[:3] == ["falha", "falha", "fica"]
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_queda_da_sessao_nao_derruba_e_volta():
    attempts = []

    @contextlib.asynccontextmanager
    async def drop_then_stay(url, token):
        # 1ª: a sessão cai logo depois de abrir (como o Docker parando); 2ª: fica
        step = "cai" if not attempts else "fica"
        attempts.append(step)
        if step == "cai":
            raise ExceptionGroup("sessão caiu", [ConnectionError("docker parou")])
        yield FakeClient()

    core = ResilientCore("u", "t", retry=0.01, connect=drop_then_stay)
    task = asyncio.create_task(core.run())
    await asyncio.wait_for(core.ready.wait(), 1)
    assert core.online and attempts == ["cai", "fica"]
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert not core.online


async def test_painel_e_pergunta_sem_nucleo():
    from tests.fakes import StreamingScriptedLLM, reply
    from tests.jarvis.test_voice import brain

    class DownCore:
        async def openai_tools(self):
            return []

        async def call(self, name, args):
            raise CoreUnavailable("núcleo indisponível")

    llm = StreamingScriptedLLM(reply("O núcleo está fora do ar, senhor."))
    b = brain(llm, DownCore())

    async def extras(faturas):
        assert faturas is None
        return {"clima": {"agora": 28}, "mac": {"memoria_livre": 34}}

    b.panel_extras = extras
    got = []

    async def emit(ev):
        got.append(ev)

    await b.panel("p1", emit)
    assert got[-1].data == {
        "erro": "núcleo indisponível",
        "clima": {"agora": 28},
        "mac": {"memoria_livre": 34},
    }
    await b.ask("r1", "quanto gastei?", emit)
    assert got[-1].type == "done" and "fora do ar" in got[-1].text
    assert "indisponível agora" in llm.calls[0]["messages"][0]["content"]
