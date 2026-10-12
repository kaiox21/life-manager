"""Barra de status do Claude Code com os limites de uso, e cópia deles para o painel do Jarvis.

O Claude Code passa um JSON no stdin a cada atualização (code.claude.com/docs/en/statusline):
`rate_limits.five_hour` / `rate_limits.seven_day` (`used_percentage`, `resets_at`; só nos planos
Pro e Max, depois da 1ª resposta) e `context_window.used_percentage` da sessão. Este script
imprime uma linha curta ("5h 23% · semana 41% · contexto 8%") e grava os números em
~/Library/Application Support/Jarvis/claude_limits.json para o painel.

Roda com o /usr/bin/python3 do macOS (3.9): só biblioteca padrão. Nunca falha para fora.
"""

import json
import os
import sys
import tempfile
import time

OUT = os.path.expanduser("~/Library/Application Support/Jarvis/claude_limits.json")
MAX_SESSIONS = 20


def _window(data, name):
    w = (data.get("rate_limits") or {}).get(name)
    if not isinstance(w, dict) or w.get("used_percentage") is None:
        return None
    return {"pct": float(w["used_percentage"]), "resets_at": w.get("resets_at")}


def merge(previous, data, now):
    """Estado novo: janelas que vieram (as ausentes ficam como estavam) e o contexto da sessão."""
    state = dict(previous or {})
    for name, key in (("five_hour", "cinco_horas"), ("seven_day", "semana")):
        w = _window(data, name)
        if w is not None:
            state[key] = w
    sessions = dict(state.get("sessoes") or {})
    sid = data.get("session_id")
    ctx = (data.get("context_window") or {}).get("used_percentage")
    if sid and ctx is not None:
        sessions[sid] = {
            "contexto": float(ctx),
            "pasta": os.path.basename((data.get("workspace") or {}).get("current_dir") or ""),
            "em": now,
        }
        newest = sorted(sessions.items(), key=lambda kv: kv[1]["em"], reverse=True)
        sessions = dict(newest[:MAX_SESSIONS])
    state["sessoes"] = sessions
    state["atualizado"] = now
    return state


def line(data):
    parts = []
    for name, label in (("five_hour", "5h"), ("seven_day", "semana")):
        w = _window(data, name)
        if w is not None:
            parts.append(f"{label} {round(w['pct'])}%")
    ctx = (data.get("context_window") or {}).get("used_percentage")
    if ctx is not None:
        parts.append(f"contexto {round(float(ctx))}%")
    model = (data.get("model") or {}).get("display_name")
    if model:
        parts.insert(0, model)
    return " · ".join(parts)


def save(path, state):
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".claude_limits.")
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def main(stdin=sys.stdin, path=OUT, now=None):
    try:
        data = json.load(stdin)
    except ValueError:
        return
    try:
        with open(path) as f:
            previous = json.load(f)
    except (OSError, ValueError):
        previous = {}
    try:
        save(path, merge(previous, data, now if now is not None else time.time()))
    except OSError:
        pass
    print(line(data))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # a barra nunca pode quebrar o Claude Code
        pass
