#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

cargo build --release 2>/dev/null
BIN="$PWD/target/release/bank-core"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

panic_msg() { echo "$1" | awk '/panicked at/{getline; sub(/^ +/,""); print; exit}'; }

PASS=0; FAIL=0
report() {  # id repro ok evidence
  if [ "$3" = ok ]; then
    echo "[REPRODUCED] $1 $2: $4"; PASS=$((PASS+1))
  else
    echo "[NOT REPRODUCED] $1 $2: $4"; FAIL=$((FAIL+1))
  fi
}

# RS01-D01 float-money: accrue_interest truncates a cent vs exact integer math.
S="$WORK/d01.txt"
$BIN --state "$S" open whale 9388934101589121 0 >/dev/null
credited=$($BIN --state "$S" interest whale | grep -o 'credited [0-9]*' | awk '{print $2}')
exact=$(python3 -c 'print(9388934101589121 * 500 // 10000)')
if [ "$credited" != "$exact" ]; then
  report RS01-D01 float_interest ok "credited $credited but exact integer math gives $exact"
else
  report RS01-D01 float_interest fail "credited=$credited exact=$exact"
fi

# RS01-D02 integer-underflow: allowance wraps once spent > limit (release profile).
S="$WORK/d02.txt"
$BIN --state "$S" open a 100000 500 >/dev/null
$BIN --state "$S" fee a 600 >/dev/null   # fees bypass the limit, spent=600 > 500
allowance=$($BIN --state "$S" statement a | grep remaining_daily_allowance | awk '{print $2}')
if [ "${#allowance}" -gt 18 ]; then
  report RS01-D02 wrapped_allowance ok "remaining allowance wrapped to $allowance (release profile wrapping_sub)"
else
  report RS01-D02 wrapped_allowance fail "allowance=$allowance"
fi

# RS01-D03 missing-precondition: negative transfer moves money backwards.
S="$WORK/d03.txt"
$BIN --state "$S" open a 1000 9000000000 >/dev/null
$BIN --state "$S" open b 2000 9000000000 >/dev/null
$BIN --state "$S" transfer a b -500 >/dev/null
$BIN --state "$S" settle >/dev/null
ba=$($BIN --state "$S" balance a); bb=$($BIN --state "$S" balance b)
if [ "$ba" = 1500 ] && [ "$bb" = 1500 ]; then
  report RS01-D03 negative_transfer ok "a=1000->$ba b=2000->$bb after transferring -500"
else
  report RS01-D03 negative_transfer fail "a=$ba b=$bb"
fi

# RS01-D04 division-by-zero: empty recipient list.
set +e
out=$($BIN split 1000 2>&1); rc=$?
set -e
if [ $rc -ne 0 ] && echo "$out" | grep -q 'divide by zero'; then
  report RS01-D04 empty_split ok "exit $rc: $(panic_msg "$out")"
else
  report RS01-D04 empty_split fail "rc=$rc out=$out"
fi

# RS01-D05 out-of-bounds: account-at 99.
S="$WORK/d05.txt"
$BIN --state "$S" open a 100 9000000000 >/dev/null
set +e
out=$($BIN --state "$S" account-at 99 2>&1); rc=$?
set -e
if [ $rc -eq 101 ]; then
  report RS01-D05 index_oob ok "exit 101: $(panic_msg "$out")"
else
  report RS01-D05 index_oob fail "rc=$rc out=$out"
fi

# RS01-D06 invariant-violation: rejected transfer resets the spend counter.
S="$WORK/d06.txt"
$BIN --state "$S" open a 100000 1000 >/dev/null
$BIN --state "$S" open b 0 0 >/dev/null
$BIN --state "$S" transfer a b 600 >/dev/null 2>&1
$BIN --state "$S" transfer a b 600 >/dev/null 2>&1 || true   # rejected, resets counter
$BIN --state "$S" transfer a b 600 >/dev/null 2>&1
$BIN --state "$S" settle >/dev/null
bb=$($BIN --state "$S" balance b)
bb=$(echo "$bb" | tail -1)
if [ "$bb" -gt 1000 ]; then
  report RS01-D06 limit_bypass ok "settled $bb cents against a daily limit of 1000"
