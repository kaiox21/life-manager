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
        "tocar_musica",
        "timer",
        "area_transferencia",
        "listar_terminais",
        "abrir_terminal",
        "mandar_terminal",
        "fechar_terminal",
        "silenciar_avisos",
        "modo_estudo",
        "abrir_projeto",
        "rascunho",
    }


# --- abrir projeto e rascunhos (jarvis-projetos)

from jarvis.local_tools import DRAFT_REPLY  # noqa: E402


class FakeControl:
    def __init__(self, resolved, opened=None):
        self.resolved = resolved
        self.opened = opened or {
            "status": "aberto",
            "numero": 3,
            "pasta": "NC-BARBER",
            "tipo": "shell",
            "sessao": "$3",
        }
        self.calls: list[tuple[Path, bool]] = []

    def resolve(self, pasta):
        return self.resolved

    async def open(self, pasta, claude=False):
        raise AssertionError("abrir_projeto resolve antes e usa open_in")

    async def open_in(self, path, claude=False):
        self.calls.append((path, claude))
        return dict(self.opened)

    async def send(self, numero, texto, confirm):
        raise AssertionError("não manda nada")

    async def close(self, numero, confirm):
        raise AssertionError("não fecha nada")


PASTA = Path("/Users/k/Projetos/NC-BARBER")


async def test_abrir_projeto_abre_editor_e_terminal():
    r, c = FakeRunner(), FakeControl({"pasta": PASTA})
    t = tools(r, control=c)
    ok, out = await t.call("abrir_projeto", {"nome": "NC Barber"})
    assert ok and out["status"] == "aberto" and out["pasta"] == "NC-BARBER"
    assert out["editor"] == "aberto" and out["terminal"] == {
        "numero": 3,
        "tipo": "shell",
        "existente": False,
    }
    assert out["_fala"] == "NC-BARBER aberto no Visual Studio Code, senhor. Terminal 3."
    assert out["_painel_fechar"] is True
    assert r.calls == [(["open", "-a", "Visual Studio Code", str(PASTA)], None)]
    assert c.calls == [(PASTA, False)]
    assert "_fala" not in t.for_model("abrir_projeto", out)
    assert "_painel_fechar" not in t.for_model("abrir_projeto", out)


async def test_abrir_projeto_sem_editor_segue_com_o_terminal():
    r = FakeRunner(returncode=1)
    _, out = await tools(r, control=FakeControl({"pasta": PASTA})).call(
        "abrir_projeto", {"nome": "NC Barber"}
    )
    assert out["status"] == "aberto"
    assert out["editor"] == "não encontrei o app 'Visual Studio Code'"
    assert out["_fala"] == (
        "NC-BARBER aberto no Terminal 3, senhor. Não encontrei o Visual Studio Code."
    )


async def test_abrir_projeto_reaproveita_e_abre_claude():
    c = FakeControl({"pasta": PASTA}, {"status": "existente", "numero": 2, "tipo": "shell"})
    _, out = await tools(FakeRunner(), control=c).call("abrir_projeto", {"nome": "NC Barber"})
    assert out["terminal"]["existente"] is True and "Terminal 2" in out["_fala"]
    c = FakeControl({"pasta": PASTA}, {"status": "aberto", "numero": 4, "tipo": "claude"})
    _, out = await tools(FakeRunner(), control=c).call(
        "abrir_projeto", {"nome": "NC Barber", "claude": True}
    )
    assert c.calls == [(PASTA, True)] and out["terminal"]["tipo"] == "claude"


async def test_abrir_projeto_fora_da_lista_ou_ambiguo_nao_abre_nada():
    r = FakeRunner()
    _, out = await tools(r, control=FakeControl({"erro": "fora", "permitidas": ["~/P"]})).call(
        "abrir_projeto", {"nome": "/"}
    )
    assert out["erro"] == "fora" and r.calls == []
    _, out = await tools(r, control=FakeControl({"opcoes": ["~/A/sisdec", "~/P/sisdec"]})).call(
        "abrir_projeto", {"nome": "sisdec"}
    )
    assert out["opcoes"] == ["~/A/sisdec", "~/P/sisdec"] and r.calls == []


async def test_abrir_projeto_terminal_falha_mas_editor_abriu():
    c = FakeControl({"pasta": PASTA}, {"erro": "pouca memória"})
    _, out = await tools(FakeRunner(), control=c).call("abrir_projeto", {"nome": "NC Barber"})
    assert out["erro"] == "pouca memória" and out["editor"] == "aberto" and "_fala" not in out


TEXTO = "Prezado professor,\n\nEstive doente na semana da prova.\n\nAtenciosamente,\nKaio"


async def test_rascunho_copia_grava_e_nao_volta_ao_modelo(tmp_path):
    r = FakeRunner()
    t = tools(r, drafts_dir=tmp_path / "rascunhos")
    ok, out = await t.call(
        "rascunho",
        {
            "tipo": "email",
            "para": "professor de redes",
            "assunto": "Segunda chamada",
            "texto": TEXTO,
        },
    )
    assert ok and out["status"] == "pronto" and out["caracteres"] == len(TEXTO)
    assert out["_fala"] == DRAFT_REPLY and out["texto"] == TEXTO
    assert r.calls == [(["pbcopy"], TEXTO.encode())]
    (saved,) = list((tmp_path / "rascunhos").glob("*.md"))
    assert saved.name == "2026-10-08-170000-segunda-chamada.md"
    assert saved.read_text() == (
        "# email\npara: professor de redes\nassunto: Segunda chamada\n\n" + TEXTO + "\n"
    )
    assert out["arquivo"] == str(saved)  # fora da pasta pessoal falsa: caminho inteiro
    seen = t.for_model("rascunho", out)
    assert "texto" not in seen and "_fala" not in seen and seen["caracteres"] == len(TEXTO)


async def test_rascunho_mantem_os_50_mais_novos(tmp_path):
    d = tmp_path / "rascunhos"
    d.mkdir()
    for i in range(55):
        (d / f"2026-09-{i % 28 + 1:02d}-{i:06d}-velho.md").write_text("x")
    t = tools(FakeRunner(), drafts_dir=d)
    await t.call("rascunho", {"tipo": "mensagem", "para": "Netto", "texto": "O site volta amanhã."})
    files = sorted(d.glob("*.md"))
    assert len(files) == 50 and files[-1].name == "2026-10-08-170000-netto.md"


async def test_rascunho_longo_demais_e_recusado(tmp_path):
    r = FakeRunner()
    ok, msg = await tools(r, drafts_dir=tmp_path).call(
        "rascunho", {"tipo": "texto", "texto": "x" * 6001}
    )
    assert not ok and "texto" in msg and r.calls == []


async def test_botao_copiar_so_dentro_do_limite():
    r = FakeRunner()
    t = tools(r)
    await t.rascunho_copiar("x" * 7000)
    assert r.calls == []
    await t.rascunho_copiar("oi")
    assert r.calls == [(["pbcopy"], b"oi")]
