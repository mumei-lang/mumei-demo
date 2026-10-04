#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONDONTWRITEBYTECODE=1
DATA_DIR=$(mktemp -d)
PORT=${PORT:-8311}
BASE="http://127.0.0.1:$PORT"
SERVER_PID=""
REPRODUCED=0

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

post_expense() {  # user amount category day note
    curl -s -o /dev/null -X POST "$BASE/expenses" \
        -H "X-User: $1" -H 'Content-Type: application/json' \
        -d "{\"amount_cents\": $2, \"category\": \"$3\", \"day\": \"$4\", \"note\": \"$5\"}"
}

# seed data used by several cases
post_expense alice 1250 food:groceries 2026-09-14 aliceshop >/dev/null
post_expense bob 3200 travel:rail 2026-09-14 bobpass >/dev/null

# PY01-D01 sql_injection: ' OR '1'='1 returns every user's rows
status=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/expenses?user=x%27%20OR%20%271%27%3D%271" || true)
resp=$(curl -s "$BASE/expenses?user=x%27%20OR%20%271%27%3D%271" || true)
if [[ "$status" == "200" && "$resp" == *bobpass* && "$resp" == *aliceshop* ]]; then
    echo "[REPRODUCED] PY01-D01 sql_injection: user=x' OR '1'='1 returned both alice and bob rows"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY01-D01 sql_injection: status=$status body=$resp"
fi

# PY01-D02 path_traversal: /export?path=../secret.txt escapes the reports dir
echo "topsecret-marker-4481" > "$DATA_DIR/secret.txt"
resp=$(curl -s "$BASE/export?path=../secret.txt" || true)
if [[ "$resp" == *topsecret-marker-4481* ]]; then
    echo "[REPRODUCED] PY01-D02 path_traversal: /export?path=../secret.txt returned '$resp'"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY01-D02 path_traversal: body=$resp"
fi

# PY01-D03 division_by_zero: summary for a month with no expenses
status=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/summary?user=nobody&month=2099-01" || true)
resp=$(curl -s "$BASE/summary?user=nobody&month=2099-01" || true)
if [[ "$status" == "500" && "$resp" == *ZeroDivisionError* ]]; then
    echo "[REPRODUCED] PY01-D03 division_by_zero: empty-month summary -> HTTP 500 ZeroDivisionError"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY01-D03 division_by_zero: status=$status body=$resp"
fi

# PY01-D04 bankers_rounding: average_expense([1,4]) rounds 2.5 down to 2
got=$(python3 -c 'import ledger; print(ledger.average_expense([1, 4]))')
if [[ "$got" == "2" ]]; then
    echo "[REPRODUCED] PY01-D04 bankers_rounding: average_expense([1,4])=$got (half-up would give 3)"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY01-D04 bankers_rounding: average_expense([1,4])=$got"
fi

# PY01-D05 boundary_excluded: spending exactly the limit reports status ok
post_expense dora 500 food:lunch 2026-09-14 sandwich >/dev/null
resp=$(curl -s -X POST "$BASE/budget" -H 'Content-Type: application/json' \
    -d '{"user": "dora", "month": "2026-09", "limit_cents": 500}' || true)
if [[ "$resp" == *'"spent_cents": 500'* && "$resp" == *'"status": "ok"'* ]]; then
    echo "[REPRODUCED] PY01-D05 boundary_excluded: spent==limit (500) reports status ok, not exceeded"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY01-D05 boundary_excluded: body=$resp"
fi

# PY01-D06 cross_user_read: alice's session reads bob's expenses via ?user=
resp=$(curl -s -H 'X-User: alice' "$BASE/expenses?user=bob" || true)
if [[ "$resp" == *bobpass* ]]; then
    echo "[REPRODUCED] PY01-D06 cross_user_read: X-User alice read bob's expenses: $resp"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY01-D06 cross_user_read: body=$resp"
fi

