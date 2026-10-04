#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.foundry/bin:$PATH"

forge build >/dev/null

mapfile -t cases < <(python3 - <<'PY'
import json
with open("DEFECTS.json") as f:
    data = json.load(f)
for d in data["defects"]:
    print(f'{d["id"]}\t{d["repro"]}')
PY
)

fail=0
for line in "${cases[@]}"; do
    id="${line%%	*}"
    repro="${line##*	}"
    if out="$(forge test --match-test "test_repro_${repro}" -vv 2>&1)"; then
        evidence="$(printf '%s\n' "$out" \
            | sed -n '/Logs:/,/^$/p' \
            | sed -n 's/^  \(.*\)/\1/p' \
            | paste -sd';' - | sed 's/;/; /g')"
        echo "[REPRODUCED] $id $repro: $evidence"
    else
        reason="$(printf '%s\n' "$out" | grep -m1 -E '\[FAIL|Reason:|revert' || true)"
        echo "[NOT REPRODUCED] $id $repro: $reason"
        fail=1
    fi
done
exit "$fail"
