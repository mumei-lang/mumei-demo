#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

cargo build --release 2>/dev/null
BIN=target/release/matrix-tool
WORK=$(mktemp -d)
trap 'rm -rf "$WORK" /tmp/matrix_tool_cache.txt' EXIT

printf '1 2 3\n4 5 6\n' > "$WORK/m23.txt"
printf '4 3\n2 1\n' > "$WORK/m2.txt"

echo "== mean =="
$BIN --input "$WORK/m23.txt" --op mean
echo "== scale by 3 =="
$BIN --input "$WORK/m23.txt" --op scale --factor 3
echo "== transpose =="
$BIN --input "$WORK/m23.txt" --op transpose
echo "== invert =="
$BIN --input "$WORK/m2.txt" --op invert
echo "== checksum =="
$BIN --input "$WORK/m23.txt" --op checksum
echo "== report =="
$BIN --input "$WORK/m23.txt" --op report --label daily --out "$WORK/summary.txt"
cat "$WORK/summary.txt"
