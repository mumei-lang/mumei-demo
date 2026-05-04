---
name: testing-mumei-demo
description: Test mumei-demo scenarios end-to-end through make demo, CLI report output, Lean bridge regression checks, natural-language extraction, and Streamlit dashboard evidence.
---
# Testing mumei-demo

## Devin Secrets Needed

- `OPENAI_API_KEY`: required only for scenarios that call `mumei-agent` LLM extraction/generation, such as `nl_to_verified`.
- Local demos that do not call an external LLM can run without API keys, browser login, or external service credentials.

## Prerequisites

- A sibling checkout of `mumei` should exist at `../mumei` and provide a built binary at `../mumei/target/debug/mumei` or `../mumei/target/release/mumei`.
- Sibling checkouts of `mumei-agent` and `mumei-lean` should exist at `../mumei-agent` and `../mumei-lean`.
- RTGS Settlement validation requires `forge_tasks/vstd_settlement.json` in the default `../mumei-agent` checkout.
- RegTech Compliance validation requires `forge_tasks/vstd_regtech.json` in the default `../mumei-agent` checkout.
- Natural-language validation requires the companion `mumei-agent` checkout to support `python -m agent extract-spec` and `python -m agent generate` for forge task specs.
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
python3 -m json.tool scenarios/rtgs_settlement/scenario.json >/dev/null
python3 -m json.tool scenarios/regtech_compliance/scenario.json >/dev/null
python3 -m json.tool scenarios/nl_to_verified/scenario.json >/dev/null
python3 -m json.tool scenarios/nl_to_verified/expected/extracted_spec.json >/dev/null
```

## Primary Natural Language to Verified demo

Run with an `OPENAI_API_KEY` available in the environment:

```bash
OPENAI_API_KEY="$OPENAI_API_KEY" \
MUMEI_BIN=/home/ubuntu/repos/mumei/target/debug/mumei \
MUMEI_AGENT_PYTHON="$(command -v python3)" \
./scripts/run_scenario.sh nl_to_verified \
  --mumei-repo /home/ubuntu/repos/mumei \
  --mumei-agent-repo /home/ubuntu/repos/mumei-agent \
  --mumei-bin /home/ubuntu/repos/mumei/target/debug/mumei \
  --mumei-agent-python "$(command -v python3)"
```

Expected assertions:

- Command exits `0`.
- Output includes `Mumei Demo: Natural Language to Verified Mumei`.
- Output includes the three scenario narration steps for spec extraction, code generation, and final verification.
- Output includes `l2_agent/extract_spec: PASS`, `l2_agent/generate_code: PASS`, and `l1_z3/verify_code: PASS` in that order.
- Final success line is exactly `Result: Bug caught. Correct code proven. Zero human review.` with the trailing period.
- `reports/nl_to_verified/latest/result.json` has `overall_status == "PASS"` and layer keys `l2_agent` and `l1_z3`.
- Step statuses are `extract_spec == "PASS"`, `generate_code == "PASS"`, and `verify_code == "PASS"`.
- Proof density is `100% (3/3 atoms)`.
- `reports/nl_to_verified/latest/extracted_spec.json` is a valid forge task spec with `task_id`, `target_file` starting with `std/`, valid `mode`, and at least one atom with `name`, `inputs`, `return_type`, `requires`, and `ensures`.
- `reports/nl_to_verified/latest/generated.mm` exists and is non-empty.
- `reports/nl_to_verified/latest/verify_code.log` contains `Verification passed`.

If `extract_spec` passes but `generate_code` fails with unsupported Mumei syntax, verify that the companion `mumei-agent` checkout normalizes single-atom forge task specs to the single-atom generation path and that generation prompts warn against unsupported syntax such as `if ... then`, `.unwrap()`, or atom-level `else` blocks.

## Primary RegTech Compliance demo

Run:

```bash
MUMEI_BIN=/home/ubuntu/repos/mumei/target/debug/mumei \
MUMEI_AGENT_PYTHON="$(command -v python3)" \
make demo-regtech
```

Expected assertions:

- Command exits `0`.
- Output includes `Mumei Demo: RegTech Compliance Protocol`.
- Output includes `Step 1: LLM generates KYC compliance code...` and `Step 2: mumei verifies the code...`.
- Output includes `l1_z3/detect_bug: REJECTED`, `BUG DETECTED!`, `Match is not exhaustive`, and `Counter-example: CustomerType::PEP (tag=3)`.
- Output includes `l1_z3/verify_correct: PASS` and `All 5 atoms verified by Z3 (match exhaustiveness + forall)`.
- Output includes `l1_z3/verify_e2e: PASS` and `l2_agent/forge_dryrun: PASS`.
- Output does not include any `l3_lean` step because RegTech is intentionally a 2-layer Z3 + Agent scenario.
- Final success line is exactly `Result: Bug caught. Correct code proven. Zero human review.` with the trailing period.
- `reports/regtech_compliance/latest/result.json` has `overall_status == "PASS"` and exactly the `l1_z3` and `l2_agent` layer keys.
- RegTech step statuses are `detect_bug == "REJECTED"`, `verify_correct == "PASS"`, `verify_e2e == "PASS"`, and `forge_dryrun == "PASS"`.
- RegTech proof density is `100% (4/4 atoms)`.
- `reports/regtech_compliance/latest/detect_bug.log` contains `Match is not exhaustive` and `CustomerType::PEP (tag=3)`.
- `reports/regtech_compliance/latest/compliance.proof.json` exists and contains `classify_risk`, `get_transaction_limit`, `check_transaction`, `verify_all_transactions_compliant`, and `approval_level`.

## Primary RTGS Settlement demo

Run:

```bash
./scripts/run_scenario.sh rtgs_settlement \
  --mumei-repo /home/ubuntu/repos/mumei \
  --mumei-lean-repo /home/ubuntu/repos/mumei-lean \
  --mumei-agent-repo /home/ubuntu/repos/mumei-agent \
  --mumei-bin /home/ubuntu/repos/mumei/target/debug/mumei \
  --mumei-agent-python "$(command -v python3)"
