#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

NODE_FLAGS=""
if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>23||(a===23&&b>=6)?0:1)'; then
  NODE_FLAGS="--experimental-strip-types --no-warnings"
fi

PORT="${PORT:-8322}"
BASE="http://127.0.0.1:$PORT"
mkdir -p out
PORT="$PORT" node $NODE_FLAGS server.ts >out/server.log 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 100); do
  curl -fsS "$BASE/health" >/dev/null 2>&1 && break
  sleep 0.1
done
curl -fsS "$BASE/health" >/dev/null

say() { printf '\n$ %s\n' "$*"; }
J='content-type: application/json'

say "POST /shorten (generated code)"
curl -fsS -X POST "$BASE/shorten" -H "$J" -d '{"url":"https://nodejs.org/api/http.html"}'
say "POST /shorten (alias docs)"
curl -fsS -X POST "$BASE/shorten" -H "$J" -d '{"url":"https://developer.mozilla.org/en-US/docs/Web/HTTP","alias":"docs","ttlSeconds":86400}'
say "GET /r/docs"
curl -sS -o /dev/null -w '%{http_code} -> %{redirect_url}\n' "$BASE/r/docs"
curl -sS -o /dev/null -w '%{http_code} -> %{redirect_url}\n' "$BASE/r/docs"
say "GET /stats/docs"
curl -fsS "$BASE/stats/docs"
say "POST /shorten (alias tmp)"
curl -fsS -X POST "$BASE/shorten" -H "$J" -d '{"url":"https://example.org/","alias":"tmp"}'
say "POST /admin/delete without credentials"
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/admin/delete" -H "$J" -d '{"code":"tmp"}'
say "GET /health"
curl -fsS "$BASE/health"
echo
echo "run.sh: happy path OK"
