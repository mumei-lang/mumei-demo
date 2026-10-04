#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONDONTWRITEBYTECODE=1
DATA_DIR=$(mktemp -d)
PORT=${PORT:-8312}
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

mkacct() {  # owner label initial -> prints id
    curl -s -X POST "$BASE/accounts" -H "X-Owner: $1" -H 'Content-Type: application/json' \
        -d "{\"owner\": \"$1\", \"label\": \"$2\", \"initial_cents\": $3}" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
}
balance() {  # id -> cents
    curl -s "$BASE/accounts/$1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["balance_cents"])'
}
total() {
    curl -s "$BASE/accounts" | python3 -c 'import json,sys; print(sum(a["balance_cents"] for a in json.load(sys.stdin)["accounts"]))'
}

# PY03-D01 negative_transfer: a negative amount pulls money from the destination
c=$(mkacct carol a1 100); d=$(mkacct dave a2 100)
curl -s -o /dev/null -X POST "$BASE/transfer" -H 'X-Owner: carol' -H 'Content-Type: application/json' \
    -d "{\"from\": $c, \"to\": $d, \"amount_cents\": -50}"
cb=$(balance "$c"); db=$(balance "$d")
if [[ "$cb" == "125" && "$db" == "50" ]]; then
    echo "[REPRODUCED] PY03-D01 negative_transfer: amount -50 -> src=$cb dst=$db"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY03-D01 negative_transfer: src=$cb dst=$db"
fi

# PY03-D02 fee_overdraft: the cover check ignores the fee, balance ends negative
e=$(mkacct erin a3 100); f=$(mkacct fred a4 0)
curl -s -o /dev/null -X POST "$BASE/transfer" -H 'X-Owner: erin' -H 'Content-Type: application/json' \
    -d "{\"from\": $e, \"to\": $f, \"amount_cents\": 100}"
eb=$(balance "$e")
if [[ "$eb" == "-25" ]]; then
    echo "[REPRODUCED] PY03-D02 fee_overdraft: transfer 100 of 100 -> balance $eb (fee uncovered)"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY03-D02 fee_overdraft: balance=$eb"
fi

# PY03-D03 double_close: closing an already-closed account appends a second entry
g=$(mkacct gina a5 40)
curl -s -o /dev/null -X POST "$BASE/close" -H 'X-Owner: gina' -H 'Content-Type: application/json' -d "{\"id\": $g}"
curl -s -o /dev/null -X POST "$BASE/close" -H 'X-Owner: gina' -H 'Content-Type: application/json' -d "{\"id\": $g}"
closes=$(curl -s "$BASE/statement/$g" | python3 -c 'import json,sys; print(sum(1 for e in json.load(sys.stdin)["entries"] if e["kind"]=="close"))')
if [[ "$closes" == "2" ]]; then
    echo "[REPRODUCED] PY03-D03 double_close: statement has $closes close entries after two closes"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY03-D03 double_close: close entries=$closes"
fi

# PY03-D04 transfer_lost_update: 50 parallel transfers of 1 cent lose updates
h=$(mkacct hank a6 1000); i=$(mkacct ivy a7 0)
python3 - "$BASE" "$h" "$i" <<'EOF'
import json, sys, threading, urllib.request
base, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
barrier = threading.Barrier(50)
def fire(_):
    barrier.wait()
    req = urllib.request.Request(
        base + "/transfer",
        data=json.dumps({"from": int(src), "to": int(dst), "amount_cents": 1}).encode(),
        headers={"Content-Type": "application/json", "X-Owner": "hank"},
    )
    try:
        urllib.request.urlopen(req).read()
    except Exception:
        pass
threads = [threading.Thread(target=fire, args=(n,)) for n in range(50)]
for t in threads: t.start()
for t in threads: t.join()
EOF
hb=$(balance "$h"); ib=$(balance "$i")
if [[ "$hb" != "-300" ]]; then
    echo "[REPRODUCED] PY03-D04 transfer_lost_update: after 50x(1+25) debits src=$hb (expected -300), dst=$ib"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY03-D04 transfer_lost_update: src=$hb dst=$ib look correct"
