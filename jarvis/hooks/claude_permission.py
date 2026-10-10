"""Hook `PermissionRequest` síncrono do Jarvis: Permitir/Negar pelos botões do aviso.

Roda com o /usr/bin/python3 do macOS (3.9, só biblioteca padrão) em TODAS as sessões do Claude
Code, mas só age dentro dos terminais compartilhados (tmux com o socket `jarvis`); fora deles
sai na hora, calado. Dentro, manda o pedido ao cérebro (porta e token no session.json, 600) e
espera a decisão do Kaio. O diálogo do terminal aparece em paralelo e vale a primeira resposta.
Cérebro fora, erro ou resposta vazia: sai sem imprimir nada e o diálogo decide. Nunca sai com
erro (o comando instalado ainda termina com `|| true`).
openspec/changes/jarvis-terminais-controle, design, decisão 7.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

SOCKET = os.environ.get("JARVIS_TMUX_SOCKET") or "jarvis"  # outro socket só nos testes
SESSION = Path(
    os.environ.get("JARVIS_SESSION_FILE")
    or Path.home() / "Library/Application Support/Jarvis/session.json"
)
WAIT = 595  # o hook está instalado com 600 s
MAX_FIELD = 2000  # conteúdo de arquivo não precisa ir ao cérebro (só o resumo aparece)


def in_jarvis_tmux(env):
    tmux = env.get("TMUX", "")
    return bool(tmux and env.get("TMUX_PANE")) and os.path.basename(tmux.split(",")[0]) == SOCKET


def trimmed(value):
    if isinstance(value, dict):
        return {k: trimmed(v) for k, v in value.items()}
    if isinstance(value, str) and len(value) > MAX_FIELD:
        return value[:MAX_FIELD] + "…"
    return value


def ask_brain(data, pane):
    session = json.loads(SESSION.read_text())
    port, token = int(session["hook_port"]), str(session["token"])
    payload = {
        "hook_event_name": "PermissionRequest",
        "tool_name": data.get("tool_name", ""),
        "tool_input": trimmed(data.get("tool_input") or {}),
        "session_id": data.get("session_id", ""),
        "cwd": data.get("cwd", ""),
        "jarvis_painel": pane,
    }
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/permissao",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # nada de proxy
    with opener.open(request, timeout=WAIT) as response:
        return json.loads(response.read() or b"{}")


def main():
    try:
        if not in_jarvis_tmux(os.environ):
            return 0
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict) or data.get("hook_event_name") != "PermissionRequest":
            return 0
        out = ask_brain(data, os.environ["TMUX_PANE"])
        decision = (
            (out.get("hookSpecificOutput") or {}).get("decision") if isinstance(out, dict) else None
        )
        if isinstance(decision, dict) and decision.get("behavior") in ("allow", "deny"):
            sys.stdout.write(json.dumps(out))
    except Exception:  # noqa: BLE001 — nunca atrapalhar o Claude Code
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
