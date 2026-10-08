#!/usr/bin/env bash
# Deploy a partir do Mac: atualiza o código no VPS e sobe tudo.
#   deploy/deploy.sh usuario@ip-do-vps
set -euo pipefail
HOST=${1:?usuario@ip-do-vps}
ssh "$HOST" 'cd ~/life-manager && git pull --ff-only \
  && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build \
  && docker compose ps'
