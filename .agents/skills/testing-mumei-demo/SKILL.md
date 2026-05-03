---
name: testing-mumei-demo
description: Test mumei-demo scenarios end-to-end through make demo, CLI report output, Lean bridge regression checks, and Streamlit dashboard evidence.
---
# Testing mumei-demo

## Prerequisites

- A sibling checkout of `mumei` should exist at `../mumei` and provide a built binary at `../mumei/target/debug/mumei` or `../mumei/target/release/mumei`.
- Sibling checkouts of `mumei-agent` and `mumei-lean` should exist at `../mumei-agent` and `../mumei-lean`.
- No API keys or browser login are required for local demo validation.
- If the dashboard needs dependencies, install them with:

```bash
python -m pip install -r dashboard/requirements.txt
```

## Static checks

Run from the repo root:

```bash
python3 -m compileall -q scripts dashboard
bash -n scripts/setup_repos.sh
bash -n scripts/run_scenario.sh
bash -n scripts/run_all.sh
python3 -m json.tool scenarios/ownership_transfer/scenario.json >/dev/null
python3 -m json.tool scenarios/_template/scenario.json >/dev/null
```

## Primary ownership transfer demo

Run:

```bash
MUMEI_BIN=/home/ubuntu/repos/mumei/target/debug/mumei make demo
```

Expected assertions:

- Command exits `0`.
- Output includes Step 1 through Step 4 narration.
- Output includes `BUG DETECTED!`.
- Output includes `InvalidPreState: 'accept' requires 'PendingTransfer'`.
- Output includes `All 5 atoms verified by Z3`.
- Output includes `CERTIFIED: no_transfer_without_accept` when Lake is available, or an explicit Lake-toolchain skip when unavailable.
- Final success line is exactly `Result: Bug caught. Correct code proven. Zero human review.` with the trailing period.
- `reports/ownership_transfer/latest/result.json` has `overall_status` equal to `PASS`.
- `detect_bug.status` is `REJECTED`, `verify_correct.status` is `PASS`, and `artifacts` contains `ownership.proof.json`.
- `reports/ownership_transfer/latest/detect_bug.log` contains `InvalidPreState`.

## CLI report

After `make demo`, run:

```bash
python3 dashboard/cli_report.py reports/ownership_transfer/latest/result.json
```

Expected assertions:

- Output includes `BEFORE: LLM alone`.
- Output includes `hostile_takeover skips accept and tries Idle → Transferred`.
- Output includes `AFTER: LLM + mumei`.
- Output includes `InvalidPreState catches the bug before deployment`.
- Output includes `Audit Status:  TRUSTLESS`.
- Output includes `Moment:        Proof failure → Bug found`.

## Lean bridge failure regression

Create a fake failing Lake executable and run the scenario with it first in `PATH`:

```bash
mkdir -p /home/ubuntu/fake-lake
printf '#!/usr/bin/env bash\necho fake lake failure >&2\nexit 42\n' > /home/ubuntu/fake-lake/lake
chmod +x /home/ubuntu/fake-lake/lake
PATH=/home/ubuntu/fake-lake:$PATH MUMEI_BIN=/home/ubuntu/repos/mumei/target/debug/mumei make demo
```

Expected assertions:

- Command exits non-zero.
- Output includes `l3_lean/lean_build: FAIL`.
- Output includes `l3_lean/lean_bridge: SKIPPED`.
- Output includes `Lean bridge skipped: proof build failed`.
- Output includes `Result: Demo failed. Inspect result.json for details.`.
- After `l3_lean/lean_bridge: SKIPPED`, output must not include `CERTIFIED: no_transfer_without_accept`.

## Dashboard recording flow

After restoring a successful latest report with `make demo`, start the dashboard:

```bash
streamlit run dashboard/app.py
```

Open the local Streamlit page in the browser and verify:

- Sidebar scenario is `ownership_transfer`.
- Top metrics show `l1_z3=PASS`, `l2_agent=PASS`, and `l3_lean=PASS` when Lake is available.
- Proof Density is `100%` and `6/6 atoms` in the normal Lake-available environment.
- Expanding `REJECTED: Z3 Bug Detection: hostile_takeover` shows log text containing `InvalidPreState`.
- Expanding `ownership.proof.json` shows generated proof certificate data.
