import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "jarvis/hooks/claude_permission.py"
REQUEST = {
    "hook_event_name": "PermissionRequest",
    "session_id": "s1",
    "cwd": "/x",
    "tool_name": "Write",
    "tool_input": {"file_path": "/x/a.txt", "content": "y" * 10_000},
}
TMUX = {"TMUX": "/private/tmp/tmux-501/jarvis,1,0", "TMUX_PANE": "%3"}


def run(env, session_file, data=REQUEST):
    return subprocess.run(
        ["/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable, str(SCRIPT)],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=20,
        env={"PATH": "/usr/bin:/bin", "JARVIS_SESSION_FILE": str(session_file), **env},
    )


def serve(answer):
    got = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            got.append((self.headers.get("Authorization"), body))
            out = json.dumps(answer).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, got


def session(tmp_path, port):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"port": 1, "token": "tk", "hook_port": port}))
    return path


def test_fora_do_tmux_do_jarvis_sai_calado(tmp_path):
    server, got = serve({})
    for env in ({}, {"TMUX": "/private/tmp/tmux-501/default,1,0", "TMUX_PANE": "%1"}):
        proc = run(env, session(tmp_path, server.server_address[1]))
        assert proc.returncode == 0 and proc.stdout == "" and proc.stderr == ""
    assert got == []  # nem chega a falar com o cérebro
    server.shutdown()


def test_cerebro_fora_sai_calado(tmp_path):
    proc = run(TMUX, session(tmp_path, 9))  # porta fechada
    assert proc.returncode == 0 and proc.stdout == ""
    proc = run(TMUX, tmp_path / "nao-existe.json")
    assert proc.returncode == 0 and proc.stdout == ""


def test_permitir_vem_do_cerebro_com_painel_e_token(tmp_path):
    allow = {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow"},
        }
    }
    server, got = serve(allow)
    proc = run(TMUX, session(tmp_path, server.server_address[1]))
    assert proc.returncode == 0 and json.loads(proc.stdout) == allow
    auth, body = got[0]
    assert auth == "Bearer tk" and body["jarvis_painel"] == "%3" and body["tool_name"] == "Write"
    assert len(body["tool_input"]["content"]) < 2100  # conteúdo grande cortado
    server.shutdown()


def test_negar_e_resposta_vazia(tmp_path):
    deny = {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny", "message": "O Kaio negou pelo Jarvis."},
        }
    }
    server, _ = serve(deny)
    assert json.loads(run(TMUX, session(tmp_path, server.server_address[1])).stdout) == deny
    server.shutdown()
    server, _ = serve({})
    assert run(TMUX, session(tmp_path, server.server_address[1])).stdout == ""
    server.shutdown()


def test_outro_evento_e_ignorado(tmp_path):
    server, got = serve({})
    run(TMUX, session(tmp_path, server.server_address[1]), {"hook_event_name": "Stop"})
    assert got == []
    server.shutdown()