else
  report RS01-D06 limit_bypass fail "b=$bb"
fi

# RS01-D07 invalid-state-transition: settle credits a closed account.
S="$WORK/d07.txt"
$BIN --state "$S" open a 1000 9000000000 >/dev/null
$BIN --state "$S" open b 500 9000000000 >/dev/null
$BIN --state "$S" transfer a b 400 >/dev/null
$BIN --state "$S" close b --token bk-7f3a1c9e-ops >/dev/null
$BIN --state "$S" settle >/dev/null
bb=$($BIN --state "$S" balance b)
if [ "$bb" = 900 ]; then
  report RS01-D07 settle_closed ok "closed account b went 500->$bb via queued transfer"
else
  report RS01-D07 settle_closed fail "b=$bb"
fi

# RS01-D08 unbounded-resource: audit log grows without bound.
S="$WORK/d08.txt"
$BIN --state "$S" open a 100000000 9000000000 >/dev/null
printf 'deposit a 1\n%.0s' $(seq 5000) | $BIN --state "$S" batch
n=$($BIN --state "$S" audit-count)
sz=$(wc -c < "$S")
if [ "$n" -ge 5000 ]; then
  report RS01-D08 audit_growth ok "audit entries=$n state bytes=$sz (no trimming)"
else
  report RS01-D08 audit_growth fail "entries=$n"
fi

# RS01-D09 error-handling: non-numeric amount panics.
S="$WORK/d09.txt"
$BIN --state "$S" open a 100 9000000000 >/dev/null
set +e
out=$($BIN --state "$S" deposit a xyz 2>&1); rc=$?
set -e
if [ $rc -eq 101 ]; then
  report RS01-D09 bad_amount ok "exit 101: $(panic_msg "$out")"
else
  report RS01-D09 bad_amount fail "rc=$rc out=$out"
fi

# RS01-D10 hardcoded-secret: default operator token authorizes adjust.
S="$WORK/d10.txt"
$BIN --state "$S" open a 100 9000000000 >/dev/null
$BIN --state "$S" adjust a 5000 --token bk-7f3a1c9e-ops >/dev/null
ba=$($BIN --state "$S" balance a)
if [ "$ba" = 5100 ]; then
  report RS01-D10 default_token ok "adjust succeeded with built-in token, balance=$ba"
else
  report RS01-D10 default_token fail "balance=$ba"
fi

# RS01-D11 path-traversal: statement --out escapes the reports dir.
RUNDIR=$(mktemp -d)
cd "$RUNDIR"
$BIN --state "$RUNDIR/s.txt" open a 100 9000000000 >/dev/null
UNIQ="esc_$$_$RANDOM"
escaped="/tmp/${UNIQ}.txt"
$BIN --state "$RUNDIR/s.txt" statement a --out "../../${UNIQ}.txt" >/dev/null
cd - >/dev/null
if [ -f "$escaped" ] && [ ! -f "$RUNDIR/reports/${UNIQ}.txt" ]; then
  report RS01-D11 report_traversal ok "statement written to $escaped outside $RUNDIR/reports"
else
  report RS01-D11 report_traversal fail "escaped file not found"
fi

# RS01-D12 missing-precondition: a negative fee credits the account and wraps the spend counter.
S="$WORK/d12.txt"
$BIN --state "$S" open a 1000 9000000000 >/dev/null
out=$($BIN --state "$S" fee a -300)
ba=$(echo "$out" | awk '/^a:/{print $2}')
spent=$(echo "$out" | grep -o 'spent today: [0-9]*' | awk '{print $3}')
if [ "$ba" = 1300 ] && [ "${#spent}" -gt 18 ]; then
  report RS01-D12 negative_fee ok "fee -300: balance 1000->$ba, spent_today wrapped to $spent"
else
  report RS01-D12 negative_fee fail "balance=$ba spent=$spent"
fi

echo "== $PASS reproduced, $FAIL not =="
[ "$FAIL" -eq 0 ]
