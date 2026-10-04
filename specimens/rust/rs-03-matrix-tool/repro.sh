#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

cargo build --release 2>/dev/null
BIN="$PWD/target/release/matrix-tool"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK" /tmp/matrix_tool_cache.txt /tmp/rs03_victim_$$*' EXIT

PASS=0; FAIL=0
report() {
  if [ "$3" = ok ]; then
    echo "[REPRODUCED] $1 $2: $4"; PASS=$((PASS+1))
  else
    echo "[NOT REPRODUCED] $1 $2: $4"; FAIL=$((FAIL+1))
  fi
}

# RS03-D01 out-of-bounds / wrong index: at() uses rows as the stride.
printf '1 2 3\n4 5 6\n' > "$WORK/m23.txt"
out=$($BIN --input "$WORK/m23.txt" --op report --label x --out "$WORK/s.txt")
expected=$(python3 -c 'm=[[1,2,3],[4,5,6]];print(" ".join(f"col{c}={sum(r[c] for r in m)}" for c in range(3)))')
actual=$(echo "$out" | grep -o 'col[0-9]*=[0-9-]*' | tr '\n' ' ' | sed 's/ $//')
if [ "$actual" != "$expected" ]; then
  report RS03-D01 swapped_stride ok "column totals '$actual' != correct '$expected'"
else
  report RS03-D01 swapped_stride fail "actual=$actual"
fi

# RS03-D02 division-by-zero: mean on an empty file.
: > "$WORK/empty.txt"
set +e
out=$($BIN --input "$WORK/empty.txt" --op mean 2>&1); rc=$?
set -e
if [ $rc -eq 101 ]; then
  report RS03-D02 empty_mean ok "exit 101: $(echo "$out" | grep -o 'divide.*zero\|attempt to.*' | head -1)"
else
  report RS03-D02 empty_mean fail "rc=$rc out=$out"
fi

# RS03-D03 division-by-zero: singular matrix invert yields inf.
printf '1 2\n2 4\n' > "$WORK/singular.txt"
out=$($BIN --input "$WORK/singular.txt" --op invert)
if echo "$out" | grep -qi 'inf\|NaN'; then
  report RS03-D03 singular_invert ok "invert of singular matrix printed '$out'"
else
  report RS03-D03 singular_invert fail "out=$out"
fi

# RS03-D04 integer-overflow: i32 scale wraps negative (release profile).
printf '1500000000\n' > "$WORK/big.txt"
out=$($BIN --input "$WORK/big.txt" --op scale --factor 2 | tail -1)
if [ "$out" -lt 0 ]; then
  report RS03-D04 scale_wrap ok "1500000000 * 2 wrapped to $out (release profile)"
else
  report RS03-D04 scale_wrap fail "out=$out"
fi

# RS03-D05 error-handling: non-numeric cell panics.
printf '1 2\n3 x\n' > "$WORK/badcell.txt"
set +e
out=$($BIN --input "$WORK/badcell.txt" --op mean 2>&1); rc=$?
set -e
if [ $rc -eq 101 ]; then
  report RS03-D05 bad_cell ok "exit 101: $(echo "$out" | grep -o 'panicked.*' | head -1)"
else
  report RS03-D05 bad_cell fail "rc=$rc out=$out"
fi

# RS03-D06 design/logic: ragged rows silently truncated by first-row width.
printf '1 2\n3 4 5 6\n' > "$WORK/ragged.txt"
out=$($BIN --input "$WORK/ragged.txt" --op scale --factor 1)
if echo "$out" | grep -q '2 x 2' && ! echo "$out" | grep -q '5'; then
  report RS03-D06 ragged_rows ok "cells 5 and 6 silently dropped: $(echo "$out" | tr '\n' '|')"
else
  report RS03-D06 ragged_rows fail "out=$out"
fi

# RS03-D07 logic-error: u32 factor > i32::MAX becomes negative via `as i32`.
printf '7\n' > "$WORK/seven.txt"
out=$($BIN --input "$WORK/seven.txt" --op scale --factor 3000000000 | tail -1)
if [ "$out" -lt 0 ]; then
  report RS03-D07 factor_sign ok "factor 3000000000 applied as negative: 7 -> $out"
else
  report RS03-D07 factor_sign fail "out=$out"
fi

# RS03-D08 off-by-one: transpose drops the last column.
out=$($BIN --input "$WORK/m23.txt" --op transpose)
dims=$(echo "$out" | head -1)
if [ "$dims" = "2 x 2" ]; then
  report RS03-D08 transpose_drop ok "transpose of 2x3 printed $dims, last column lost"
else
  report RS03-D08 transpose_drop fail "dims=$dims"
fi

# RS03-D09 command-injection: label is interpolated into a shell command.
MARK="/tmp/rs03_victim_$$_mark"
$BIN --input "$WORK/m23.txt" --op report --label "x'; touch $MARK; echo '" --out "$WORK/sum.txt" >/dev/null
if [ -f "$MARK" ]; then
  report RS03-D09 label_injection ok "label ran a command: $MARK exists"
else
  report RS03-D09 label_injection fail "marker not created"
fi

# RS03-D10 weak-crypto: additive checksum collides on permuted input.
printf '1 2\n3 4\n' > "$WORK/ca.txt"
printf '2 1\n4 3\n' > "$WORK/cb.txt"
ca=$($BIN --input "$WORK/ca.txt" --op checksum | awk '{print $2}')
cb=$($BIN --input "$WORK/cb.txt" --op checksum | awk '{print $2}')
if [ "$ca" = "$cb" ] && ! cmp -s "$WORK/ca.txt" "$WORK/cb.txt"; then
  report RS03-D10 checksum_collision ok "different files share checksum $ca"
else
  report RS03-D10 checksum_collision fail "ca=$ca cb=$cb"
fi

# RS03-D11 toctou: predictable cache path follows a pre-placed symlink.
VICTIM="/tmp/rs03_victim_$$_victim.txt"
echo "keep me" > "$VICTIM"
rm -f /tmp/matrix_tool_cache.txt
ln -s "$VICTIM" /tmp/matrix_tool_cache.txt
$BIN --input "$WORK/m23.txt" --op mean >/dev/null
if grep -q 'keep me' "$VICTIM" 2>/dev/null; then
  report RS03-D11 cache_symlink fail "victim intact"
elif grep -q 'mean' "$VICTIM"; then
  report RS03-D11 cache_symlink ok "victim file overwritten through symlink: $(cat "$VICTIM")"
else
  report RS03-D11 cache_symlink fail "victim=$(cat "$VICTIM")"
fi
rm -f /tmp/matrix_tool_cache.txt

echo "== $PASS reproduced, $FAIL not =="
[ "$FAIL" -eq 0 ]
