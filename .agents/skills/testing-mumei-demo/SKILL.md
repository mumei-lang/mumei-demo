---
name: testing-mumei-demo
description: Test mumei-demo scenarios end-to-end through make demo, CLI report output, Lean bridge regression checks, natural-language extraction, and Streamlit dashboard evidence.
---
# Testing mumei-demo

## Devin Secrets Needed

- `OPENAI_API_KEY`: required only for live scenarios that call `mumei-agent` LLM extraction/generation, such as direct non-fixture `nl_to_verified` runs.
- Local demos and `make demo-ci` can run without API keys, browser login, or external service credentials because CI fixture mode is enabled by the target.

## Prerequisites

- A sibling checkout of `mumei` should exist at `../mumei` and provide a built binary at `../mumei/target/debug/mumei` or `../mumei/target/release/mumei`.
- Sibling checkouts of `mumei-agent` and `mumei-lean` should exist at `../mumei-agent` and `../mumei-lean`.
- RTGS Settlement validation requires `forge_tasks/vstd_settlement.json` in the default `../mumei-agent` checkout.
- RegTech Compliance validation requires `forge_tasks/vstd_regtech.json` in the default `../mumei-agent` checkout.
- RegTech Compliance validation also requires `std/compliance.mm` in the sibling `../mumei` checkout (resolved via `MUMEI_STD_PATH`, which defaults to `{mumei_repo}/std`). `correct_code.mm` imports this module via `import "std/compliance" as compliance;` and the verify step will fail if the file is missing.
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
python3 -m json.tool scenarios/rtgs_settlement/scenario.json >/dev/null
python3 -m json.tool scenarios/regtech_compliance/scenario.json >/dev/null
python3 -m json.tool scenarios/nl_to_verified/scenario.json >/dev/null
python3 -m json.tool scenarios/smart_contract_audit/scenario.json >/dev/null
python3 -m json.tool scenarios/medical_device/scenario.json >/dev/null
python3 -m json.tool scenarios/aviation_control/scenario.json >/dev/null
python3 -m json.tool scenarios/nl_to_verified/expected/extracted_spec.json >/dev/null
```

## Full CI-equivalent validation (`make demo-ci`)

This is the fastest way to validate the complete pipeline without live LLM credentials. It runs all seven scenarios with fixture mode enabled by the Makefile target, then generates a cross-scenario summary.

```bash
# Clean stale reports first
rm -rf reports/ dashboard/summary.md dashboard/highlights.md

