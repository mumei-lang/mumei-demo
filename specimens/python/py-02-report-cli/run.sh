#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONDONTWRITEBYTECODE=1
OUT_DIR=$(mktemp -d)
trap 'rm -rf "$OUT_DIR"' EXIT

echo "== python3 report.py --input timesheets.csv --rate 120 =="
python3 report.py --input timesheets.csv --rate 120 --out "$OUT_DIR/report.txt"

echo
echo "== report written to $OUT_DIR/report.txt =="
run_sh_marker=1
