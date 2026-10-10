import json
import stat
import subprocess
import sys
from pathlib import Path

from jarvis.hooks import claude_event as hook

BASE = {
    "session_id": "s1",
    "transcript_path": "/x/s1.jsonl",
    "cwd": "/Users/kaio/Downloads/life-manager",
    "permission_mode": "default",
}
SCRIPT = Path(hook.__file__)


def test_permissao_de_bash_guarda_so_o_comando():
    data = {
        **BASE,
        "hook_event_name": "PermissionRequest",
        "tool_name": "Bash",
        "tool_input": {"command": "npm   test", "description": "roda os testes"},
        "permission_suggestions": [],
    }
    assert hook.record(data, 7958, 1.0) == {
        "t": 1.0,
        "evento": "PermissionRequest",
        "pid": 7958,
        "sessao": "s1",
        "pasta": "/Users/kaio/Downloads/life-manager",
        "ferramenta": "Bash",
        "resumo": "npm test",
    }


def test_write_guarda_o_caminho_e_nunca_o_conteudo():
    data = {
        **BASE,
        "hook_event_name": "PermissionRequest",
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/a.py", "content": "SEGREDO=123"},
    }
    item = hook.record(data, 1, 1.0)
    assert item["resumo"] == "/tmp/a.py"
    assert "SEGREDO" not in json.dumps(item)


def test_resumo_cortado_em_120():
    data = {
        **BASE,
        "hook_event_name": "PermissionRequest",
        "tool_name": "Bash",
        "tool_input": {"command": "x" * 500},
    }
    assert len(hook.record(data, 1, 1.0)["resumo"]) == 120


def test_mensagem_e_notificacao_sem_texto():
    prompt = {**BASE, "hook_event_name": "UserPromptSubmit", "prompt": "minha senha é 123"}
    note = {
        **BASE,
        "hook_event_name": "Notification",
        "notification_type": "idle_prompt",
        "message": "Claude is waiting for your input",
    }
    stop = {**BASE, "hook_event_name": "Stop", "last_assistant_message": "resposta privada"}
    for data in (prompt, note, stop):
        text = json.dumps(hook.record(data, 1, 1.0))
        assert "senha" not in text and "waiting" not in text and "privada" not in text
    assert hook.record(note, 1, 1.0)["tipo"] == "idle_prompt"


def test_mcp_resume_pelo_nome_da_ferramenta():
    data = {**BASE, "hook_event_name": "PermissionRequest", "tool_name": "mcp__x__apagar"}
    assert hook.record(data, 1, 1.0)["resumo"] == "mcp__x__apagar"


def _run(stdin: str, events: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin,
        capture_output=True,
        text=True,
        env={"JARVIS_EVENTS_FILE": str(events), "PATH": "/usr/bin:/bin"},
    )


def test_script_grava_uma_linha_600_e_fica_calado(tmp_path):
    events = tmp_path / "eventos.jsonl"
    data = {**BASE, "hook_event_name": "Stop", "stop_reason": "end_turn"}
    proc = _run(json.dumps(data), events)
    assert proc.returncode == 0 and proc.stdout == "" and proc.stderr == ""
    (line,) = events.read_text().splitlines()
    assert json.loads(line)["evento"] == "Stop"
    assert stat.S_IMODE(events.stat().st_mode) == 0o600


def test_script_com_lixo_no_stdin_sai_zero_e_calado(tmp_path):
    proc = _run("isto não é json", tmp_path / "e.jsonl")
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")


def test_script_roda_no_python_do_macos(tmp_path):
    """O hook roda com /usr/bin/python3 (3.9): precisa compilar e funcionar nele."""
    py = Path("/usr/bin/python3")
    if not py.exists():
        return
    events = tmp_path / "e.jsonl"
    proc = subprocess.run(
        [str(py), str(SCRIPT)],
        input=json.dumps({**BASE, "hook_event_name": "SessionStart", "source": "startup"}),
        capture_output=True,
        text=True,
        env={"JARVIS_EVENTS_FILE": str(events), "PATH": "/usr/bin:/bin"},
    )
    assert (proc.returncode, proc.stderr) == (0, "")
    assert json.loads(events.read_text())["evento"] == "SessionStart"


def test_dentro_do_tmux_grava_painel_e_socket(tmp_path):
    events = tmp_path / "eventos.jsonl"
    data = {**BASE, "hook_event_name": "SessionStart", "source": "startup"}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        env={
            "JARVIS_EVENTS_FILE": str(events),
            "PATH": "/usr/bin:/bin",
            "TMUX": "/private/tmp/tmux-501/jarvis,88357,1",
            "TMUX_PANE": "%7",
        },
    )
    assert proc.returncode == 0 and proc.stdout == ""
    item = json.loads(events.read_text())
    assert item["painel"] == "%7" and item["socket"] == "jarvis"


def test_fora_do_tmux_sem_painel(tmp_path):
    events = tmp_path / "eventos.jsonl"
    _run(json.dumps({**BASE, "hook_event_name": "Stop"}), events)
    item = json.loads(events.read_text())
    assert "painel" not in item and "socket" not in item
