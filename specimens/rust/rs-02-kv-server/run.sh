#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

cargo build --release 2>/dev/null
BIN="$PWD/target/release/kv-server"
PORT=${PORT:-8341}
WORK=$(mktemp -d)
KV_DATA_DIR="$WORK/data" PORT=$PORT "$BIN" &
SRV=$!
cleanup() { kill "$SRV" 2>/dev/null || true; rm -rf "$WORK"; }
trap cleanup EXIT
for _ in $(seq 50); do
  curl -s -o /dev/null "http://127.0.0.1:$PORT/kv/health" && break
  sleep 0.1
done

echo "PUT /kv/hello <- world"
curl -s -X PUT --data 'world' "http://127.0.0.1:$PORT/kv/hello"
echo "GET /kv/hello"
curl -s "http://127.0.0.1:$PORT/kv/hello"
echo "POST /incr/visits?delta=5"
curl -s -X POST "http://127.0.0.1:$PORT/incr/visits?delta=5"
curl -s -X POST "http://127.0.0.1:$PORT/incr/visits?delta=2"
echo "GET /keys?prefix=he"
curl -s "http://127.0.0.1:$PORT/keys?prefix=he"
echo "POST /snapshot?path=snap.txt"
curl -s -X POST "http://127.0.0.1:$PORT/snapshot?path=snap.txt"
echo "GET /ui?key=hello"
curl -s "http://127.0.0.1:$PORT/ui?key=hello" | head -2
