#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONDONTWRITEBYTECODE=1
DATA_DIR=$(mktemp -d)
PORT=${PORT:-8313}
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

echo "== POST /upload =="
doc_id=$(curl -s -X POST "$BASE/upload" -H 'X-Api-Key: alice-key' -H 'Content-Type: application/json' \
    -d '{"title": "quarterly notes", "body": "'"$(echo -n 'meeting notes for Q3' | base64)"'", "meta": {"format": "text"}}' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "uploaded doc id=$doc_id"

echo "== GET /doc (owner key) =="
curl -s -H 'X-Api-Key: alice-key' "$BASE/doc?id=$doc_id"
echo

echo "== POST /share =="
share=$(curl -s -X POST "$BASE/share" -H 'X-Api-Key: alice-key' -H 'Content-Type: application/json' \
    -d "{\"id\": \"$doc_id\", \"ttl_seconds\": 3600}")
echo "$share"
token=$(echo "$share" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

echo "== GET /doc (share token) =="
curl -s "$BASE/doc?id=$doc_id&token=$token"
echo

echo "== GET /docs.html =="
curl -s "$BASE/docs.html"
echo

echo "== GET /quota =="
curl -s -H 'X-Api-Key: alice-key' "$BASE/quota"
echo

echo "== GET /go?next=/docs.html =="
curl -s -o /dev/null -w 'redirect -> %{redirect_url}\n' "$BASE/go?next=/docs.html"
echo "run.sh: done"
