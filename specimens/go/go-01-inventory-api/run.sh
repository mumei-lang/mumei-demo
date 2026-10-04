#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -c 'from pathlib import Path; Path("bin").mkdir(exist_ok=True)'
go build -o bin/inventory-api .
PORT=8331 ./bin/inventory-api >server.log 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true' EXIT

ready=0
for ((attempt = 0; attempt < 50; attempt++)); do
  if curl -fsS http://127.0.0.1:8331/report >/dev/null; then
    ready=1
    break
  fi
  sleep 0.1
done
if [[ "$ready" -ne 1 ]]; then
  printf 'server did not become ready\n' >&2
  exit 1
fi

curl -fsS -X POST http://127.0.0.1:8331/items \
  -H 'Content-Type: application/json' \
  -d '{"sku":"tea-100","name":"Green tea","stock":24,"locations":["A1","B2"],"supplier":{"name":"North Supply"}}'
curl -fsS -X POST http://127.0.0.1:8331/reserve \
  -H 'Content-Type: application/json' -d '{"sku":"tea-100","qty":3}'
curl -fsS 'http://127.0.0.1:8331/items/tea-100'
curl -fsS 'http://127.0.0.1:8331/report?limit=1'
