import os
import time
from datetime import date

from jarvis.briefing import Weather
from jarvis.local_tools import Completed
from jarvis.panel_extras import PanelExtras, bill_days, parse_battery, parse_swap
from jarvis.sessions import Folders


class Runner:
    def __init__(self, outputs=None, fail=()):
        self.outputs = outputs or {}
        self.fail = set(fail)
        self.calls = []

    async def __call__(self, argv, stdin):
        self.calls.append(argv)
        key = argv[-1] if argv[0] != "osascript" else "osascript"
        if key in self.fail:
            return Completed(1, "", "erro")
        return Completed(0, self.outputs.get(key, ""), "")


MAC = {
    "kern.memorystatus_level": "37\n",
    "vm.swapusage": "total = 2048.00M  used = 812.25M  free = 1235.75M  (encrypted)\n",
    "batt": "Now drawing from 'Battery Power'\n"
    " -InternalBattery-0 (id=1)\t84%; discharging; 5:12\n",
    "osascript": "Tempo Perdido\tLegião Urbana\tplaying\n",
}


def extras(tmp_path, runner, config=None, fetch=None):
    async def sunny(lat, lon):
        return Weather(27.4, 34.1, 21.9, 0)

    return PanelExtras(
        runner,
        Folders([tmp_path]),
        lambda: config or {},
        lambda: (-15.79, -47.88, "Brasília"),
        fetch=fetch or sunny,
        today=lambda: date(2026, 10, 10),
    )


def test_le_swap_e_bateria():
    assert parse_swap(MAC["vm.swapusage"]) == 0.8
    assert parse_swap("total = 4.00G  used = 1.50G  free = 2.50G") == 1.5
    assert parse_battery(MAC["batt"]) == {"pct": 84, "carregando": False}
    assert parse_battery("-InternalBattery-0\t100%; charged; 0:00 remaining")["carregando"]
    assert parse_battery("Now drawing from 'AC Power'") is None  # Mac sem bateria


def test_dias_ate_fechar_e_fracao_do_ciclo():
    faturas = [
        {"cartao": "Itaú", "fechamento": "25/10/2026"},
        {"cartao": "Nubank", "fechamento": "12/10/2026"},
    ]
    out = bill_days(faturas, date(2026, 10, 10))
    assert [f["cartao"] for f in out] == ["Nubank", "Itaú"]  # a que fecha primeiro
    assert out[0]["dias_para_fechar"] == 2 and out[0]["fracao_ciclo"] == 0.93
    assert out[1]["dias_para_fechar"] == 15


async def test_junta_tudo(tmp_path):
    (tmp_path / "life-manager").mkdir()
    out = await extras(tmp_path, Runner(MAC))([{"cartao": "Nubank", "fechamento": "12/10/2026"}])
    assert out["clima"] == {
        "agora": 27.4,
        "max": 34.1,
        "min": 21.9,
        "chuva": 0,
        "cidade": "Brasília",
    }
    assert out["mac"] == {
        "memoria_livre": 37,
        "swap_gb": 0.8,
        "bateria": {"pct": 84, "carregando": False},
    }
    assert out["musica"] == {"faixa": "Tempo Perdido", "artista": "Legião Urbana", "tocando": True}
    assert out["projetos"] == [{"nome": "life-manager", "caminho": str(tmp_path / "life-manager")}]
    assert out["faturas"][0]["dias_para_fechar"] == 2


async def test_cada_parte_falha_sozinha(tmp_path):
    async def offline(lat, lon):
        return None

    async def broken(lat, lon):
        raise RuntimeError("boom")

    out = await extras(tmp_path, Runner(MAC, fail={"osascript"}), fetch=offline)()
    assert out["clima"] is None and out["musica"] is None and out["mac"]["memoria_livre"] == 37
    out = await extras(tmp_path, Runner({}), fetch=broken)()
    assert out["clima"] is None and out["mac"]["swap_gb"] is None and "faturas" not in out


