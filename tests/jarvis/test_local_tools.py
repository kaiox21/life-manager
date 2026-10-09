from datetime import datetime
from pathlib import Path

import pytest

from jarvis.local_tools import Completed, LocalTools


class FakeRunner:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.calls: list[tuple[list[str], bytes | None]] = []
        self.stdout = stdout
        self.returncode = returncode

    async def __call__(self, argv, stdin):
        assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
        self.calls.append((argv, stdin))
        return Completed(self.returncode, self.stdout, "")


def tools(runner, **kw):
    return LocalTools(
        runner=runner,
        config=kw.pop("config", {}),
        home=Path("/Users/k"),
        now=lambda: datetime(2026, 10, 8, 17, 0),
        **kw,
    )


async def test_abrir_app_sem_shell():
    r = FakeRunner()
    ok, out = await tools(r).call("abrir_app", {"nome": "Safari"})
    assert ok and out == {"status": "aberto", "app": "Safari"}
    assert r.calls == [(["open", "-a", "Safari"], None)]


async def test_nome_malicioso_nao_executa_nada():
    r = FakeRunner()
    ok, out = await tools(r).call("abrir_app", {"nome": "Safari; rm -rf ~"})
    assert ok and "inválido" in out["erro"]
    assert r.calls == []


async def test_app_inexistente():
    _, out = await tools(FakeRunner(returncode=1)).call("abrir_app", {"nome": "Nada"})
    assert "Não encontrei" in out["erro"]


async def test_buscar_arquivo_limita_e_encurta_caminho():
    paths = "\n".join(f"/Users/k/Docs/arq{i}.pdf" for i in range(30))
    r = FakeRunner(stdout=paths)
    _, out = await tools(r).call("buscar_arquivo", {"texto": "contrato"})
    assert r.calls[0][0] == ["mdfind", "-onlyin", "/Users/k", "contrato"]
    assert out["total"] == 30 and len(out["arquivos"]) == 20
    assert out["arquivos"][0] == "~/Docs/arq0.pdf"


async def test_atalho_fora_da_lista_e_recusado():
    r = FakeRunner()
    t = tools(r, config={"atalhos_permitidos": ["Modo Foco"]})
    _, out = await t.call("rodar_atalho", {"nome": "Apagar tudo"})
    assert "lista permitida" in out["erro"] and r.calls == []
    _, out = await t.call("rodar_atalho", {"nome": "Modo Foco"})
    assert out["status"] == "executado"
    assert r.calls == [(["shortcuts", "run", "Modo Foco"], None)]


async def test_lista_vazia_por_padrao():
    _, out = await tools(FakeRunner()).call("rodar_atalho", {"nome": "Qualquer"})
    assert out["permitidos"] == []


async def test_spotify_com_script_fixo():
    r = FakeRunner()
    _, out = await tools(r).call("controlar_musica", {"acao": "pausar"})
    assert out == {"status": "ok", "acao": "pausar"}
    assert r.calls[0][0] == ["osascript", "-e", 'tell application "Spotify" to pause']


async def test_timer_texto_vai_como_argumento(monkeypatch):
    r = FakeRunner()
    import jarvis.local_tools as lt

    async def no_sleep(_):
        return None

    monkeypatch.setattr(lt.asyncio, "sleep", no_sleep)
    t = tools(r)
    _, out = await t.call("timer", {"minutos": 10, "texto": 'café" & do shell script "x'})
    assert out["hora"] == "17:10"
    for task in list(t._timers):
        await task
    argv = r.calls[0][0]
    assert argv[0] == "osascript" and argv[-1] == 'café" & do shell script "x'
    assert all("do shell script" not in a for a in argv[:-1])


async def test_ler_clipboard_exige_confirmacao():
    r = FakeRunner(stdout="segredo")
    asked: list[str] = []

    async def nega(msg):
        asked.append(msg)
        return False

    _, out = await tools(r, confirm=nega).call("area_transferencia", {"acao": "ler"})
    assert out["status"] == "negado" and r.calls == [] and asked

    async def aceita(msg):
        return True

    _, out = await tools(r, confirm=aceita).call("area_transferencia", {"acao": "ler"})
    assert out["conteudo"] == "segredo"


async def test_escrever_clipboard_por_stdin():
    r = FakeRunner()
    _, out = await tools(r).call("area_transferencia", {"acao": "escrever", "texto": "olá"})
    assert out["status"] == "copiado"
    assert r.calls == [(["pbcopy"], "olá".encode())]


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("timer", {"minutos": 0}),
        ("controlar_musica", {"acao": "apagar"}),
        ("abrir_app", {"nome": "Safari", "extra": 1}),
        ("inexistente", {}),
    ],
)
async def test_validacao(name, args):
    ok, msg = await tools(FakeRunner()).call(name, args)
    assert not ok and isinstance(msg, str)


def test_schemas_para_o_modelo():
    names = {t["function"]["name"] for t in tools(FakeRunner()).openai_tools()}
    assert names == {
        "abrir_app",
        "buscar_arquivo",
        "rodar_atalho",
        "controlar_musica",
        "timer",
        "area_transferencia",
        "listar_terminais",
    }
