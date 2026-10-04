#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

NODE_FLAGS=""
if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>23||(a===23&&b>=6)?0:1)'; then
  NODE_FLAGS="--experimental-strip-types --no-warnings"
fi

PORT="${PORT:-8321}"
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

say "POST /tasks (alice)"
curl -fsS -X POST "$BASE/tasks" -H "$J" -H 'X-User: alice' -d '{"title":"Write release notes","priority":2}'
say "POST /tasks (alice)"
curl -fsS -X POST "$BASE/tasks" -H "$J" -H 'X-User: alice' -d '{"title":"Fix login redirect","description":"customer report"}'
say "POST /tasks (bob)"
curl -fsS -X POST "$BASE/tasks" -H "$J" -H 'X-User: bob' -d '{"title":"Plan sprint review","priority":4}'
say "PATCH /tasks/1"
curl -fsS -X PATCH "$BASE/tasks/1" -H "$J" -H 'X-User: alice' -d '{"description":"for v1.4"}'
say "POST /tasks/1/move -> in_progress"
curl -fsS -X POST "$BASE/tasks/1/move" -H "$J" -H 'X-User: alice' -d '{"to":"in_progress"}'
say "POST /tasks/1/move -> review"
curl -fsS -X POST "$BASE/tasks/1/move" -H "$J" -H 'X-User: alice' -d '{"to":"review"}'
say "POST /tasks/1/move -> done"
curl -fsS -X POST "$BASE/tasks/1/move" -H "$J" -H 'X-User: alice' -d '{"to":"done"}'
say "GET /board"
curl -fsS "$BASE/board"
say "GET /search?q=login"
curl -fsS "$BASE/search?q=login"
echo
echo "run.sh: happy path OK"
