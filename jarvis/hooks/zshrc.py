"""Instala (ou remove) no ~/.zshrc o bloco que põe as janelas novas do Terminal.app no tmux do
Jarvis (terminais compartilhados com o painel).

    python3 jarvis/hooks/zshrc.py            instala ou atualiza
    python3 jarvis/hooks/zshrc.py --remover  tira só o bloco do Jarvis

Backup em ~/.zshrc.bak-jarvis; só mexe entre os marcadores. O bloco não usa `exec`: o tmux roda
e, se terminar bem, a janela fecha junto (`&& exit`); se o tmux falhar, a janela fica num shell
normal, nunca fechada. openspec/changes/jarvis-terminais-controle, design, decisão 3.
"""

import shutil
import sys
from pathlib import Path

ZSHRC = Path.home() / ".zshrc"
START = "# >>> jarvis tmux >>>"
END = "# <<< jarvis tmux <<<"
BLOCK = r"""# >>> jarvis tmux >>>
# Janelas novas do Terminal.app entram no tmux do Jarvis (terminais compartilhados com o painel).
# Desligar numa janela: JARVIS_SEM_TMUX=1. De vez: bash jarvis/install_mac.sh --sem-tmux
if [[ -o interactive && -z "$TMUX" && -z "$JARVIS_SEM_TMUX" && "$TERM_PROGRAM" == "Apple_Terminal" ]]; then
  _jarvis_tmux="${JARVIS_TMUX_BIN:-/opt/homebrew/bin/tmux}"
  [[ -x "$_jarvis_tmux" ]] || _jarvis_tmux=/usr/local/bin/tmux
  if [[ -x "$_jarvis_tmux" ]] && "$_jarvis_tmux" -V >/dev/null 2>&1; then
    "$_jarvis_tmux" -L jarvis -f "$HOME/Library/Application Support/Jarvis/tmux.conf" \
      new-session -c "$PWD" \; set-option destroy-unattached on \; set-option @jarvis_origem terminal \
      && exit
  fi
  unset _jarvis_tmux
fi
# <<< jarvis tmux <<<
"""


def without_block(text):
    if START not in text:
        return text
    before, _, rest = text.partition(START)
    _, _, after = rest.partition(END)
    return before.rstrip("\n") + ("\n" if before.strip() else "") + after.lstrip("\n")


def install(path=ZSHRC):
    text = path.read_text() if path.exists() else ""
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak-jarvis"))
    body = without_block(text).rstrip("\n")
    path.write_text((body + "\n\n" if body else "") + BLOCK)


def remove(path=ZSHRC):
    if not path.exists() or START not in path.read_text():
        return
    shutil.copy2(path, path.with_name(path.name + ".bak-jarvis"))
    path.write_text(without_block(path.read_text()))


def main(argv):
    if "--remover" in argv:
        remove()
        print("bloco do tmux do Jarvis removido de " + str(ZSHRC))
    else:
        install()
        print("janelas novas do Terminal.app entram no tmux do Jarvis (" + str(ZSHRC) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
