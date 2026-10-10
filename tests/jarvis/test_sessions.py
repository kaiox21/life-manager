import asyncio
import os
import signal
import sys
from pathlib import Path

import pytest

from jarvis.sessions import Folders, PtyClient, clean_text, memory_level

# Programa falso no lugar do `tmux attach`: anuncia que está pronto, ecoa o que recebe
# (modo raw) e responde ao SIGWINCH com o tamanho da janela.
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


async def wait_for(pred, limit: float = 5.0) -> None:
    end = asyncio.get_running_loop().time() + limit
    while not pred():
        if asyncio.get_running_loop().time() > end:
            raise AssertionError("tempo esgotado")
        await asyncio.sleep(0.02)


@pytest.fixture
def roots(tmp_path: Path) -> Path:
    for p in ("proj/life-manager/app", "proj/sisdec", "outra/sisdec", "proj/a/b/c"):
        (tmp_path / p).mkdir(parents=True)
    return tmp_path


def test_limpa_controles_e_corta():
    assert clean_text("a\x00b\x7fc\x9b\td\ne") == "abc\td\ne"
    assert len(clean_text("x" * 5000)) == 4000


def start(on_output, on_exit=lambda: None, **kw) -> PtyClient:
    return PtyClient(
        [sys.executable, "-c", FAKE],
        {"PATH": "/usr/bin:/bin"},
        Path.home(),
        on_output,
        on_exit,
        **kw,
    )


async def test_cliente_ecoa_redimensiona_e_fecha():
    out: list[bytes] = []
    exits: list[bool] = []
    c = start(out.append, lambda: exits.append(True), cols=90, rows=20)
    await wait_for(lambda: b"<pronto" in b"".join(out))
    assert c.write(b"oi")
    await wait_for(lambda: b"<eco oi>" in b"".join(out))
    c.resize(100, 30)
    await wait_for(lambda: b"<tam 100x30>" in b"".join(out))
    await c.close()
    assert c.closed and c.proc.poll() is not None and exits == [True]
    assert not c.write(b"x")


async def test_programa_que_sai_avisa():
    out: list[bytes] = []
    exits: list[bool] = []
    c = start(out.append, lambda: exits.append(True))
    await wait_for(lambda: b"<pronto" in b"".join(out))
    os.killpg(c.pid, signal.SIGTERM)
    await wait_for(lambda: exits)
    assert c.closed


async def test_pausa_segura_a_saida():
    out: list[bytes] = []
    c = start(out.append)
    await wait_for(lambda: b"<pronto" in b"".join(out))
    c.pause(True)
    c.write(b"zz")
    await asyncio.sleep(0.3)
    assert b"<eco zz>" not in b"".join(out)
    c.pause(False)
    await wait_for(lambda: b"<eco zz>" in b"".join(out))
    await c.close()


def test_memoria_le_um_numero_ou_nada():
    level = memory_level()
    assert level is None or 0 <= level <= 100


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