# Fixture mode is enabled internally by make demo-ci
make demo-ci
```

Expected assertions:

- Command exits `0`.
- `reports/{scenario}/latest/result.json` exists for all seven scenarios: `ownership_transfer`, `rtgs_settlement`, `regtech_compliance`, `nl_to_verified`, `smart_contract_audit`, `medical_device`, and `aviation_control`.
- Each `result.json` has `overall_status == "PASS"`.
- Each `result.json` has `proof_density.percentage == 100` with these densities: ownership_transfer 6/6, rtgs_settlement 6/6, regtech_compliance 5/5, nl_to_verified 3/3, smart_contract_audit 4/4, medical_device 4/4, aviation_control 3/3.
- `dashboard/summary.md` exists with a markdown table containing all seven scenario rows.
- `dashboard/summary.md` has no "Missing results" section.

### Cross-scenario summary validation

After `demo-ci`, verify the generated summary:

```bash
cat dashboard/summary.md
```

Expected table rows:

```text
| `ownership_transfer` | PASS | 6 | 6 | 100% |
| `rtgs_settlement` | PASS | 6 | 6 | 100% |
| `regtech_compliance` | PASS | 5 | 5 | 100% |
| `nl_to_verified` | PASS | 3 | 3 | 100% |
| `smart_contract_audit` | PASS | 4 | 4 | 100% |
| `medical_device` | PASS | 4 | 4 | 100% |
| `aviation_control` | PASS | 3 | 3 | 100% |
```

You can also generate the summary standalone:

```bash
python3 scripts/generate_report.py --summary --require-all
```

### Negative test for `demo-ci` non-zero exit

To verify that `demo-ci` returns non-zero on failure, set `MUMEI_BIN` to a non-existent path:

```bash
rm -rf reports/ dashboard/summary.md
MUMEI_BIN=/nonexistent/mumei make demo-ci; echo "EXIT_CODE=$?"
```

Expected: exit code is non-zero. All seven scenarios still run with continue-on-failure behavior and `dashboard/summary.md` is still generated.

Tip: Corrupting `.mm` source files may not trigger a failure because `mumei verify` can report "0 item(s) verified" with exit code 0 when the file contains no atoms. Use a missing binary or missing scenario config to force a definitive failure instead.

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
- Output includes `Step 1: LLM generates KYC/AML compliance code...` and `Step 2: mumei verify checks match exhaustiveness...`.
- Output includes `l1_z3/detect_bug: REJECTED`, `BUG DETECTED! Match exhaustiveness violation`, `Match is not exhaustive`, and `Counter-example: CustomerType::PEP (tag=3)`.
- Output includes `l1_z3/verify_negative_suite: REJECTED` to confirm the negative test suite still catches a missing PEP match arm.
- Output includes `l1_z3/verify_correct: PASS`, `All atoms verified`, and `forall quantifier proves limit compliance`.
- Output includes `l1_z3/verify_e2e: PASS` and `l2_agent/forge_dryrun: PASS`.
- Output does not include any `l3_lean` step because RegTech is intentionally a 2-layer Z3 + Agent scenario.
- Final success line is exactly `Result: Bug caught. Correct code proven. Zero human review.` with the trailing period.
- `reports/regtech_compliance/latest/result.json` has `overall_status == "PASS"` and exactly the `l1_z3` and `l2_agent` layer keys.
- RegTech step statuses are `detect_bug == "REJECTED"`, `verify_negative_suite == "REJECTED"`, `verify_correct == "PASS"`, `verify_e2e == "PASS"`, and `forge_dryrun == "PASS"`.
- RegTech proof density is `100% (5/5 atoms or layer steps verified)`.
- `reports/regtech_compliance/latest/detect_bug.log` contains `Match is not exhaustive` and `CustomerType::PEP (tag=3)`.
- `reports/regtech_compliance/latest/compliance.proof.json` exists and contains the demo wrapper atoms `demo_classify_all_customer_types`, `demo_get_transaction_limit`, `demo_check_transaction`, `demo_verify_all_transactions_compliant`, and `demo_approval_level`, which delegate to the imported `std/compliance.mm` atoms.

## Primary Natural Language to Verified demo

Run with an `OPENAI_API_KEY` available in the environment when not using fixture mode:

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
- Output includes `l2_agent/extract_spec: PASS`, `l2_agent/generate_code: PASS`, and `l1_z3/verify_code: PASS` in that order.
- Final success line is exactly `Result: Bug caught. Correct code proven. Zero human review.` with the trailing period.
- `reports/nl_to_verified/latest/result.json` has `overall_status == "PASS"` and layer keys `l2_agent` and `l1_z3`.
- Proof density is `100% (3/3 atoms)`.

### NL fixture mode verification

When `CI_FIXTURE_MODE=1` is set, `nl_to_verified` loads `scenarios/nl_to_verified/expected/extracted_spec.json` instead of calling the live LLM. To verify fixture artifacts:

```bash
test -f reports/nl_to_verified/latest/extracted_spec.json && echo "EXISTS" || echo "MISSING"
test -f reports/nl_to_verified/latest/generated.mm && echo "EXISTS" || echo "MISSING"
rg "Verification passed" reports/nl_to_verified/latest/verify_code.log
```

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
- Output includes `All 4 atoms verified by Z3`.
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
- RegTech output includes `buggy_classify_risk misses PEP customer type in match`, `Non-exhaustive match catches the bug before deployment`, `Z3 Negative Test Suite`, and `Proof Density: 100% (5/5 atoms or layer steps verified)`.
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

- Sidebar scenario can be changed between `ownership_transfer`, `rtgs_settlement`, `regtech_compliance`, `nl_to_verified`, `smart_contract_audit`, `medical_device`, and `aviation_control`.
- Natural-language dashboard evidence should show `l2_agent=PASS`, `l1_z3=PASS`, and Proof Density `100%` with `3/3 atoms`.
- RegTech dashboard evidence should show `l1_z3=PASS`, `l2_agent=PASS`, no `l3_lean` metric, and Proof Density `100%` with `5/5 atoms or layer steps verified`.
- RTGS/ownership dashboard evidence should show expected L1/L2/L3 metrics; proof density is usually `100%` and `6/6 atoms` for RTGS in a Lake-available environment.
- Expanding the RegTech rejected steps shows log text containing `Match is not exhaustive` and `CustomerType::PEP (tag=3)`.
- Expanding the ownership rejected step shows log text containing `InvalidPreState`.
- Expanding proof certificate artifacts shows generated JSON. RegTech should show `compliance.proof.json`; RTGS should show both `settlement.proof.json` and `settlement.lean-cert.json`.

If recording dashboard evidence, maximize the browser first where possible and annotate scenario selection, layer metrics, proof density, expanded step logs, and verification/proof evidence. Save and attach the processed mp4 in the final testing report.

## General tips

- Lean builds are slow on first run (~160s) but cached afterward (~0.6s). If you see long Lean build times, that is expected for the first invocation.
- The first run of `make demo-ci` may take 3-5 minutes due to Lean compilation. Subsequent runs are much faster.
- All testing is shell-only CLI output unless testing the Streamlit dashboard; no browser recording is needed for CLI-only validation.
- When running `demo-ci`, always clean `reports/` and `dashboard/summary.md` first to avoid stale data from previous runs.
- If running `./scripts/run_scenario.sh nl_to_verified` directly without `CI_FIXTURE_MODE=1`, expect a live LLM call and require `OPENAI_API_KEY`.
