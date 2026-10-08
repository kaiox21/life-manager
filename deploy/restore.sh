#!/usr/bin/env bash
# Restaura um backup cifrado num banco. A chave privada fica no Mac.
#
#   deploy/restore.sh ARQUIVO.dump.age BANCO [CHAVE_PRIVADA]
#
# Recria BANCO do zero e restaura. A chave privada nunca fica no VPS: para restaurar lá,
# decifre no Mac (age -d -i ~/.config/life-manager/backup.key ARQ > ARQ.dump), copie o .dump
# para o VPS e rode este script com o .dump.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

FILE=${1:?arquivo .dump.age ou .dump}
DB=${2:?banco de destino}
KEY=${3:-$HOME/.config/life-manager/backup.key}
COMPOSE="docker compose ${COMPOSE_FILES:-}"

if [[ "$FILE" == *.age ]]; then
  DECRYPT=(age -d -i "$KEY" "$FILE")
else
  DECRYPT=(cat "$FILE")
fi

$COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"$DB\" WITH (FORCE)" -c "CREATE DATABASE \"$DB\""
"${DECRYPT[@]}" | $COMPOSE exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$DB" \
  --no-owner --exit-on-error
echo "restaurado em $DB"
