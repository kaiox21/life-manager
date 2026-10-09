import json
import subprocess

from jarvis.hooks import install as inst

OUTRO = {"type": "command", "command": "afplay /System/Library/Sounds/Glass.aiff"}


def _settings(tmp_path, data=None):
    path = tmp_path / ".claude/settings.json"
    path.parent.mkdir(parents=True)
    if data is not None:
        path.write_text(json.dumps(data))
    return path


def test_instala_preservando_o_resto_e_com_backup(tmp_path):
    original = {"model": "opus", "hooks": {"Stop": [{"hooks": [OUTRO]}]}}
    path = _settings(tmp_path, original)
    script = inst.install(path, tmp_path / "hooks")
    data = json.loads(path.read_text())
    assert data["model"] == "opus"
    assert data["hooks"]["Stop"][0] == {"hooks": [OUTRO]}  # o hook do Kaio continua
    assert set(data["hooks"]) == set(inst.EVENTS)
    ours = data["hooks"]["PermissionRequest"][0]["hooks"][0]
    assert ours["async"] is True and str(script) in ours["command"]
    assert data["hooks"]["Notification"][0]["matcher"] == "idle_prompt"
    assert json.loads(path.with_name("settings.json.bak-jarvis").read_text()) == original
    assert script.read_text() == (inst.Path(inst.__file__).with_name("claude_event.py")).read_text()


def test_instalar_de_novo_nao_duplica(tmp_path):
    path = _settings(tmp_path, {})
    inst.install(path, tmp_path / "hooks")
    inst.install(path, tmp_path / "hooks")
    data = json.loads(path.read_text())
    assert all(len(groups) == 1 for groups in data["hooks"].values())


def test_remover_deixa_o_arquivo_como_estava(tmp_path):
    original = {"model": "opus", "hooks": {"Stop": [{"hooks": [OUTRO]}]}}
    path = _settings(tmp_path, original)
    inst.install(path, tmp_path / "hooks")
    inst.uninstall(path)
    assert json.loads(path.read_text()) == original
    path.write_text(json.dumps({"theme": "dark"}))
    inst.install(path, tmp_path / "hooks")
    inst.uninstall(path)
    assert json.loads(path.read_text()) == {"theme": "dark"}  # sem "hooks" vazio sobrando


def test_sem_settings_cria(tmp_path):
    path = tmp_path / ".claude/settings.json"
    inst.install(path, tmp_path / "hooks")
    assert set(json.loads(path.read_text())["hooks"]) == set(inst.EVENTS)


def test_comando_instalado_sai_zero_mesmo_sem_o_script(tmp_path):
    cmd = inst.command(tmp_path / "apagado/claude_event.py")
    proc = subprocess.run(["/bin/sh", "-c", cmd], input="{}", capture_output=True, text=True)
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")
