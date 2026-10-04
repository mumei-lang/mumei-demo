#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

NODE_FLAGS=""
if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>23||(a===23&&b>=6)?0:1)'; then
  NODE_FLAGS="--experimental-strip-types --no-warnings"
fi

PORT="${PORT:-8322}"
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

NODE_FLAGS="$NODE_FLAGS" python3 - "$BASE" <<'PY'
import concurrent.futures, http.client, http.server, json, os, re, subprocess, sys, threading, time, urllib.parse

BASE = sys.argv[1]
HOSTPORT = urllib.parse.urlparse(BASE).netloc
results = {}


def call(method, path, body=None, headers=None):
    conn = http.client.HTTPConnection(HOSTPORT, timeout=30)
    data = json.dumps(body) if body is not None else None
    conn.request(method, path, body=data, headers={"content-type": "application/json", **(headers or {})})
    r = conn.getresponse()
    text = r.read().decode()
    loc = r.getheader("location")
    conn.close()
    return r.status, text, loc


def shorten(**body):
    status, text, _ = call("POST", "/shorten", body)
    return status, json.loads(text)


def case(did, name, fn):
    try:
        ok, evidence = fn()
    except Exception as exc:
        ok, evidence = False, f"harness error: {exc!r}"
    results[did] = ok
    print(f"{'[REPRODUCED]' if ok else '[NOT REPRODUCED]'} {did} {name}: {evidence}", flush=True)


def code_from_math_random():
    os.makedirs("out", exist_ok=True)
    with open("out/probe-code.mjs", "w") as f:
        f.write('import { generateCode } from "../links.ts";\n'
                'Math.random = () => 0.123456789;\n'
                'const a = generateCode();\n'
                'Math.random = () => 0.123456789;\n'
                'console.log(a, generateCode());\n')
    cmd = ["node", *os.environ.get("NODE_FLAGS", "").split(), "out/probe-code.mjs"]
    a, b = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.split()
    return a == b, f"with Math.random pinned to 0.123456789, generateCode() returned {a!r} twice ({b!r})"


def alias_overwrite():
    s1, l1 = shorten(url="https://intranet.example.com/handbook", alias="docs")
    s2, l2 = shorten(url="https://attacker.example.net/login", alias="docs")
    _, _, loc = call("GET", "/r/docs")
    return s2 == 201 and loc == "https://attacker.example.net/login", f"second alias=docs -> {s2}; /r/docs now redirects to {loc}"


def javascript_redirect():
    status, link = shorten(url="javascript:alert(document.cookie)")
    rs, _, loc = call("GET", f"/r/{link['code']}")
    return status == 201 and rs == 302 and loc.startswith("javascript:"), f"shorten -> {status}; GET /r/{link['code']} -> {rs} Location: {loc}"


def click_lost_update():
    _, link = shorten(url="https://example.com/race")
    n = 200
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
        codes = list(pool.map(lambda _: call("GET", f"/r/{link['code']}")[0], range(n)))
    _, text, _ = call("GET", f"/stats/{link['code']}")
    clicks = json.loads(text)["clicks"]
    return codes.count(302) == n and clicks < n, f"{codes.count(302)} redirects served, stats clicks={clicks}"


def clicks_per_day_div_zero():
    _, link = shorten(url="https://example.com/today")
    call("GET", f"/r/{link['code']}")
    _, text, _ = call("GET", f"/stats/{link['code']}")
    st = json.loads(text)
    return st["clicks"] == 1 and st["clicksPerDay"] is None, f"clicks={st['clicks']} clicksPerDay={st['clicksPerDay']!r} on creation day"


def hardcoded_admin_token():
    token = re.search(r'ADMIN_TOKEN = "([^"]+)"', open("server.ts").read()).group(1)
    shorten(url="https://example.com/victim", alias="victim")
    denied, _, _ = call("POST", "/admin/delete", {"code": "victim"}, {"X-Admin": "guess"})
    status, text, _ = call("POST", "/admin/delete", {"code": "victim"}, {"X-Admin": token})
    return denied == 403 and status == 200 and json.loads(text)["deleted"], f"X-Admin={token!r} copied from source -> {status} {text}"


def alias_case_lookup():
    _, link = shorten(url="https://example.com/promo", alias="Promo")
    status, _, _ = call("GET", "/r/Promo")
    return status == 404, f"alias 'Promo' stored as {link['code']!r}; GET /r/Promo -> {status}"


def alias_truncated():
    s, link = shorten(url="https://example.com/spring", alias="spring24")
    status, _, _ = call("GET", "/r/spring24")
    return s == 201 and link["code"] != "spring24" and status == 404, f"8-char alias 'spring24' accepted as {link['code']!r}; GET /r/spring24 -> {status}"


def expired_link_resolves():
    _, link = shorten(url="https://example.com/flash-sale", ttlSeconds=1)
    time.sleep(2.2)
    status, _, loc = call("GET", f"/r/{link['code']}")
    return status == 302, f"ttlSeconds=1, after 2.2s GET /r/{link['code']} -> {status} {loc}"


def preview_ssrf():
    hits = []

    class Internal(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            body = b"<html><title>internal-metadata</title>db_password=hunter2</html>"
            self.send_response(200)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Internal)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        target = f"http://127.0.0.1:{srv.server_port}/latest/meta-data"
        status, link = shorten(url=target, preview=True)
        snippet = (link.get("preview") or {}).get("snippet", "")
    finally:
        srv.shutdown()
    return status == 201 and "db_password" in snippet and hits, f"preview of {target} -> server fetched {hits}, snippet={snippet[-30:]!r}"


def stats_unknown_code():
    status, text, _ = call("GET", "/stats/doesnotexist")
    return status == 500, f"GET /stats/doesnotexist -> {status} {text}"


case("TS02-D01", "code_from_math_random", code_from_math_random)
case("TS02-D02", "alias_overwrite", alias_overwrite)
case("TS02-D03", "javascript_redirect", javascript_redirect)
case("TS02-D04", "click_lost_update", click_lost_update)
case("TS02-D05", "clicks_per_day_div_zero", clicks_per_day_div_zero)
case("TS02-D06", "hardcoded_admin_token", hardcoded_admin_token)
case("TS02-D07", "alias_case_lookup", alias_case_lookup)
case("TS02-D08", "alias_truncated", alias_truncated)
case("TS02-D09", "expired_link_resolves", expired_link_resolves)
case("TS02-D10", "preview_ssrf", preview_ssrf)
case("TS02-D11", "stats_unknown_code", stats_unknown_code)

expected = {d["id"] for d in json.load(open("DEFECTS.json"))["defects"]}
missing = expected - set(results)
for did in sorted(missing):
    print(f"[NOT REPRODUCED] {did} missing_case: repro.sh has no case for this defect")
ok = not missing and all(results.get(d) for d in expected)
print(f"{sum(1 for d in expected if results.get(d))}/{len(expected)} defects reproduced")
sys.exit(0 if ok else 1)
PY