fi

# PY03-D05 negative_page_offset: offset=-2&limit=10 returns the tail entries
j=$(mkacct jack a8 0)
for _ in 1 2 3; do
    curl -s -o /dev/null -X POST "$BASE/transfer" -H 'X-Owner: jack' -H 'Content-Type: application/json' \
        -d "{\"from\": $h, \"to\": $j, \"amount_cents\": 1}" || true
done
# transfers may fail on balance; use close entries instead if needed: top up via house->jack
count=$(curl -s "$BASE/statement/$j" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["entries"]))')
tail=$(curl -s "$BASE/statement/$j?offset=-2&limit=10" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["entries"]))')
if [[ "$count" -ge 3 && "$tail" == "2" ]]; then
    echo "[REPRODUCED] PY03-D05 negative_page_offset: offset=-2 limit=10 returned $tail tail entries of $count"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY03-D05 negative_page_offset: entries=$count tail=$tail"
fi

# PY03-D06 debit_without_rollback: failed destination leg keeps the debit
k=$(mkacct kate a9 200)
before=$(total)
status=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/transfer" -H 'X-Owner: kate' \
    -H 'Content-Type: application/json' -d "{\"from\": $k, \"to\": 999, \"amount_cents\": 50}" || true)
after=$(total)
if [[ "$status" == "404" && $((before - after)) -eq 50 ]]; then
    echo "[REPRODUCED] PY03-D06 debit_without_rollback: HTTP $status but total $before -> $after (50 destroyed)"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY03-D06 debit_without_rollback: status=$status total $before -> $after"
fi

# PY03-D07 cross_owner_read: any caller reads any account
resp=$(curl -s -H 'X-Owner: mallory' "$BASE/accounts/$c" || true)
if [[ "$resp" == *'"owner": "carol"'* ]]; then
    echo "[REPRODUCED] PY03-D07 cross_owner_read: X-Owner mallory read carol's account: $resp"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY03-D07 cross_owner_read: body=$resp"
fi

# PY03-D08 label_xss: account label is interpolated into the HTML statement raw
x=$(curl -s -X POST "$BASE/accounts" -H 'X-Owner: luke' -H 'Content-Type: application/json' \
    -d '{"owner": "luke", "label": "<script>alert(1)</script>", "initial_cents": 10}' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
html=$(curl -s "$BASE/statement/$x.html" || true)
if [[ "$html" == *'<script>alert(1)</script>'* ]]; then
    echo "[REPRODUCED] PY03-D08 label_xss: statement HTML contains raw <script> label"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY03-D08 label_xss: html=$html"
fi

# PY03-D09 field_smuggling: balance_cents set via request body bypasses the cap
resp=$(curl -s -X POST "$BASE/accounts" -H 'X-Owner: mallory' -H 'Content-Type: application/json' \
    -d '{"owner": "mallory", "label": "spare", "initial_cents": 50, "balance_cents": 1000000}' || true)
if [[ "$resp" == *'"balance_cents": 1000000'* ]]; then
    echo "[REPRODUCED] PY03-D09 field_smuggling: balance_cents=1000000 accepted despite 10000 initial cap"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY03-D09 field_smuggling: body=$resp"
fi

# PY03-D10 unowned_debit: transfer debits 'from' without checking the caller owns it
l=$(mkacct lisa a10 500); m=$(mkacct mike a11 0)
status=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/transfer" -H 'X-Owner: eve' \
    -H 'Content-Type: application/json' -d "{\"from\": $l, \"to\": $m, \"amount_cents\": 100}" || true)
lb=$(balance "$l")
if [[ "$status" == "200" && "$lb" == "375" ]]; then
    echo "[REPRODUCED] PY03-D10 unowned_debit: X-Owner eve debited lisa's account ($lb) successfully"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY03-D10 unowned_debit: status=$status balance=$lb"
fi

expected=$(python3 -c 'import json; print(len(json.load(open("DEFECTS.json"))["defects"]))')
echo "repro.sh: $REPRODUCED/$expected defects reproduced"
[[ "$REPRODUCED" == "$expected" ]]
