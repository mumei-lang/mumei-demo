#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -c 'from pathlib import Path; Path("bin").mkdir(exist_ok=True); Path("tmp").mkdir(exist_ok=True)'
go build -o bin/auth-gateway .
python3 - <<'PY'
import hashlib
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

root = Path.cwd()
server_log = open(root / "server.log", "wb")
server = subprocess.Popen(
    [str(root / "bin/auth-gateway")],
    cwd=root,
    env={**os.environ, "PORT": "8332"},
    stdout=server_log,
    stderr=subprocess.STDOUT,
)
target_server = None
passed = 0
total = 11

def request(method, path, payload=None, token=None):
    headers = {}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    connection = http.client.HTTPConnection("127.0.0.1", 8332, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read().decode(errors="replace"), dict(response.getheaders())
    except Exception as error:
        return 0, str(error), {}
    finally:
        connection.close()

def result(defect, case, reproduced, evidence):
    global passed
    state = "REPRODUCED" if reproduced else "NOT REPRODUCED"
    print(f"[{state}] {defect} {case}: {evidence}")
    passed += int(reproduced)

def login(name, password, next_url=None):
    suffix = "" if next_url is None else "?next=" + urllib.parse.quote(next_url, safe="")
    return request("POST", "/login" + suffix, {"user": name, "password": password})

def profile(token, name):
    return request("GET", "/profile?user=" + urllib.parse.quote(name), token=token)

def admin_password():
    source = (root / "main.go").read_text()
    match = re.search(r'const adminPassword = "([^"]+)"', source)
    return match.group(1) if match else ""

def panic_line(fragment):
    server_log.flush()
    lines = (root / "server.log").read_text(errors="replace").splitlines()
    matches = [line.strip() for line in lines if fragment in line]
    return matches[-1] if matches else ""

try:
    for _ in range(100):
        status, _, _ = request("GET", "/healthz")
        if status == 200:
            break
        time.sleep(0.03)

    status, body, _ = login("alice", "bluebird42")
    token = json.loads(body).get("token", "") if status == 200 else ""
    delta = abs(time.time_ns() - int(token)) if token.isdigit() else 10**30
    result("GO03-D01", "timestamp_token", token.isdigit() and delta < 5_000_000_000,
           f"token={token}, delta_ns={delta}")

    timing = subprocess.run(["go", "test", "-run", "TestTokenComparison", "-count=1", "-v", "."],
                            cwd=root, capture_output=True, text=True)
    timing_output = timing.stdout + timing.stderr
    timing_line = next((line.strip() for line in timing_output.splitlines() if "ratio=" in line), "")
    ratio_match = re.search(r"ratio=([0-9.]+)", timing_line)
    ratio = float(ratio_match.group(1)) if ratio_match else 0
    result("GO03-D02", "token_comparison_timing",
           timing.returncode == 0 and ratio > 5,
           timing_line or f"go test exit={timing.returncode}")

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        target_port = listener.getsockname()[1]
    target_code = (
        "from http.server import BaseHTTPRequestHandler,HTTPServer\n"
        "class H(BaseHTTPRequestHandler):\n"
        " def do_GET(self):\n"
        "  body=b'instance-profile: local-service-account'\n"
        "  self.send_response(200); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)\n"
        " def log_message(self,*args): pass\n"
        f"HTTPServer(('127.0.0.1',{target_port}),H).serve_forever()\n"
    )
    target_server = subprocess.Popen([sys.executable, "-c", target_code],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", target_port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.02)
    target_url = f"http://127.0.0.1:{target_port}/meta"
    status, body, _ = request("GET", "/proxy?target=" + urllib.parse.quote(target_url, safe=""), token=token)
    result("GO03-D03", "loopback_proxy", status == 200 and "instance-profile: local-service-account" in body,
           f"HTTP {status}, body={body.strip()!r}")

    bob_status, bob_body, _ = login("bob", "bluebird42")
    bob_token = json.loads(bob_body).get("token", "") if bob_status == 200 else ""
    status, body, _ = profile(bob_token, "alice")
    account_name = json.loads(body).get("name") if status == 200 else None
    result("GO03-D04", "cross_profile_lookup", status == 200 and account_name == "alice",
           f"HTTP {status}, requested=alice, returned={account_name!r}")

    alice_profile = json.loads(profile(token, "alice")[1])
    bob_profile = json.loads(profile(bob_token, "bob")[1])
    expected_hash = hashlib.sha1(b"bluebird42").hexdigest()
    same_hash = alice_profile.get("password_sha1") == bob_profile.get("password_sha1") == expected_hash
    result("GO03-D05", "profile_hashes", same_hash,
           f"alice_hash={alice_profile.get('password_sha1')}, bob_hash={bob_profile.get('password_sha1')}")

    password = admin_password()
    admin_status, admin_body, _ = login("admin", password)
    admin_token = json.loads(admin_body).get("token", "") if admin_status == 200 else ""
    rotate_status, _, _ = request("POST", "/rotate", token=admin_token)
    old_status, old_body, _ = profile(token, "alice")
    result("GO03-D06", "token_after_rotation", rotate_status == 204 and old_status == 200,
           f"rotate_http={rotate_status}, old_token_profile_http={old_status}")

    unknown_status, _, _ = login("ghost", "anything")
    panic = panic_line("nil pointer dereference")
    result("GO03-D07", "unknown_account", bool(panic), panic or f"HTTP {unknown_status}")

    statuses = [login("alice", "wrong-password")[0] for _ in range(20)]
    result("GO03-D08", "login_window", statuses.count(401) == 20 and 429 not in statuses,
           f"unauthorized={statuses.count(401)}, rate_limited={statuses.count(429)}")

    rotate_status, _, _ = request("POST", "/rotate", token=admin_token)
    result("GO03-D09", "source_password_rotation", bool(password) and rotate_status == 204,
           f"source_value_present={bool(password)}, HTTP {rotate_status}")

    health_status, health_body, _ = request("GET", "/healthz")
    health = json.loads(health_body) if health_status == 200 else {}
    result("GO03-D10", "health_configuration", health_status == 200 and bool(health.get("signing_key")),
           f"HTTP {health_status}, signing_key={health.get('signing_key')!r}")

    redirect_status, _, headers = login("alice", "bluebird42", "https://evil.example/")
    location = headers.get("Location", "")
    result("GO03-D11", "external_next", redirect_status == 302 and location == "https://evil.example/",
           f"HTTP {redirect_status}, location={location!r}")
finally:
    if target_server is not None:
        target_server.terminate()
        try:
            target_server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            target_server.kill()
            target_server.wait()
    server.terminate()
    try:
        server.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()
    server_log.close()

raise SystemExit(0 if passed == total else 1)
PY
