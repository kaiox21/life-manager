import asyncio
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from jarvis.sessions import BUFFER_BYTES, Folders, Session, Sessions, clean_text

# Programa falso no lugar do `claude`: anuncia os argumentos e a variável do terminal, ecoa o
# que recebe (modo raw) e responde ao SIGWINCH com o tamanho da janela.
FAKE = r"""
import os, signal, sys, termios, tty, fcntl, struct, json
def size(*_):
    rows, cols, _, _ = struct.unpack("HHHH", fcntl.ioctl(0, termios.TIOCGWINSZ, b"\0" * 8))
    os.write(1, f"<tam {cols}x{rows}>".encode())
signal.signal(signal.SIGWINCH, size)
tty.setraw(0)
os.write(1, ("<pronto " + json.dumps({"argv": sys.argv[1:], "t": os.environ.get("JARVIS_TERMINAL"),
    "tok": bool(os.environ.get("JARVIS_HOOK_TOKEN")),
    "key": os.environ.get("ANTHROPIC_API_KEY")}) + ">").encode())
while True:
    data = os.read(0, 1024)
    if not data:
        break
    os.write(1, b"<eco " + data + b">")
"""


def fake_command(_claude: str, args: list[str]) -> list[str]:
    return [sys.executable, "-c", FAKE, *args]


def exec_command(_claude: str, args: list[str]) -> list[str]:
    # o mesmo `exec "$0" "$@"` do comando real, com /bin/sh no lugar do zsh de login
    return ["/bin/sh", "-c", 'exec "$0" "$@"', sys.executable, "-c", FAKE, *args]


@pytest.fixture
def roots(tmp_path: Path) -> Path:
    for p in ("proj/life-manager/app", "proj/sisdec", "outra/sisdec", "proj/a/b/c"):
        (tmp_path / p).mkdir(parents=True)
    return tmp_path


def make(roots: Path, **kw) -> tuple[Sessions, list[bytes], list[Session]]:
    s = Sessions(
        Folders([roots / "proj", roots / "outra"]),
        command=kw.pop("command", fake_command),
        memory=kw.pop("memory", lambda: 50),
        tabs_file=kw.pop("tabs_file", roots / "abas.json"),
        **kw,
    )
    out: list[bytes] = []
    exits: list[Session] = []
    s.on_output = lambda sess, data: out.append(data)
    s.on_exit = exits.append
    return s, out, exits


async def wait_for(pred, limit: float = 5.0) -> None:
    end = asyncio.get_running_loop().time() + limit
    while not pred():
        if asyncio.get_running_loop().time() > end:
            raise AssertionError("tempo esgotado")
        await asyncio.sleep(0.02)


def settings(token: str) -> str:
    return json.dumps({"hooks": {}, "tk": "x"})


async def test_abre_ecoa_e_encerra(roots, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "segredo-do-cerebro")
    s, out, exits = make(roots)
    sess = s.start(roots / "proj/sisdec", settings)
    await wait_for(lambda: b"<pronto" in b"".join(out))
    hello = b"".join(out).decode()
    assert '"--settings"' in hello and f'"t": "{sess.sid}"' in hello and '"tok": true' in hello
    assert '"key": null' in hello  # segredos do cérebro não vão para a sessão
    assert s.write(sess.sid, b"oi")
    await wait_for(lambda: b"<eco oi>" in b"".join(out))
    assert await s.close(sess.sid)
    assert sess.proc.poll() is not None
    assert exits == [sess] and s.open == {}
    assert s.closed == {}  # fechada pelo Kaio: a aba some


async def test_pid_e_do_programa_depois_do_exec(roots):
    s, out, _ = make(roots, command=exec_command)
    sess = s.start(roots / "proj/sisdec", settings)
    await wait_for(lambda: b"<pronto" in b"".join(out))
    ps = await asyncio.create_subprocess_exec(
        "ps", "-o", "comm=", "-p", str(sess.pid), stdout=asyncio.subprocess.PIPE
    )
    comm, _ = await ps.communicate()
    assert b"python" in comm.lower()
    await s.close(sess.sid)


async def test_resize_e_redesenho(roots):
    s, out, _ = make(roots)
    sess = s.start(roots / "proj/sisdec", settings)
    await wait_for(lambda: b"<pronto" in b"".join(out))
    s.resize(sess.sid, 100, 30)
    await wait_for(lambda: b"<tam 100x30>" in b"".join(out))
    out.clear()
    s.redraw(sess.sid)
    await wait_for(lambda: b"<tam 100x30>" in b"".join(out))
    await s.close(sess.sid)


