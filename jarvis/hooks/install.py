"""Instala (ou remove) os hooks do Jarvis no ~/.claude/settings.json.

    python3 jarvis/hooks/install.py            instala ou atualiza
    python3 jarvis/hooks/install.py --remover  tira só os hooks do Jarvis

Copia o script do hook para um lugar fixo (fora do repositório), faz backup do settings.json
e só mexe nas entradas do Jarvis, reconhecidas pelo caminho do script.
"""

import json
import shutil
import sys
from pathlib import Path

HOME = Path.home()
SETTINGS = HOME / ".claude/settings.json"
HOOK_DIR = HOME / "Library/Application Support/Jarvis/hooks"
SCRIPT_NAME = "claude_event.py"
MARK = "/" + SCRIPT_NAME + '"'  # o comando do Jarvis termina no script entre aspas
PYTHON = "/usr/bin/python3"
# evento -> matcher (None = todos)
EVENTS = {
    "SessionStart": None,
    "UserPromptSubmit": None,
    "PermissionRequest": None,
    "PostToolUse": None,
    "PostToolUseFailure": None,
    "Notification": "idle_prompt",
    "Stop": None,
    "SessionEnd": None,
}


def command(script):
    # Nunca falha para fora: script ausente faria o python sair com 2, que pode bloquear.
    return f'{PYTHON} "{script}" >/dev/null 2>&1 || true'


def is_ours(hook):
    return isinstance(hook, dict) and MARK in str(hook.get("command", ""))


def remove_ours(settings):
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings
    for event in list(hooks):
        groups = []
        for group in hooks[event] or []:
            kept = [h for h in group.get("hooks", []) if not is_ours(h)]
            if kept:
                groups.append({**group, "hooks": kept})
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]
    return settings


def add_ours(settings, script):
    settings = remove_ours(settings)  # rodar de novo não duplica
    hooks = settings.setdefault("hooks", {})
    for event, matcher in EVENTS.items():
        group = {"hooks": [{"type": "command", "command": command(script), "async": True}]}
        if matcher:
            group = {"matcher": matcher, **group}
        hooks.setdefault(event, []).append(group)
    return settings


def load(path):
    if not path.exists():
        return {}
    text = path.read_text()
    return json.loads(text) if text.strip() else {}


def save(path, settings):
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak-jarvis"))
    tmp = path.with_name(path.name + ".tmp-jarvis")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def install(settings_path=SETTINGS, hook_dir=HOOK_DIR, source=None):
    source = source or Path(__file__).with_name(SCRIPT_NAME)
    hook_dir.mkdir(parents=True, exist_ok=True)
    script = hook_dir / SCRIPT_NAME
    shutil.copy2(source, script)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    save(settings_path, add_ours(load(settings_path), script))
    return script


def uninstall(settings_path=SETTINGS):
    if settings_path.exists():
        save(settings_path, remove_ours(load(settings_path)))


def main(argv):
    if not Path(PYTHON).exists():
        print("sem " + PYTHON + ": hooks do Jarvis não instalados")
        return 1
    if "--remover" in argv:
        uninstall()
        print("hooks do Jarvis removidos de " + str(SETTINGS))
    else:
        script = install()
        print("hooks do Jarvis instalados em " + str(SETTINGS) + " (script: " + str(script) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
