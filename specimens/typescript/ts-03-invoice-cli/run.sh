#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

NODE_FLAGS=""
if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>23||(a===23&&b>=6)?0:1)'; then
  NODE_FLAGS="--experimental-strip-types --no-warnings"
fi
invoice() { node $NODE_FLAGS invoice.ts "$@"; }

mkdir -p out

printf '\n$ invoice.ts --items items.json --tax 10 --discount 5 --customer Globex --date 2026-10-01\n'
invoice --items items.json --tax 10 --discount 5 --customer Globex --date 2026-10-01

printf '\n$ invoice.ts --items items.json --tax 8 --out out/invoice.txt\n'
invoice --items items.json --tax 8 --customer Initech --date 2026-10-02 --out out/invoice.txt
cat out/invoice.txt

printf '\n$ invoice.ts --items items.json --tax 10 --json\n'
invoice --items items.json --tax 10 --customer Globex --date 2026-10-01 --json | head -n 5

echo
echo "run.sh: happy path OK"