```

Expected assertions:

- Command exits `0`.
- Output includes `Step 1: LLM generates RTGS settlement code...` and `BUG DETECTED!`.
- Output includes `InvalidPreState: 'settle' requires 'Validated'` and current state `Pending`.
- Output includes `All 4 atoms verified by Z3 (balance conservation)`.
- Output includes the visible certified headline prefix `CERTIFIED: no_settlement_without_validate` when Lake is available.
- Output does not include ownership-only strings like `PendingTransfer`, `All 5 atoms`, or `no_transfer_without_accept`.
- `reports/rtgs_settlement/latest/result.json` has `overall_status == "PASS"`, L1/L2/L3 layer status `PASS`, and proof density `100% (6/6 atoms)`.
- `reports/rtgs_settlement/latest/settlement.proof.json` contains exactly the RTGS atoms: `validate_transaction`, `execute_settlement`, `safe_settlement`, `full_settlement`.
- `reports/rtgs_settlement/latest/settlement.lean-cert.json` exists and is listed in `result.json.artifacts`; `lean_bridge.log` should mention writing the lean cert.

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

After running a scenario, render its latest report:

```bash
python3 dashboard/cli_report.py reports/regtech_compliance/latest/result.json
python3 dashboard/cli_report.py reports/rtgs_settlement/latest/result.json
python3 dashboard/cli_report.py reports/ownership_transfer/latest/result.json
python3 dashboard/cli_report.py reports/nl_to_verified/latest/result.json
```

Expected assertions:

- Output includes `BEFORE: LLM alone`, `AFTER: LLM + mumei`, `Audit Status:  TRUSTLESS`, and `Moment:        Proof failure → Bug found`.
- RegTech output includes `buggy_classify_risk misses PEP customer type in match`, `Non-exhaustive match catches the bug before deployment`, and `Proof Density: 100% (4/4 atoms)`.
- RegTech output must not contain `L3: Lean`.
- RTGS output includes the visible prefix `hostile_settlement skips validate and tries Pending → Settle` and `Proof Density: 100% (6/6 atoms)`.
- Ownership output includes `hostile_takeover skips accept and tries Idle → Transferred`.
- Natural-language output includes `Mumei Verification Report: Natural Language to Verified Mumei`, all three PASS steps, and `Proof Density: 100% (3/3 atoms)`.
- The CLI box is fixed-width, so long visible narrative may be truncated; verify full untruncated narrative strings in `result.json`.

## Lean bridge failure regression

Create a fake failing Lake executable and run the ownership scenario with it first in `PATH`:

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

After generating a successful latest report, start the dashboard:

```bash
streamlit run dashboard/app.py
```

Open the local Streamlit page in the browser and verify:

- Sidebar scenario can be changed between `ownership_transfer`, `rtgs_settlement`, `regtech_compliance`, and `nl_to_verified`.
- Natural-language dashboard evidence should show `l2_agent=PASS`, `l1_z3=PASS`, and Proof Density `100%` with `3/3 atoms`.
- Expanding the natural-language steps should show `PASS: Agent Spec Extraction`, `PASS: Agent Code Generation`, and `PASS: Z3 Generated Code Verification`; the Z3 log should contain `Verification passed`.
- RegTech dashboard evidence should show `l1_z3=PASS`, `l2_agent=PASS`, no `l3_lean` metric, and Proof Density `100%` with `4/4 atoms`.
- RTGS/ownership dashboard evidence should show expected L1/L2/L3 metrics; proof density is usually `100%` and `6/6 atoms` for RTGS in a Lake-available environment.
- Expanding the RegTech rejected step shows log text containing `Match is not exhaustive` and `CustomerType::PEP (tag=3)`.
- Expanding the ownership rejected step shows log text containing `InvalidPreState`.
- Expanding proof certificate artifacts shows generated JSON. RegTech should show `compliance.proof.json`; RTGS should show both `settlement.proof.json` and `settlement.lean-cert.json`.

If recording dashboard evidence, maximize the browser first where possible and annotate scenario selection, layer metrics, proof density, expanded step logs, and verification/proof evidence. Save and attach the processed mp4 in the final testing report.
