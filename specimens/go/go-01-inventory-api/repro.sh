#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -c 'from pathlib import Path; Path("bin").mkdir(exist_ok=True)'
go build -o bin/inventory-api .
python3 - <<'PY'
import concurrent.futures
import http.client
import json
import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

base = Path.cwd()
log = open(base / "server.log", "wb")
server = subprocess.Popen(
    [str(base / "bin/inventory-api")],
    cwd=base,
    env={**os.environ, "PORT": "8331"},
    stdout=log,
    stderr=subprocess.STDOUT,
)

def request(method, path, payload=None, headers=None):
    body = None if payload is None else json.dumps(payload).encode()
    request_headers = dict(headers or {})
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection("127.0.0.1", 8331, timeout=4)
    try:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        return response.status, response.read().decode(errors="replace"), dict(response.getheaders())
    except Exception as error:
        return 0, str(error), {}
    finally:
        connection.close()

def result(defect, case, reproduced, evidence):
    state = "REPRODUCED" if reproduced else "NOT REPRODUCED"
    print(f"[{state}] {defect} {case}: {evidence}")
    return reproduced

def create(sku, stock=10, locations=None, supplier=True):
    payload = {"sku": sku, "name": sku, "stock": stock, "locations": ["A1"] if locations is None else locations}
    if supplier:
        payload["supplier"] = {"name": "North Supply"}
    return request("POST", "/items", payload)

def panic_evidence(fragment):
    log.flush()
    text = (base / "server.log").read_text(errors="replace")
    lines = [line.strip() for line in text.splitlines() if fragment in line]
    return lines[-1] if lines else ""

for _ in range(100):
    if server.poll() is not None:
        break
    status, _, _ = request("GET", "/report")
    if status == 200:
        break
    time.sleep(0.03)

passed = 0
total = 11

create("parallel", 10)
barrier = __import__("threading").Barrier(51)
def reserve_once(_):
    barrier.wait()
    return request("POST", "/reserve", {"sku": "parallel", "qty": 1})[0]
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
    futures = [pool.submit(reserve_once, i) for i in range(50)]
    barrier.wait()
    statuses = [future.result() for future in futures]
successes = statuses.count(200)
status, body, _ = request("GET", "/items/parallel")
stock = json.loads(body).get("stock") if status == 200 else "unavailable"
passed += result("GO01-D01", "parallel_reserve", successes > 10 or (isinstance(stock, int) and stock < 0),
                 f"successful={successes}, final_stock={stock}")

create("bulk", 0)
status, body, _ = request("POST", "/restock", {"sku": "bulk", "packs": 50000, "perPack": 50000})
wrapped = json.loads(body).get("stock") if status == 200 else None
passed += result("GO01-D02", "bulk_overflow", status == 200 and wrapped < 0,
                 f"HTTP {status}, returned_stock={wrapped}")

create("release", 10)
request("POST", "/reserve", {"sku": "release", "qty": 2})
status, body, _ = request("POST", "/release", {"sku": "release", "qty": 5})
released = json.loads(body) if status == 200 else {}
passed += result("GO01-D03", "excess_release", released.get("reserved") == -3 and released.get("stock") == 13,
                 f"HTTP {status}, stock={released.get('stock')}, reserved={released.get('reserved')}")

status, body, _ = request("GET", "/items")
panic = panic_evidence("index out of range")
passed += result("GO01-D04", "short_item_path", bool(panic),
                 panic or f"HTTP {status}, response={body[:80]!r}")

create("empty-locations", 4, locations=[])
status, body, _ = request("GET", "/items/empty-locations")
panic = panic_evidence("integer divide by zero")
passed += result("GO01-D05", "empty_location_average", bool(panic),
                 panic or f"HTTP {status}, response={body[:80]!r}")

create("no-supplier", 4, supplier=False)
status, body, _ = request("GET", "/items/no-supplier")
panic = panic_evidence("nil pointer dereference")
passed += result("GO01-D06", "missing_supplier_view", bool(panic),
                 panic or f"HTTP {status}, response={body[:80]!r}")

status, body, _ = request("GET", "/report?limit=100")
panic = panic_evidence("slice bounds out of range")
passed += result("GO01-D07", "report_limit", bool(panic),
                 panic or f"HTTP {status}, response={body[:80]!r}")

fd_path = Path(f"/proc/{server.pid}/fd")
before = len(list(fd_path.iterdir()))
for _ in range(25):
    request("GET", "/search?q=tea")
after = len(list(fd_path.iterdir()))
passed += result("GO01-D08", "request_fd_growth", after - before >= 20,
                 f"open_fds_before={before}, open_fds_after={after}")

connection = http.client.HTTPConnection("127.0.0.1", 8331, timeout=4)
try:
    connection.request("POST", "/items", body=b"{", headers={"Content-Type": "application/json"})
    response = connection.getresponse()
    malformed_status = response.status
    malformed_body = response.read().decode(errors="replace")
finally:
    connection.close()
passed += result("GO01-D09", "malformed_item_json", malformed_status == 201 and '"sku":""' in malformed_body,
                 f"HTTP {malformed_status}, response={malformed_body.strip()}")

query = urllib.parse.quote("<script>alert(7)</script>")
status, body, headers = request("GET", "/search?q=" + query)
passed += result("GO01-D10", "search_markup", status == 200 and "<script>alert(7)</script>" in body and "text/html" in headers.get("Content-Type", ""),
                 f"HTTP {status}, content_type={headers.get('Content-Type')}, body={body.strip()}")

source = (base / "main.go").read_text()
match = re.search(r'const adminToken = "([^"]+)"', source)
token = match.group(1) if match else ""
status, body, _ = request("POST", "/admin/reset", headers={"X-Admin-Token": token})
passed += result("GO01-D11", "source_token_reset", bool(token) and status == 204,
                 f"source_value_present={bool(token)}, HTTP {status}")

server.terminate()
try:
    server.wait(timeout=3)
except subprocess.TimeoutExpired:
    server.kill()
    server.wait()
log.close()
raise SystemExit(0 if passed == total else 1)
PY
