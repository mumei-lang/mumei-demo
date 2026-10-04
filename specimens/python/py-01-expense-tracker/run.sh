#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONDONTWRITEBYTECODE=1
DATA_DIR=$(mktemp -d)
PORT=${PORT:-8311}
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
    if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        break
    fi
    sleep 0.2
done

echo "== POST /expenses (alice, bob) =="
curl -s -X POST "http://127.0.0.1:$PORT/expenses" \
    -H 'X-User: alice' -H 'Content-Type: application/json' \
    -d '{"amount_cents": 1250, "category": "food:groceries", "day": "2026-09-14", "note": "weekly shop"}'
echo
curl -s -X POST "http://127.0.0.1:$PORT/expenses" \
    -H 'X-User: alice' -H 'Content-Type: application/json' \
    -d '{"amount_cents": 480, "category": "food:coffee", "day": "2026-09-15", "note": "flat white"}'
echo
curl -s -X POST "http://127.0.0.1:$PORT/expenses" \
    -H 'X-User: bob' -H 'Content-Type: application/json' \
    -d '{"amount_cents": 3200, "category": "travel:rail", "day": "2026-09-14", "note": "commuter pass"}'
echo

echo "== GET /expenses?user=alice =="
curl -s "http://127.0.0.1:$PORT/expenses?user=alice"
echo

echo "== GET /summary?user=alice&month=2026-09 =="
curl -s "http://127.0.0.1:$PORT/summary?user=alice&month=2026-09"
echo

echo "== POST /budget =="
curl -s -X POST "http://127.0.0.1:$PORT/budget" \
    -H 'Content-Type: application/json' \
    -d '{"user": "alice", "month": "2026-09", "limit_cents": 5000}'
echo

echo "== POST /reports + GET /export =="
curl -s -X POST "http://127.0.0.1:$PORT/reports?user=alice&month=2026-09"
echo
curl -s "http://127.0.0.1:$PORT/export?path=report-alice-2026-09.csv"

echo "== GET /health =="
curl -s "http://127.0.0.1:$PORT/health"
echo
echo "run.sh: done"