# PY01-D07 connection_leak: 50 malformed POSTs leave 50 open db connections
db_fds() {
    python3 - "$1" <<'EOF'
import glob, os, sys
n = 0
for fd in glob.glob(f"/proc/{sys.argv[1]}/fd/*"):
    try:
        if "expenses.db" in os.readlink(fd):
            n += 1
    except OSError:
        pass
print(n)
EOF
}
open_count() {
    curl -s "$BASE/health" | python3 -c 'import json,sys; print(json.load(sys.stdin)["open_connections"])'
}
before=$(open_count)
fds_before=$(db_fds "$SERVER_PID")
for _ in $(seq 1 50); do
    curl -s -o /dev/null -X POST "$BASE/expenses" -H 'X-User: lea' \
        -H 'Content-Type: application/json' \
        -d '{"amount_cents": 100, "category": "food:snack", "day": "not-a-day", "note": "x"}' || true
done
after=$(open_count)
fds_after=$(db_fds "$SERVER_PID")
if [[ $((after - before)) -ge 50 && $((fds_after - fds_before)) -ge 50 ]]; then
    echo "[REPRODUCED] PY01-D07 connection_leak: open_connections $before->$after, db fds $fds_before->$fds_after after 50 bad POSTs"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY01-D07 connection_leak: open_connections $before->$after, db fds $fds_before->$fds_after"
fi

# PY01-D08 subcategory_oob: a category without ':' crashes /summary
post_expense fred 900 rent 2026-09-14 flat >/dev/null
status=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/summary?user=fred&month=2026-09" || true)
resp=$(curl -s "$BASE/summary?user=fred&month=2026-09" || true)
if [[ "$status" == "500" && "$resp" == *IndexError* ]]; then
    echo "[REPRODUCED] PY01-D08 subcategory_oob: category 'rent' -> /summary HTTP 500 IndexError"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY01-D08 subcategory_oob: status=$status body=$resp"
fi

# PY01-D09 embedded_admin_token: token read straight out of the config module
token=$(python3 -c 'import config; print(config.ADMIN_TOKEN)')
status=$(curl -s -o /dev/null -w '%{http_code}' -H "X-Admin-Token: $token" "$BASE/admin/stats" || true)
resp=$(curl -s -H "X-Admin-Token: $token" "$BASE/admin/stats" || true)
if [[ "$status" == "200" && "$resp" == *'"users"'* ]]; then
    echo "[REPRODUCED] PY01-D09 embedded_admin_token: config.ADMIN_TOKEN grants /admin/stats -> $resp"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY01-D09 embedded_admin_token: status=$status body=$resp"
fi

# PY01-D10 negative_amount: a -5000 expense drives the month total negative
post_expense erin -5000 food:refund 2026-09-14 chargeback >/dev/null
resp=$(curl -s "$BASE/summary?user=erin&month=2026-09" || true)
if [[ "$resp" == *'"total_cents": -5000'* ]]; then
    echo "[REPRODUCED] PY01-D10 negative_amount: posted -5000, month total_cents is -5000"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY01-D10 negative_amount: body=$resp"
fi

# PY01-D11 stacktrace_leak: the 500 body exposes the traceback and file paths
status=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/summary?user=nobody&month=2099-01" || true)
resp=$(curl -s "$BASE/summary?user=nobody&month=2099-01" || true)
if [[ "$status" == "500" && "$resp" == *'Traceback (most recent call last)'* && "$resp" == *'File "'* ]]; then
    line=$(echo "$resp" | grep -m1 'File "' || true)
    echo "[REPRODUCED] PY01-D11 stacktrace_leak: 500 body contains traceback incl. $line"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY01-D11 stacktrace_leak: status=$status body=$resp"
fi

expected=$(python3 -c 'import json; print(len(json.load(open("DEFECTS.json"))["defects"]))')
echo "repro.sh: $REPRODUCED/$expected defects reproduced"
[[ "$REPRODUCED" == "$expected" ]]
