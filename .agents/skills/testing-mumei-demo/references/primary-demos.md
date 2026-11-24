# Primary scenario demos (RegTech, NL to Verified, RTGS, ownership)

Read this when running one of the primary scenarios individually and you need its exact command and expected output/`result.json` assertions.

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
MUMEI_BIN=/home/ubuntu/repos/mumei/target/debug/mumei make demo-ownership
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
