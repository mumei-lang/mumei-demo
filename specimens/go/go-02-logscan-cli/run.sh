#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -c 'from pathlib import Path; Path("bin").mkdir(exist_ok=True); Path("tmp").mkdir(exist_ok=True)'
go build -o bin/logscan .
./bin/logscan -input testdata/access.log -top 3 -since 2026-01-01 \
  -out tmp/summary.txt -workers 4
