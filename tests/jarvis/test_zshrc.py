import os
import stat
import subprocess
from pathlib import Path

import pytest

from jarvis.hooks import zshrc

ZSH = "/bin/zsh"
pytestmark = pytest.mark.skipif(not Path(ZSH).exists(), reason="sem zsh")


def test_instala_no_fim_com_backup_sem_duplicar(tmp_path):
    rc = tmp_path / ".zshrc"
    rc.write_text("export FOO=1\nalias ll='ls -l'\n")
    zshrc.install(rc)
    zshrc.install(rc)
    text = rc.read_text()
    assert text.startswith("export FOO=1\nalias ll='ls -l'\n")
    assert text.count(zshrc.START) == 1 and text.rstrip().endswith(zshrc.END)
    assert (tmp_path / ".zshrc.bak-jarvis").exists()


def test_remover_deixa_como_estava(tmp_path):
    rc = tmp_path / ".zshrc"
    original = "export FOO=1\n# fim\n"
    rc.write_text(original)
    zshrc.install(rc)
    zshrc.remove(rc)
    assert rc.read_text() == original
    empty = tmp_path / "vazio" / ".zshrc"
    empty.parent.mkdir()
    zshrc.install(empty)
    zshrc.remove(empty)
    assert empty.read_text() == ""


def fake_tmux(tmp_path: Path, exit_code: int) -> Path:
    path = tmp_path / f"tmux-{exit_code}"
    log = tmp_path / "tmux.log"
    path.write_text(
        f'#!/bin/sh\nif [ "$1" = "-V" ]; then echo "tmux 3.8"; exit 0; fi\n'
        f'echo "$@" >> "{log}"\nexit {exit_code}\n'
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def run_zsh(tmp_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    zdot = tmp_path / "zdot"
    zdot.mkdir(exist_ok=True)
    zshrc.install(zdot / ".zshrc")
    with (zdot / ".zshrc").open("a") as f:
        f.write('echo "SHELL-CONTINUOU"\n')
    return subprocess.run(
        [ZSH, "-i", "-c", "true"],
        capture_output=True,
        text=True,
        timeout=20,
        env={"HOME": str(tmp_path), "ZDOTDIR": str(zdot), "PATH": "/usr/bin:/bin", **env},
    )


def test_terminal_app_entra_no_tmux_e_sai_junto(tmp_path):
    tmux = fake_tmux(tmp_path, 0)
    proc = run_zsh(tmp_path, {"TERM_PROGRAM": "Apple_Terminal", "JARVIS_TMUX_BIN": str(tmux)})
    assert "SHELL-CONTINUOU" not in proc.stdout  # o tmux terminou bem: a janela fecha junto
    args = (tmp_path / "tmux.log").read_text()
    assert (
        "-L jarvis" in args
        and "destroy-unattached on" in args
        and "@jarvis_origem terminal" in args
    )


def test_tmux_que_falha_deixa_o_shell_normal(tmp_path):
    tmux = fake_tmux(tmp_path, 1)
    proc = run_zsh(tmp_path, {"TERM_PROGRAM": "Apple_Terminal", "JARVIS_TMUX_BIN": str(tmux)})
    assert "SHELL-CONTINUOU" in proc.stdout


@pytest.mark.parametrize(
    "env",
    [
        {"TERM_PROGRAM": "vscode"},
        {"TERM_PROGRAM": "Apple_Terminal", "JARVIS_SEM_TMUX": "1"},
        {"TERM_PROGRAM": "Apple_Terminal", "TMUX": "/private/tmp/tmux-501/jarvis,1,0"},
    ],
)
def test_nao_entra_no_tmux(tmp_path, env):
    tmux = fake_tmux(tmp_path, 0)
    proc = run_zsh(tmp_path, {**env, "JARVIS_TMUX_BIN": str(tmux)})
    assert "SHELL-CONTINUOU" in proc.stdout
    assert not (tmp_path / "tmux.log").exists()


def test_sem_tmux_instalado_shell_normal(tmp_path):
    proc = run_zsh(tmp_path, {"TERM_PROGRAM": "Apple_Terminal", "JARVIS_TMUX_BIN": "/nao/existe"})
    # sem /opt/homebrew nem /usr/local no PATH de teste ainda pode existir o tmux real: só
    # garante que, sem ele, o shell segue (quando existe, a janela entraria no tmux de verdade)
    if not os.access("/usr/local/bin/tmux", os.X_OK):
        assert "SHELL-CONTINUOU" in proc.stdout
