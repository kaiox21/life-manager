"""Hook do Claude Code para o Jarvis: anota o evento num arquivo local e sai.

Roda com o /usr/bin/python3 do macOS (3.9, só biblioteca padrão) a cada evento configurado
pelo `install.py`. Regras (openspec/specs/jarvis-terminais):
- guarda só evento, processo, sessão, pasta e um resumo curto do pedido de permissão;
  nunca o texto das mensagens, conteúdo de arquivos ou saída de comandos;
- nunca imprime nada e nunca sai com erro: a saída de um hook assíncrono entra na conversa
  e um código 2 pode bloquear a ação (o comando instalado ainda termina com `|| true`).
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

EVENTS = Path(
    os.environ.get("JARVIS_EVENTS_FILE")
    or Path.home() / "Library/Application Support/Jarvis/claude-events.jsonl"
)
MAX_SUMMARY = 120
FILE_TOOLS = {"Edit", "Write", "Read", "MultiEdit", "NotebookEdit"}


def short(text):
    text = " ".join(str(text).split())
    return text if len(text) <= MAX_SUMMARY else text[: MAX_SUMMARY - 1] + "…"


def summary(tool, tool_input):
    """Resumo do pedido: comando, arquivo, URL ou nome da ferramenta (sem conteúdo)."""
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool == "Bash":
        return short(tool_input.get("command", ""))
    if tool in FILE_TOOLS:
        return short(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    if tool == "WebFetch":
        return short(tool_input.get("url", ""))
    if tool in ("Glob", "Grep"):
        return short(tool_input.get("pattern", ""))
    return short(tool or "")


def claude_pid(start=None):
    """Sobe pelos processos pais até o `claude` (o hook é filho dele: sh → zsh → claude)."""
    pid = start or os.getppid()
    for _ in range(8):
        if pid <= 1:
            return None
        out = subprocess.run(
            ["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True
        ).stdout.strip()
        if not out:
            return None
        ppid, _, comm = out.partition(" ")
        if os.path.basename(comm.strip()) == "claude":
            return pid
        pid = int(ppid)
    return None


def record(data, pid, now):
    event = data.get("hook_event_name", "")
    item = {
        "t": round(now, 3),
        "evento": event,
        "pid": pid,
        "sessao": data.get("session_id", ""),
        "pasta": data.get("cwd", ""),
    }
    tmux = os.environ.get("TMUX", "")
    if tmux and os.environ.get("TMUX_PANE"):  # terminal dentro do tmux: qual painel, qual socket
        item["painel"] = os.environ["TMUX_PANE"]
        item["socket"] = os.path.basename(tmux.split(",")[0])
    if event == "Notification":
        item["tipo"] = data.get("notification_type", "")
    if event == "SessionStart" and data.get("session_title"):
        item["nome"] = short(data["session_title"])
    if event == "PermissionRequest":
        tool = data.get("tool_name", "")
        item["ferramenta"] = tool
        item["resumo"] = summary(tool, data.get("tool_input"))
    return item


def append(item):
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(item, ensure_ascii=False) + "\n").encode()
    fd = os.open(str(EVENTS), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line)  # uma escrita só: linhas curtas não se misturam entre hooks
    finally:
        os.close(fd)


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if isinstance(data, dict) and data.get("hook_event_name"):
            append(record(data, claude_pid(), time.time()))
    except Exception:  # noqa: BLE001 — nunca atrapalhar o Claude Code
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
