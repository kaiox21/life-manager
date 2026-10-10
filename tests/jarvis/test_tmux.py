import asyncio
import os
import secrets
from pathlib import Path

import pytest

from jarvis.tmux import Tmux, find_tmux, parse_panes

CONF = Path(__file__).resolve().parents[2] / "jarvis/tmux.conf"
pytestmark = pytest.mark.skipif(find_tmux() is None, reason="sem tmux")


@pytest.fixture
async def tmux():
    t = Tmux(socket=f"jt-teste-{secrets.token_hex(3)}", conf=CONF)
    yield t
    await t.run("kill-server")


async def until(pred, limit: float = 5.0):
    end = asyncio.get_running_loop().time() + limit
    while True:
        value = pred()
        if asyncio.iscoroutine(value):
            value = await value
        if value:
            return value
        if asyncio.get_running_loop().time() > end:
            raise AssertionError("tempo esgotado")
        await asyncio.sleep(0.1)


async def test_configuracao_carregada(tmux, tmp_path):
    assert await tmux.new_session(tmp_path)
    _, out = await tmux.run("show-options", "-g")
    opts = dict(line.split(" ", 1) for line in out.splitlines() if " " in line)
    assert opts["prefix"] == "C-]" and opts["mouse"] == "on" and opts["status"] == "off"
    _, server = await tmux.run("show-options", "-s")
    assert "escape-time 10" in server and "extended-keys on" in server


async def test_sessao_aberta_pelo_jarvis_aparece_na_lista(tmux, tmp_path):
    sessao = await tmux.new_session(tmp_path)
    (pane,) = await until(tmux.panes)
    assert pane.sessao == sessao and pane.origem == "jarvis" and not pane.aba
    assert os.path.realpath(pane.pasta) == os.path.realpath(tmp_path)  # noqa: ASYNC240
    assert pane.shell_livre and pane.clientes == 0
    assert await tmux.set_option(sessao, "@jarvis_aba", "1")
    (pane,) = await tmux.panes()
    assert pane.aba
    assert await tmux.unset_option(sessao, "@jarvis_aba")
    assert await tmux.kill(sessao)
    assert await tmux.panes() == []


async def test_segredo_do_cerebro_nao_chega_ao_terminal(tmux, tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_SEGREDO_TESTE", "vazou")
    sessao = await tmux.new_session(tmp_path)
    (pane,) = await until(tmux.panes)
    await asyncio.sleep(1.0)  # shell de login pronto (com a suíte toda rodando, demora)
    assert await tmux.send_command(pane.painel, 'echo "[$JARVIS_SEGREDO_TESTE]" > saida.txt')
    out = tmp_path / "saida.txt"
    await until(lambda: out.exists() and out.read_text().strip(), 10)
    assert out.read_text().strip() == "[]"
    await tmux.kill(sessao)


async def test_comando_apaga_a_linha_pela_metade(tmux, tmp_path):
    (tmp_path / "build").mkdir()
    sessao = await tmux.new_session(tmp_path)
    (pane,) = await until(tmux.panes)
    await asyncio.sleep(1.0)  # shell pronto
    await tmux.run("send-keys", "-t", pane.painel, "-l", "rm -rf build ")  # sem Enter
    assert await tmux.send_command(pane.painel, "echo ok > feito.txt")
    await until(lambda: (tmp_path / "feito.txt").exists())
    assert (tmp_path / "build").is_dir()  # o rm pela metade não rodou
    assert not await tmux.send_command(pane.painel, "echo a\nrm -rf ~")  # várias linhas
    await tmux.kill(sessao)


async def test_mensagem_vai_colada_com_enter(tmux, tmp_path):
    sessao = await tmux.new_session(tmp_path)
    (pane,) = await until(tmux.panes)
    await tmux.send_command(pane.painel, "cat > msg.txt")
    await until(lambda: tmux_cmd_is(tmux, "cat"))
    assert await tmux.send_message(pane.painel, "roda os testes")
    await until(lambda: (tmp_path / "msg.txt").exists() and (tmp_path / "msg.txt").read_text())
    assert (tmp_path / "msg.txt").read_text() == "roda os testes\n"
    await tmux.kill(sessao)


async def tmux_cmd_is(tmux: Tmux, cmd: str) -> bool:
    panes = await tmux.panes()
    return bool(panes) and panes[0].comando == cmd


async def test_sem_tmux_lista_vazia():
    t = Tmux(binary="", socket="x")
    assert not t.available and await t.panes() == []
    assert await t.new_session(Path("/tmp")) is None


def test_parse_ignora_linhas_ruins_e_paineis_extras():
    sep = "\x1f"
    good = sep.join(["$1", "%1", "10", "/tmp", "zsh", "1", "5", "terminal", "1"])
    extra = sep.join(["$1", "%2", "11", "/tmp", "vim", "1", "5", "terminal", "1"])
    panes = parse_panes("\n".join([good, extra, "lixo", sep.join(["$2"] * 3)]))
    assert (
        len(panes) == 1
        and panes[0].painel == "%1"
        and panes[0].aba
        and panes[0].origem == "terminal"
    )