async def test_clima_guardado_por_10_min(tmp_path):
    calls = []

    async def fetch(lat, lon):
        calls.append(1)
        return Weather(20, 25, 15, 0)

    e = extras(tmp_path, Runner(MAC), fetch=fetch)
    await e.weather()
    await e.weather()
    assert calls == [1]


def test_projetos_da_config_ou_os_mais_recentes(tmp_path):
    for i, name in enumerate(["a", "b", "c", "d", "e", "f", "g", ".oculto"]):
        (tmp_path / name).mkdir()
        os.utime(tmp_path / name, (time.time() - 100 + i, time.time() - 100 + i))
    names = [p["nome"] for p in extras(tmp_path, Runner()).projects()]
    assert names == ["g", "f", "e", "d", "c", "b"]  # 6 mais recentes, sem ocultos
    chosen = extras(tmp_path, Runner(), config={"projetos": ["c", "/etc", "nao-existe"]})
    assert [p["nome"] for p in chosen.projects()] == ["c"]  # fora das permitidas some


# --- painel no cérebro e botões no servidor


async def test_painel_do_cerebro_junta_os_extras():
    from jarvis.mcp_client import ToolResult
    from tests.fakes import StreamingScriptedLLM
    from tests.jarvis.test_agent import FakeCore
    from tests.jarvis.test_voice import brain

    core = FakeCore({"painel": ToolResult(True, {"faturas": [{"fechamento": "12/10/2026"}]})})
    b = brain(StreamingScriptedLLM(), core)
    seen = []

    async def fake_extras(faturas):
        seen.append(faturas)
        return {"clima": None, "faturas": [{"fechamento": "12/10/2026", "dias_para_fechar": 2}]}

    b.panel_extras = fake_extras
    got = []

    async def emit(ev):
        got.append(ev)

    await b.panel("p1", emit)
    assert seen == [[{"fechamento": "12/10/2026"}]]
    assert got[0].data["faturas"][0]["dias_para_fechar"] == 2 and "clima" in got[0].data


async def test_botoes_resumo_e_musica_no_servidor():
    import asyncio
    import json

    from websockets.asyncio.client import connect

    from jarvis import events
    from jarvis.server import JarvisServer

    class B:
        def __init__(self):
            self.calls = []

        async def ask(self, rid, text, emit, mode="texto"):
            pass

        async def resolve_confirmation(self, cid, ok):
            pass

        async def panel(self, rid, emit):
            pass

        async def briefing(self, rid, emit):
            self.calls.append("resumo")
            await emit(events.done(rid, "Bom dia, senhor."))

        async def evening(self, rid, emit):
            self.calls.append("boa noite")
            await emit(events.done(rid, "Boa noite, senhor."))

        async def local_action(self, acao):
            self.calls.append(acao)

    b = B()
    server = JarvisServer(b, token="tk")
    async with server.run(session_file=None) as port:  # noqa: SIM117 (a porta vem do 1º)
        async with connect(f"ws://127.0.0.1:{port}/?token=tk") as ws:
            await ws.send(json.dumps({"type": "briefing", "id": "r1"}))
            assert json.loads(await asyncio.wait_for(ws.recv(), 2))["type"] == "done"
            await ws.send(json.dumps({"type": "evening", "id": "r2"}))
            assert json.loads(await asyncio.wait_for(ws.recv(), 2))["type"] == "done"
            await ws.send(json.dumps({"type": "local", "acao": "musica_tocar_pausar"}))
            await asyncio.sleep(0.1)
    assert b.calls == ["resumo", "boa noite", "musica_tocar_pausar"]


async def test_acao_local_fora_da_lista_nao_faz_nada():
    from tests.fakes import StreamingScriptedLLM
    from tests.jarvis.test_agent import FakeCore
    from tests.jarvis.test_voice import brain

    b = brain(StreamingScriptedLLM(), FakeCore())
    calls = []

    async def alternar():
        calls.append("alternar")

    b._local.musica_alternar = alternar
    await b.local_action("rm -rf")
    await b.local_action("musica_tocar_pausar")
    assert calls == ["alternar"]
