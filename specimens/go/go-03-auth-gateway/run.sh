#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -c 'from pathlib import Path; Path("bin").mkdir(exist_ok=True)'
go build -o bin/auth-gateway .
PORT=8332 ./bin/auth-gateway >server.log 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true' EXIT

ready=0
for ((attempt = 0; attempt < 50; attempt++)); do
  if curl -fsS http://127.0.0.1:8332/healthz >/dev/null; then
    ready=1
    break
  fi
  sleep 0.1
done
if [[ "$ready" -ne 1 ]]; then
  printf 'server did not become ready\n' >&2
  exit 1
fi

login_response="$(curl -fsS -X POST http://127.0.0.1:8332/login \
  -H 'Content-Type: application/json' -d '{"user":"alice","password":"bluebird42"}'
)"
printf '%s\n' "$login_response"
token="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])' <<<"$login_response")"
curl -fsS -H "Authorization: Bearer $token" \
  'http://127.0.0.1:8332/profile?user=alice'
curl -fsS http://127.0.0.1:8332/healthz
