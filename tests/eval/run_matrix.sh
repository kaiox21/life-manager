#!/usr/bin/env bash
# Roda a prova para vários modelos em paralelo, cada um num banco de teste próprio.
# Uso: tests/eval/run_matrix.sh "openai/gpt-5-nano google/gemini-2.5-flash-lite" [escalada]
# Precisa do postgres-test no ar (docker compose --profile test up -d postgres-test).
set -euo pipefail
MODELS=(${1:?lista de modelos entre aspas})
ESCALATION=${2:-deepseek/deepseek-v4-pro}
OUT=data/eval/matrix-$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT"
i=0
for model in "${MODELS[@]}"; do
  i=$((i + 1))
  db="eval${i}_test"
  docker compose --profile test exec -T postgres-test \
    sh -c "dropdb -U test --if-exists $db && createdb -U test $db"
  TEST_DATABASE_URL="postgresql+psycopg://test:test@localhost:5433/$db" \
  MODEL_PRIMARY="$model" MODEL_CLASSIFIER="$model" MODEL_ESCALATION="$ESCALATION" \
    uv run pytest -m eval -q -s -p no:cacheprovider > "$OUT/${model//\//_}.log" 2>&1 &
done
wait
for f in "$OUT"/*.log; do sed -n '/^PROVA/,/^falhas/p' "$f"; echo; done
