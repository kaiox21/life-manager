#!/usr/bin/env bash
# Instala o Jarvis para abrir com o login do macOS.
#   jarvis/install_mac.sh            # instala/atualiza (depois de: cd jarvis-ui && npm run tauri build -- --bundles app)
#   jarvis/install_mac.sh --remove   # desinstala
# Cérebro: LaunchAgent com KeepAlive (reinicia se cair). App: LaunchAgent que abre o Jarvis.app no login.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs/Jarvis"
APP_SRC="$ROOT/jarvis-ui/src-tauri/target/release/bundle/macos/Jarvis.app"
APP_DST="$HOME/Applications/Jarvis.app"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
BRAIN=com.kaio.jarvis.brain
UI=com.kaio.jarvis.ui

unload() {
  launchctl bootout "gui/$(id -u)/$1" 2>/dev/null || true
  # o bootout é assíncrono: espera o serviço sumir antes de carregar de novo
  for _ in $(seq 1 50); do launchctl print "gui/$(id -u)/$1" >/dev/null 2>&1 || return 0; sleep 0.2; done
}
load() {
  for _ in 1 2 3 4 5; do launchctl bootstrap "gui/$(id -u)" "$1" 2>/dev/null && return 0; sleep 1; done
  echo "não consegui carregar $1" >&2; return 1
}

if [[ "${1:-}" == "--remove" ]]; then
  unload "$BRAIN"; unload "$UI"
  rm -f "$AGENTS/$BRAIN.plist" "$AGENTS/$UI.plist"
  rm -rf "$APP_DST"
  echo "Jarvis removido do login."
  exit 0
fi

[ -d "$APP_SRC" ] || { echo "Falta o app: rode 'npm run tauri build -- --bundles app' em jarvis-ui/"; exit 1; }
mkdir -p "$AGENTS" "$LOGS" "$HOME/Applications"
pkill -x jarvis-ui 2>/dev/null || true   # encerra o app antigo antes de trocar o bundle
sleep 1
rm -rf "$APP_DST" && cp -R "$APP_SRC" "$APP_DST"

cat > "$AGENTS/$BRAIN.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$BRAIN</string>
  <key>ProgramArguments</key><array>
    <string>$UV</string><string>run</string><string>--project</string><string>$ROOT</string>
    <string>python</string><string>-m</string><string>jarvis</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$LOGS/brain.log</string>
  <key>StandardErrorPath</key><string>$LOGS/brain.log</string>
</dict></plist>
PLIST

cat > "$AGENTS/$UI.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$UI</string>
  <key>ProgramArguments</key><array><string>/usr/bin/open</string><string>-a</string><string>$APP_DST</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
PLIST

for label in "$BRAIN" "$UI"; do
  unload "$label"
  load "$AGENTS/$label.plist"
done
echo "Jarvis instalado: cérebro ($LOGS/brain.log) e app abrem com o login. Atalhos: ⌥Espaço (texto), segure ⌘⇧Espaço (voz), ⌥⇧Espaço (painel)."
