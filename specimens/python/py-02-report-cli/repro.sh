#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONDONTWRITEBYTECODE=1
WORK=$(mktemp -d)
REPRODUCED=0
trap 'rm -rf "$WORK"' EXIT

# PY02-D01 float_amounts: 3h at rate 0.1 prints a binary-float artefact
cat > "$WORK/float.csv" <<'CSV'
worker,date,project,duration
w,2026-09-14,p,3h
CSV
out=$(python3 report.py --input "$WORK/float.csv" --rate 0.1 --out "$WORK/float.txt" 2>&1 || true)
if [[ "$out" == *'0.30000000000000004'* ]]; then
    amt=$(echo "$out" | grep -m1 'amount:' | sed 's/^ *//')
    echo "[REPRODUCED] PY02-D01 float_amounts: rate 0.1 x 3h -> $amt"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY02-D01 float_amounts: output=$out"
fi

# PY02-D02 zero_total_worker: a worker whose rows total 0m crashes the run
cat > "$WORK/zero.csv" <<'CSV'
worker,date,project,duration
zed,2026-09-14,p,0m
CSV
err=$(python3 report.py --input "$WORK/zero.csv" --rate 100 --out "$WORK/z.txt" 2>&1 >/dev/null || true)
if [[ "$err" == *ZeroDivisionError* ]]; then
    echo "[REPRODUCED] PY02-D02 zero_total_worker: worker 'zed' with 0m -> ZeroDivisionError"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY02-D02 zero_total_worker: err=$err"
fi

# PY02-D03 out_arg_injection: --out is interpolated into a shell command
cat > "$WORK/cli.csv" <<'CSV'
worker,date,project,duration
w,2026-09-14,p,1h
CSV
SPECIMEN_DIR="$PWD"
(cd "$WORK" && PYTHONDONTWRITEBYTECODE=1 python3 "$SPECIMEN_DIR/report.py" \
    --input cli.csv --rate 100 --out 'rep.txt; echo INJECTED > marker.txt' >/dev/null 2>&1 || true)
if [[ -f "$WORK/marker.txt" && "$(cat "$WORK/marker.txt")" == "INJECTED" ]]; then
    echo "[REPRODUCED] PY02-D03 out_arg_injection: --out 'x; echo INJECTED > marker.txt' created marker.txt=INJECTED"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY02-D03 out_arg_injection: marker.txt missing or wrong"
fi

# PY02-D04 short_row_index: a 3-column row raises IndexError in parse_row
err=$(python3 -c "import report; report.parse_row(['zed','2026-09-14','p'])" 2>&1 || true)
if [[ "$err" == *IndexError* ]]; then
    echo "[REPRODUCED] PY02-D04 short_row_index: 3-column row -> IndexError"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY02-D04 short_row_index: err=$err"
fi

# PY02-D05 first_day_skipped: overtime on the first day is dropped
got=$(python3 -c 'import timesheet; print(timesheet.overtime_minutes([600, 100], 480))')
if [[ "$got" == "0" ]]; then
    echo "[REPRODUCED] PY02-D05 first_day_skipped: overtime_minutes([600,100],480)=$got (day1 OT of 120 lost)"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY02-D05 first_day_skipped: got=$got"
fi

# PY02-D06 duration_regex_hang: a 24-digit non-matching duration stalls the parse
result=$(python3 - <<'EOF'
import subprocess, sys
try:
    subprocess.run(
        [sys.executable, "-c",
         "import timesheet; timesheet.parse_duration('1' * 24 + 'x')"],
        timeout=5, capture_output=True,
    )
    print("finished")
except subprocess.TimeoutExpired:
    print("timeout")
EOF
)
if [[ "$result" == "timeout" ]]; then
    echo "[REPRODUCED] PY02-D06 duration_regex_hang: parse of 24-digit duration exceeded 5s timeout"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY02-D06 duration_regex_hang: parse returned within 5s"
fi

# PY02-D07 silent_truncation: a bad row ends parsing but the run still exits 0
cat > "$WORK/mid.csv" <<'CSV'
worker,date,project,duration
early,2026-09-14,p,8h
mid,2026-09-14,p,oops
late,2026-09-15,p,8h
CSV
set +e
out=$(python3 report.py --input "$WORK/mid.csv" --rate 100 --out "$WORK/mid.txt" 2>&1)
rc=$?
set -e
if [[ $rc -eq 0 && "$out" == *early* && "$out" != *late* ]]; then
    echo "[REPRODUCED] PY02-D07 silent_truncation: bad middle row -> exit 0, 'late' worker missing from report"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY02-D07 silent_truncation: rc=$rc out=$out"
fi

# PY02-D08 negative_duration: -2h is accepted and subtracts from the total
cat > "$WORK/neg.csv" <<'CSV'
worker,date,project,duration
neg,2026-09-14,p,-2h
neg,2026-09-15,p,8h
CSV
out=$(python3 report.py --input "$WORK/neg.csv" --rate 100 --out "$WORK/neg.txt" 2>&1 || true)
if [[ "$out" == *'hours: 6.00'* ]]; then
    echo "[REPRODUCED] PY02-D08 negative_duration: -2h + 8h -> hours: 6.00"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY02-D08 negative_duration: out=$out"
fi

# PY02-D09 saturday_not_weekend: Saturday hours do not count as weekend
cat > "$WORK/sat.csv" <<'CSV'
worker,date,project,duration
sat,2026-09-19,p,2h
sat,2026-09-21,p,8h
CSV
out=$(python3 report.py --input "$WORK/sat.csv" --rate 100 --out "$WORK/sat.txt" 2>&1 || true)
dow=$(python3 -c 'from datetime import date; print(date(2026, 9, 19).strftime("%A"))')
if [[ "$out" == *'weekend: 0h00m'* ]]; then
    echo "[REPRODUCED] PY02-D09 saturday_not_weekend: 2h worked on 2026-09-19 ($dow) -> weekend: 0h00m"
    REPRODUCED=$((REPRODUCED + 1))
else
    echo "[NOT REPRODUCED] PY02-D09 saturday_not_weekend: out=$out"
fi

expected=$(python3 -c 'import json; print(len(json.load(open("DEFECTS.json"))["defects"]))')
echo "repro.sh: $REPRODUCED/$expected defects reproduced"
[[ "$REPRODUCED" == "$expected" ]]
