#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONDONTWRITEBYTECODE=1
DATA_DIR=$(mktemp -d)
PORT=${PORT:-8312}
BASE="http://127.0.0.1:$PORT"
SERVER_PID=""

cleanup() {
    if [[ -n "$SERVER_PID" ]]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    rm -rf "$DATA_DIR"
}
trap cleanup EXIT

DATA_DIR="$DATA_DIR" PORT="$PORT" python3 app.py &
SERVER_PID=$!
for _ in $(seq 1 50); do
    curl -sf "$BASE/health" >/dev/null 2>&1 && break
    sleep 0.2
done

echo "== POST /accounts =="
curl -s -X POST "$BASE/accounts" -H 'X-Owner: alice' -H 'Content-Type: application/json' \
    -d '{"owner": "alice", "label": "checking", "initial_cents": 5000}'
echo
curl -s -X POST "$BASE/accounts" -H 'X-Owner: bob' -H 'Content-Type: application/json' \
    -d '{"owner": "bob", "label": "savings", "initial_cents": 2000}'
echo

echo "== POST /transfer (alice -> bob 300) =="
curl -s -X POST "$BASE/transfer" -H 'X-Owner: alice' -H 'Content-Type: application/json' \
    -d '{"from": 1, "to": 2, "amount_cents": 300}'
echo

echo "== GET /accounts/1 =="
curl -s "$BASE/accounts/1"
echo

echo "== GET /statement/1 =="
curl -s "$BASE/statement/1"
echo

echo "== GET /statement/2.html =="
curl -s "$BASE/statement/2.html"
echo

echo "== POST /close (empty account) =="
curl -s -X POST "$BASE/accounts" -H 'X-Owner: carol' -H 'Content-Type: application/json' \
    -d '{"owner": "carol", "label": "spare", "initial_cents": 0}' >/dev/null
curl -s -X POST "$BASE/close" -H 'X-Owner: carol' -H 'Content-Type: application/json' -d '{"id": 3}'
echo
echo "run.sh: done"