async def test_texto_vai_colado_sem_controles_e_com_enter(roots):
    s, out, _ = make(roots)
    sess = s.start(roots / "proj/sisdec", settings)
    await wait_for(lambda: b"<pronto" in b"".join(out))
    sent = await s.send_text(sess.sid, "roda\x03 os\x1b testes\r\nagora")
    assert sent == "roda os testes\nagora"
    await wait_for(lambda: b"\r>" in b"".join(out))
    echoed = b"".join(out)
    assert b"\x1b[200~roda os testes\nagora\x1b[201~" in echoed and b"\x03" not in echoed
    await s.close(sess.sid)


def test_limpa_controles_e_corta():
    assert clean_text("a\x00b\x7fc\x9b\td\ne") == "abc\td\ne"
    assert len(clean_text("x" * 5000)) == 4000


async def test_programa_sai_sozinho_vira_aba_encerrada_e_e_gravada(roots):
    s, out, exits = make(roots)
    sess = s.start(roots / "proj/sisdec", settings)
    sess.numero, sess.sessao = 3, "abc-123"
    await wait_for(lambda: b"<pronto" in b"".join(out))
    os.killpg(sess.pid, 15)
    await wait_for(lambda: exits)
    assert [t["aberta"] for t in s.tabs()] == [False]
    saved = json.loads((roots / "abas.json").read_text())
    assert saved == [{"numero": 3, "pasta": str(roots / "proj/sisdec"), "sessao": "abc-123"}]
    assert stat.S_IMODE((roots / "abas.json").stat().st_mode) == 0o600


async def test_abas_da_execucao_anterior_viram_encerradas(roots):
    (roots / "abas.json").write_text(
        json.dumps(
            [
                {"numero": 2, "pasta": str(roots / "proj/sisdec"), "sessao": "s-2"},
                {"numero": 5, "pasta": "/etc", "sessao": "fora"},  # fora das pastas: ignorada
            ]
        )
    )
    s, _, _ = make(roots)
    s.load_previous()
    assert [(c.numero, c.sessao) for c in s.closed.values()] == [(2, "s-2")]
    tab = s.tabs()[0]
    assert tab["aberta"] is False and tab["pasta"] == "sisdec"
    assert await s.close(tab["sid"])  # "×" na aba encerrada
    assert s.closed == {}


async def test_retomar_passa_resume(roots):
    s, out, _ = make(roots)
    sess = s.start(roots / "proj/sisdec", settings, resume="s-2")
    await wait_for(lambda: b"<pronto" in b"".join(out))
    assert '"--resume", "s-2"' in b"".join(out).decode()
    await s.close(sess.sid)


async def test_buffer_circular(roots):
    sess = Session("x", roots, 1, -1, None, "t")  # type: ignore[arg-type]
    sess.remember(b"a" * BUFFER_BYTES)
    sess.remember(b"fim")
    assert len(sess.buffer) == BUFFER_BYTES and sess.buffer.endswith(b"fim")


# --- pastas e limites (tarefa 1.2)


def test_pasta_pelo_nome(roots):
    f = Folders([roots / "proj", roots / "outra"])
    assert f.resolve("life-manager") == {"pasta": roots / "proj/life-manager"}
    assert f.resolve("LIFE-MANAGER") == {"pasta": roots / "proj/life-manager"}
    assert "opcoes" in f.resolve("sisdec")  # duas pastas com o mesmo nome
    assert "erro" in f.resolve("c")  # 3 níveis abaixo da raiz: fora
    assert "erro" in f.resolve("nao-existe")


def test_pasta_por_caminho(roots, tmp_path_factory):
    f = Folders([roots / "proj"])
    assert f.resolve(str(roots / "proj/sisdec")) == {"pasta": roots / "proj/sisdec"}
    assert "erro" in f.resolve("/")
    assert "erro" in f.resolve(str(roots / "proj/sisdec/../../outra/sisdec"))
    fora = tmp_path_factory.mktemp("fora")
    (roots / "proj/atalho").symlink_to(fora)
    assert "erro" in f.resolve(str(roots / "proj/atalho"))
    assert not f.allowed(roots / "proj/atalho")


async def test_limite_de_sessoes(roots):
    s, out, _ = make(roots, max_sessions=2)
    a = s.start(roots / "proj/sisdec", settings)
    b = s.start(roots / "proj/life-manager", settings)
    with pytest.raises(RuntimeError, match="limite é 2"):
        s.start(roots / "proj/life-manager", settings)
    await s.close(a.sid)
    await s.close(b.sid)


async def test_pouca_memoria(roots):
    s, _, _ = make(roots, memory=lambda: 12, min_memory=20)
    assert "pouca memória" in (s.can_open() or "")
    with pytest.raises(RuntimeError, match="pouca memória"):
        s.start(roots / "proj/sisdec", settings)
    s2, _, _ = make(roots, memory=lambda: None)
    assert s2.can_open() is None  # sem a leitura da memória, não bloqueia


async def test_pasta_fora_recusada_no_start(roots):
    s, _, _ = make(roots)
    with pytest.raises(RuntimeError, match="fora das pastas"):
        s.start(Path("/"), settings)
