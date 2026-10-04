#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

NODE_FLAGS=""
if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>23||(a===23&&b>=6)?0:1)'; then
  NODE_FLAGS="--experimental-strip-types --no-warnings"
fi

PORT="${PORT:-8321}"
BASE="http://127.0.0.1:$PORT"
mkdir -p out
PORT="$PORT" node $NODE_FLAGS server.ts >out/repro-server.log 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 100); do
  curl -fsS "$BASE/health" >/dev/null 2>&1 && break
  sleep 0.1
done
curl -fsS "$BASE/health" >/dev/null

python3 - "$BASE" <<'PY'
import json, sys, time, urllib.error, urllib.parse, urllib.request

BASE = sys.argv[1]
results = {}


def call(method, path, body=None, user="alice", timeout=30, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("content-type", "application/json")
    if user:
        req.add_header("X-User", user)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def report(did, name, ok, evidence):
    results[did] = ok
    tag = "[REPRODUCED]" if ok else "[NOT REPRODUCED]"
    print(f"{tag} {did} {name}: {evidence}", flush=True)


def create(title, user="alice", **extra):
    status, text = call("POST", "/tasks", {"title": title, **extra}, user=user)
    return status, (json.loads(text) if text.startswith("{") else text)


def case(did, name, fn):
    try:
        ok, evidence = fn()
    except Exception as exc:  # report and keep going
        ok, evidence = False, f"harness error: {exc!r}"
    report(did, name, ok, evidence)


def completion_empty_board():
    status, text = call("GET", "/board")
    board = json.loads(text)
    return status == 200 and board["completion"] is None, f"GET /board on an empty board -> {status} completion={board['completion']!r}"


def done_to_review():
    _, t = create("Ship invoice export")
    for step in ("in_progress", "review", "done"):
        call("POST", f"/tasks/{t['id']}/move", {"to": step})
    status, text = call("POST", f"/tasks/{t['id']}/move", {"to": "review"})
    moved = json.loads(text)
    return status == 200 and moved["status"] == "review", f"done -> review returned {status}, status={moved.get('status')!r}, advertised next for done is ['archived']"


def patch_mass_assignment():
    _, t = create("Quarterly budget")
    status, text = call("PATCH", f"/tasks/{t['id']}", {"status": "archived", "ownerId": "mallory", "id": 4242})
    p = json.loads(text)
    ok = status == 200 and p["status"] == "archived" and p["ownerId"] == "mallory" and p["id"] == 4242
    return ok, f"PATCH {{status,ownerId,id}} -> {status} status={p.get('status')!r} ownerId={p.get('ownerId')!r} id={p.get('id')!r}"


def move_missing_task():
    status, text = call("POST", "/tasks/99999/move", {"to": "review"})
    err = json.loads(text).get("error", "")
    return status == 500 and "undefined" in err, f"POST /tasks/99999/move -> {status} error={err!r}"


def error_stack_exposed():
    status, text = call("GET", "/search?q=" + urllib.parse.quote("["))
    body = json.loads(text)
    stack = body.get("stack") or ""
    frame = next((l.strip() for l in stack.splitlines() if "board.ts" in l), "")
    return status == 500 and frame != "", f"GET /search?q=[ -> {status}, stack frame leaked: {frame!r}"


def priority_nan():
    status, t = create("Renew TLS certificate", priority="high")
    return status == 201 and t["priority"] is None, f"priority='high' -> {status} stored priority={t['priority']!r} (JSON for NaN)"


def search_html_xss():
    payload = "<img src=x onerror=alert(document.domain)>"
    create(payload)
    status, text = call("GET", "/search?q=onerror")
    return status == 200 and payload in text, f"GET /search?q=onerror -> {status} body contains {payload!r} unescaped"


def move_without_owner():
    _, t = create("Alice's private task", user="alice")
    status, text = call("POST", f"/tasks/{t['id']}/move", {"to": "in_progress"}, user="mallory")
    moved = json.loads(text)
    return status == 200 and moved["ownerId"] == "alice", f"mallory moved alice's task {t['id']} -> {status} status={moved.get('status')!r}"


def column_order_lexicographic():
    for i in range(12):
        create(f"Backlog item {i}")
    _, text = call("GET", "/board")
    ids = json.loads(text)["columns"]["todo"]["ids"]
    return ids != sorted(ids), f"todo ids listed as {ids}"


def page_drops_item():
    for i in range(3):
        create(f"pagetest {i}")
    s1, p1 = call("GET", "/search?q=pagetest&size=2&page=1")
    s2, p2 = call("GET", "/search?q=pagetest&size=2&page=2")
    n1, n2 = p1.count("<li"), p2.count("<li")
    return n1 + n2 < 3, f"3 matches, size=2: page1 has {n1} item(s), page2 has {n2} item(s)"


def unbounded_body():
    size = 12 * 1024 * 1024
    status, text = call("POST", "/tasks", raw=json.dumps({"title": "x" * size}).encode())
    t = json.loads(text)
    return status == 201 and len(t["title"]) == size, f"{size}-byte title accepted -> {status}, stored title length {len(t.get('title', ''))}"


def search_regex_redos():
    create("a" * 29 + "!")
    t0 = time.time()
    call("GET", "/search?q=" + urllib.parse.quote("pagetest"))
    base = time.time() - t0
    t0 = time.time()
    status, _ = call("GET", "/search?q=" + urllib.parse.quote("^(a+)+$"), timeout=120)
    slow = time.time() - t0
    return slow > 1.0 and slow > 20 * base, f"q=^(a+)+$ took {slow:.2f}s (normal query {base:.3f}s), status {status}"


case("TS01-D04", "completion_empty_board", completion_empty_board)
case("TS01-D01", "done_to_review", done_to_review)
case("TS01-D02", "patch_mass_assignment", patch_mass_assignment)
case("TS01-D03", "move_missing_task", move_missing_task)
case("TS01-D11", "error_stack_exposed", error_stack_exposed)
case("TS01-D07", "priority_nan", priority_nan)
case("TS01-D08", "search_html_xss", search_html_xss)
case("TS01-D10", "move_without_owner", move_without_owner)
case("TS01-D06", "column_order_lexicographic", column_order_lexicographic)
case("TS01-D12", "page_drops_item", page_drops_item)
case("TS01-D09", "unbounded_body", unbounded_body)
case("TS01-D05", "search_regex_redos", search_regex_redos)

expected = {d["id"] for d in json.load(open("DEFECTS.json"))["defects"]}
missing = expected - set(results)
for did in sorted(missing):
    print(f"[NOT REPRODUCED] {did} missing_case: repro.sh has no case for this defect")
ok = not missing and all(results.get(d) for d in expected)
print(f"{sum(1 for d in expected if results.get(d))}/{len(expected)} defects reproduced")
sys.exit(0 if ok else 1)
PY
