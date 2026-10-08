#!/usr/bin/env bash
# Backup cifrado dos dois bancos (app e Evolution). Roda no VPS (cron 03:00) ou no Mac.
#
#   deploy/backup.sh                 # usa BACKUP_DEST do .env (remoto rclone, ex.: r2:life-manager)
#   deploy/backup.sh /caminho/local  # grava numa pasta local (migração Mac -> VPS, testes)
#
# Precisa de: docker compose, age, rclone (só para destino remoto).
# A chave PÚBLICA fica em deploy/backup.pub (no repositório); a PRIVADA só no Mac do Kaio.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

DEST=${1:-${BACKUP_DEST:?defina BACKUP_DEST no .env ou passe uma pasta}}
PUBKEY=${BACKUP_PUBKEY_FILE:-deploy/backup.pub}
KEEP_DAYS=${BACKUP_KEEP_DAYS:-30}
COMPOSE="docker compose ${COMPOSE_FILES:-}"
STAMP=$(date +%Y%m%d-%H%M%S)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

alert() {  # avisa pelo ntfy se configurado; sem canal, só falha
  [ -n "${ALERT_NTFY_URL:-}" ] && curl -fsS -m 10 -H "Title: Backup falhou" -d "$1" \
    ${ALERT_NTFY_TOKEN:+-H "Authorization: Bearer $ALERT_NTFY_TOKEN"} "$ALERT_NTFY_URL" >/dev/null || true
}
trap 'alert "backup.sh falhou na linha $LINENO ($(hostname))"; rm -rf "$TMP"' ERR

for db in "$POSTGRES_DB" evolution; do
  file="$TMP/${STAMP}-${db}.dump.age"
  $COMPOSE exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$db" -Fc --no-owner \
    | age -R "$PUBKEY" -o "$file"
  [ -s "$file" ] || { echo "dump vazio: $db" >&2; exit 1; }
done

if [[ "$DEST" == */* && ! "$DEST" =~ ^[A-Za-z0-9_-]+: ]]; then
  mkdir -p "$DEST"
  cp "$TMP"/*.age "$DEST"/
  find "$DEST" -name '*.dump.age' -mtime +"$KEEP_DAYS" -delete
else
  rclone copy "$TMP" "$DEST"
  rclone delete "$DEST" --min-age "${KEEP_DAYS}d" --include '*.dump.age'
fi
ls -la "$TMP"/*.age | awk '{print $5, $NF}'
echo "backup ok -> $DEST"
[ -n "${HEALTHCHECK_BACKUP_URL:-}" ] && curl -fsS -m 10 "$HEALTHCHECK_BACKUP_URL" >/dev/null || true
