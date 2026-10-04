#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -c 'from pathlib import Path; Path("bin").mkdir(exist_ok=True); Path("tmp").mkdir(exist_ok=True)'
go build -o bin/logscan .
python3 - <<'PY'
import json
import os
import resource
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
binary = str(root / "bin/logscan")
tmp = root / "tmp"
tmp.mkdir(exist_ok=True)
passed = 0
total = 10

def result(defect, case, reproduced, evidence):
    global passed
    state = "REPRODUCED" if reproduced else "NOT REPRODUCED"
    print(f"[{state}] {defect} {case}: {evidence}")
    passed += int(reproduced)

def invoke(*args, cwd=None, preexec_fn=None):
    return subprocess.run([binary, *map(str, args)], cwd=cwd or root, capture_output=True,
                          text=True, preexec_fn=preexec_fn)

def make_log(name, lines):
    path = tmp / name
    path.write_text("\n".join(lines) + "\n")
    return path

single = make_log("one.log", ["2026-01-02T00:00:00Z GET /one 200 17ms"])
proc = invoke("-input", single, "-out", tmp / "pctl.txt", "-top", "1", "-percentiles", "100")
output = proc.stdout + proc.stderr
panic_line = next((line.strip() for line in output.splitlines() if "index out of range" in line), "")
result("GO02-D01", "percentile_boundary", proc.returncode != 0 and bool(panic_line), panic_line or f"exit={proc.returncode}")

proc = invoke("-input", single, "-since", "2099-01-01T00:00:00Z", "-out", tmp / "empty.txt")
output = proc.stdout + proc.stderr
panic_line = next((line.strip() for line in output.splitlines() if "integer divide by zero" in line), "")
result("GO02-D02", "empty_average", proc.returncode != 0 and bool(panic_line), panic_line or f"exit={proc.returncode}")

proc = invoke("-input", single, "-top", "-1", "-out", tmp / "negative.txt")
output = proc.stdout + proc.stderr
panic_line = next((line.strip() for line in output.splitlines() if "slice bounds out of range" in line), "")
result("GO02-D03", "negative_top", proc.returncode != 0 and bool(panic_line), panic_line or f"exit={proc.returncode}")

malformed = make_log("bad-time.log", ["not-a-time GET /clock-skew 200 21ms"])
proc = invoke("-input", malformed, "-top", "1", "-out", tmp / "bad-time-summary.txt")
result("GO02-D04", "timestamp_parse", proc.returncode == 0 and "/clock-skew 1" in proc.stdout,
       next((line.strip() for line in proc.stdout.splitlines() if "/clock-skew" in line), f"exit={proc.returncode}"))

payload = "payload.txt; touch pwned"
proc = invoke("-input", single, "-top", "1", "-out", payload, cwd=root)
marker = root / "pwned"
created = marker.exists()
if created:
    marker.unlink()
literal = root / payload
if literal.exists():
    literal.unlink()
result("GO02-D05", "output_shell", created, f"exit={proc.returncode}, marker_created={created}")

files = []
line = "2026-01-02T00:00:00Z GET /shared 200 9ms\n"
for index in range(48):
    path = tmp / f"worker-{index}.log"
    path.write_text(line * 1200)
    files.append(str(path))
race = subprocess.run(["go", "test", "-race", "-run", "TestWorkerCounts", "."],
                      cwd=root, capture_output=True, text=True,
                      env={**os.environ, "GO_TEST_FILES": ",".join(files), "GORACE": "halt_on_error=1"})
race_output = race.stdout + race.stderr
race_line = next((line.strip() for line in race_output.splitlines() if "WARNING: DATA RACE" in line), "")
result("GO02-D06", "worker_map_access", bool(race_line), race_line or f"go test exit={race.returncode}")

many = []
for index in range(100):
    path = tmp / f"fd-{index}.log"
    path.write_text(line)
    many.append(str(path))
def lower_limit():
    resource.setrlimit(resource.RLIMIT_NOFILE, (40, 40))
proc = invoke("-input", ",".join(many), "-workers", "1", "-out", tmp / "fd-summary.txt",
              preexec_fn=lower_limit)
error_line = next((line.strip() for line in (proc.stdout + proc.stderr).splitlines()
                   if "too many open files" in line.lower()), "")
result("GO02-D07", "file_descriptor_limit", proc.returncode != 0 and bool(error_line),
       error_line or f"exit={proc.returncode}")

small = tmp / "rss-small.log"
large = tmp / "rss-large.log"
sample = "2026-01-02T00:00:00Z GET /bulk 200 9ms\n"
small.write_text(sample * 10000)
large.write_text(sample * 400000)
measure = (
    "import resource,subprocess,sys; "
    "p=subprocess.run(sys.argv[1:],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True); "
    "print(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss); "
    "sys.exit(p.returncode)"
)
def rss(path, name):
    wrapper = subprocess.run([sys.executable, "-c", measure, binary, "-input", str(path),
                              "-top", "1", "-out", str(tmp / name)], cwd=root, capture_output=True, text=True)
    return int(wrapper.stdout.strip()) if wrapper.returncode == 0 else 0
small_rss = rss(small, "rss-small-summary.txt")
large_rss = rss(large, "rss-large-summary.txt")
result("GO02-D08", "input_memory_growth", large_rss > small_rss * 4 and large_rss > 30000,
       f"small_rss_kb={small_rss}, large_rss_kb={large_rss}")

world = tmp / "world.txt"
def clear_mask():
    os.umask(0)
proc = invoke("-input", single, "-top", "1", "-out", world, preexec_fn=clear_mask)
compressed = Path(str(world) + ".gz")
mode = (compressed.stat().st_mode & 0o777) if compressed.exists() else 0
result("GO02-D09", "summary_file_mode", proc.returncode == 0 and mode == 0o666,
       f"compressed_mode={mode:#06o}, exit={proc.returncode}")

boundary = make_log("boundary.log", [
    "2026-01-01T00:00:00Z GET /boundary 200 10ms",
    "2026-01-01T00:01:00Z GET /after 200 12ms",
])
proc = invoke("-input", boundary, "-since", "2026-01-01", "-top", "1",
              "-out", tmp / "boundary-summary.txt")
rows = [line.strip() for line in proc.stdout.splitlines() if line.startswith("/")]
result("GO02-D10", "since_boundary", proc.returncode == 0 and "Requests: 1" in proc.stdout and
       any(row.startswith("/after ") for row in rows) and not any(row.startswith("/boundary ") for row in rows),
       f"requests_line={next((line for line in proc.stdout.splitlines() if line.startswith('Requests:')), '')!r}, paths={rows}")

raise SystemExit(0 if passed == total else 1)
PY
