#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

cargo build --release 2>/dev/null
BIN="$PWD/target/release/kv-server"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"; jobs -p | xargs -r kill 2>/dev/null || true' EXIT

PASS=0; FAIL=0
report() {
  if [ "$3" = ok ]; then
    echo "[REPRODUCED] $1 $2: $4"; PASS=$((PASS+1))
  else
    echo "[NOT REPRODUCED] $1 $2: $4"; FAIL=$((FAIL+1))
  fi
}

SRV_PID=""
LAST_PORT=8341
start_server() {  # data_dir [extra env KV_DATA_DIR override already applied]
  LAST_PORT=$((LAST_PORT+1))
  KV_DATA_DIR="$1" PORT=$LAST_PORT "$BIN" & SRV_PID=$!
  for _ in $(seq 50); do
    curl -s -o /dev/null "http://127.0.0.1:$LAST_PORT/kv/x" && return 0
    sleep 0.1
  done
  return 1
}
stop_server() { kill "$SRV_PID" 2>/dev/null || true; wait "$SRV_PID" 2>/dev/null || true; }
base() { echo "http://127.0.0.1:$LAST_PORT"; }

# RS02-D01 out-of-bounds: malformed request line panics the handler thread.
start_server "$WORK/d1"
reply=$(python3 -c "
import socket
s = socket.create_connection(('127.0.0.1', $LAST_PORT))
s.sendall(b'GET\r\n\r\n')
s.settimeout(3)
try:
    print(s.recv(4096).decode(), end='')
except Exception as e:
    print('ERR', e)
" || true)
after=$(curl -s "$(base)/kv/x"; echo "rc=$?")
if [ -z "$reply" ] && [ "$after" != "" ]; then
  report RS02-D01 bad_request_line ok "malformed line got empty reply; server still answers: $after"
else
  report RS02-D01 bad_request_line fail "reply='$reply' after='$after'"
fi
stop_server

# RS02-D03 race-condition: 8 threads x 40 increments lose updates.
start_server "$WORK/d3"
final=$(python3 - "$LAST_PORT" <<'PY'
import http.client, sys, threading
port = int(sys.argv[1])
barrier = threading.Barrier(8)
def worker():
    barrier.wait()
    for _ in range(40):
        c = http.client.HTTPConnection('127.0.0.1', port)
        c.request('POST', '/incr/c?delta=1')
        c.getresponse().read()
        c.close()
ts = [threading.Thread(target=worker) for _ in range(8)]
for t in ts: t.start()
for t in ts: t.join()
c = http.client.HTTPConnection('127.0.0.1', port)
c.request('GET', '/incr_read')
PY
)
# read the counter via a fresh incr of 0 (adds nothing on top of final value)
final=$(curl -s -X POST "$(base)/incr/c?delta=0")
if [ "$final" -lt 320 ]; then
  report RS02-D03 lost_updates ok "counter=$final after 8x40 increments (expected 320)"
else
  report RS02-D03 lost_updates fail "counter=$final"
fi
stop_server

# RS02-D04 path-traversal: snapshot path escapes the data dir.
start_server "$WORK/d4"
UNIQ="snap_$$_$RANDOM"
curl -s -X PUT --data v "$(base)/kv/k" >/dev/null
curl -s -X POST "$(base)/snapshot?path=../../${UNIQ}.snap" >/dev/null
if [ -f "/tmp/${UNIQ}.snap" ] && [ ! -f "$WORK/d4/${UNIQ}.snap" ]; then
  report RS02-D04 snapshot_traversal ok "wrote /tmp/${UNIQ}.snap outside $WORK/d4"
  rm -f "/tmp/${UNIQ}.snap"
else
  report RS02-D04 snapshot_traversal fail "file not found outside data dir"
fi
stop_server

# RS02-D05 integer-overflow: i32 counter wraps negative (release profile).
start_server "$WORK/d5"
curl -s -X POST "$(base)/incr/n?delta=2147483647" >/dev/null
v=$(curl -s -X POST "$(base)/incr/n?delta=10")
if [ "$v" -lt 0 ]; then
  report RS02-D05 counter_wrap ok "i32::MAX + 10 wrapped to $v (release profile)"
else
  report RS02-D05 counter_wrap fail "v=$v"
fi
stop_server

# RS02-D06 logic-error: key byte-truncation collides distinct keys.
start_server "$WORK/d6"
curl -s -X PUT --data first  "$(base)/kv/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa%C3%A9X" >/dev/null
curl -s -X PUT --data second "$(base)/kv/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa%C3%A9Y" >/dev/null
got=$(curl -s "$(base)/kv/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa%C3%A9X")
if [ "$got" = "second" ]; then
  report RS02-D06 key_collision ok "two distinct keys truncated to one; GET returns '$got'"
else
  report RS02-D06 key_collision fail "got=$got"
fi
stop_server

# RS02-D07 error-handling: prefix slice panics under the lock, poisoning it.
start_server "$WORK/d7"
curl -s -X PUT --data v "$(base)/kv/a%C3%A9" >/dev/null
before=$(curl -s "$(base)/kv/a%C3%A9")
curl -s -o /dev/null "$(base)/keys?prefix=ab" || true
sleep 0.2
set +e
after_out=$(curl -s --max-time 3 "$(base)/kv/a%C3%A9"); after_rc=$?
set -e
if [ "$before" = "v" ] && { [ "$after_rc" -ne 0 ] || [ "$after_out" != "v" ]; }; then
  report RS02-D07 poisoned_mutex ok "GET worked ('$before'), after poisoning request rc=$after_rc body='$after_out'"
else
  report RS02-D07 poisoned_mutex fail "before=$before after_rc=$after_rc out=$after_out"
fi
stop_server

# RS02-D08 resource-leak: stalled clients hold handler threads forever.
start_server "$WORK/d8"
before_n=$(ls /proc/$SRV_PID/task | wc -l)
python3 - "$LAST_PORT" <<'PY' &
import socket, sys, time
port = int(sys.argv[1])
socks = [socket.create_connection(('127.0.0.1', port)) for _ in range(16)]
for s in socks:
    s.sendall(b'GET /kv/x HTTP/1.1\r\nHost: x')   # partial request, no terminator
time.sleep(30)
PY
HOLDER=$!
sleep 1.5
after_n=$(ls /proc/$SRV_PID/task | wc -l)
if [ $((after_n - before_n)) -ge 15 ]; then
  report RS02-D08 stalled_threads ok "server threads $before_n -> $after_n while 16 clients stalled"
else
  report RS02-D08 stalled_threads fail "threads $before_n -> $after_n"
fi
kill $HOLDER 2>/dev/null || true
stop_server

# RS02-D09 hardcoded-secret: admin flush accepts the source token.
start_server "$WORK/d9"
curl -s -X PUT --data v "$(base)/kv/z" >/dev/null
out=$(curl -s -X POST "$(base)/admin/flush?token=kv-s3cr3t-flush")
got=$(curl -s -o /dev/null -w '%{http_code}' "$(base)/kv/z")
if [ "$out" = "flushed" ] && [ "$got" = "404" ]; then
  report RS02-D09 admin_token ok "flush with built-in token emptied the store (kv/z now 404)"
else
  report RS02-D09 admin_token fail "out=$out code=$got"
fi
stop_server

# RS02-D10 information-exposure: error body leaks the data dir and io error.
start_server "/proc/kv_d10_$$"
out=$(curl -s -X POST "$(base)/snapshot?path=x.snap")
if echo "$out" | grep -q '/proc/kv_d10_' && echo "$out" | grep -qi 'denied\|os error'; then
  report RS02-D10 error_leaks_path ok "500 body: $(echo "$out" | head -1)"
else
  report RS02-D10 error_leaks_path fail "out=$out"
fi
stop_server

# RS02-D11 xss: /ui echoes the query unescaped as text/html.
start_server "$WORK/d11"
out=$(curl -s "$(base)/ui?key=%3Cscript%3Ealert(1)%3C/script%3E")
ctype=$(curl -s -o /dev/null -w '%{content_type}' "$(base)/ui?key=x")
if echo "$out" | grep -q '<script>alert(1)</script>' && echo "$ctype" | grep -q text/html; then
  report RS02-D11 reflected_xss ok "script reflected verbatim in $ctype response"
else
  report RS02-D11 reflected_xss fail "out=$out ctype=$ctype"
fi
stop_server

# RS02-D02 unbounded-resource: Content-Length with no cap -> ~512MiB alloc. (last: heavy)
start_server "$WORK/d2"
rss_before=$(grep VmRSS /proc/$SRV_PID/status | awk '{print $2}')
python3 - "$LAST_PORT" <<'PY' &
import socket, sys, time
port = int(sys.argv[1])
s = socket.create_connection(('127.0.0.1', port))
s.sendall(b'PUT /kv/big HTTP/1.1\r\nHost: x\r\nContent-Length: 536870912\r\n\r\ntiny')
time.sleep(10)
PY
SLEEPY=$!
sleep 1.5
rss_after=$(grep VmRSS /proc/$SRV_PID/status | awk '{print $2}')
kill $SLEEPY 2>/dev/null || true
if [ $((rss_after - rss_before)) -gt 200000 ]; then
  report RS02-D02 huge_body ok "VmRSS ${rss_before}kB -> ${rss_after}kB after Content-Length: 536870912"
else
  report RS02-D02 huge_body fail "rss ${rss_before} -> ${rss_after}"
fi
stop_server

echo "== $PASS reproduced, $FAIL not =="
[ "$FAIL" -eq 0 ]
