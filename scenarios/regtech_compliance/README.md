# RegTech Compliance Protocol

> Mumei detects missing customer categories in LLM-generated KYC/AML compliance code.

## BEFORE: LLM alone

The user asks an LLM to implement KYC (Know Your Customer) and AML compliance
checking. The generated code classifies customers by risk level, but
`buggy_classify_risk` misses the `PEP` (Politically Exposed Person) category — a
critical regulatory oversight that could allow high-risk customers to bypass
compliance checks.

## AFTER: LLM + mumei

`mumei verify scenarios/regtech_compliance/buggy_code.mm` rejects the code:

    Match is not exhaustive: the following value is not covered by any arm:
      Counter-example: CustomerType::PEP (tag=3) -- missing from match arms

The bug is caught before deployment. No PEP customer can bypass compliance.

## CERTIFIED: Z3 proof

`correct_code.mm` imports the verified `std/compliance.mm` atoms and exercises
them through demo wrappers:
- all 4 customer types (Individual, Corporate, Government, PEP) are classified
- the `forall` quantifier ensures all transactions comply with risk-based limits
- guard-based match determines approval levels by amount

Z3 verifies the imported compliance workflow, including match exhaustiveness and
forall limit compliance.

Note: This is a 2-layer demo (Z3 + Agent). No Lean proof is needed because Z3
fully verifies match exhaustiveness and forall quantifiers for this scenario.

## Prerequisites

`correct_code.mm` imports `std/compliance.mm` from the sibling `mumei` repo:

    import "std/compliance" as compliance;

The scenario runner resolves this via `MUMEI_STD_PATH`, which defaults to
`{mumei_repo}/std` (see `scripts/run_scenario.sh`). The sibling `mumei`
checkout must therefore contain `std/compliance.mm` with the atoms
`classify_risk`, `get_transaction_limit`, `check_transaction`,
`verify_all_transactions_compliant`, and `approval_level`. Without this file
the `verify_correct` step will fail with an import-resolution error.

## Run

    make demo-regtech

From a checkout with sibling `mumei`, `mumei-agent`, and `mumei-lean` repos, run
all four scenarios in sequence:

    make demo-all

For CI-equivalent validation with dashboard summaries:

    make demo-ci

`demo-all` and `demo-ci` run `ownership_transfer`, `rtgs_settlement`,
`regtech_compliance`, and `nl_to_verified` in order. `demo-ci` returns a
non-zero exit code if any scenario does not produce `overall_status: PASS`.

## Expected output

`make demo-regtech` should show the two-layer RegTech story:

    Step 1: LLM generates KYC/AML compliance code...
    Step 2: mumei verify checks match exhaustiveness...
    l1_z3/detect_bug: REJECTED
    BUG DETECTED! Match exhaustiveness violation
    Match is not exhaustive:
    Counter-example: CustomerType::PEP (tag=3)
    l1_z3/verify_negative_suite: REJECTED
    l1_z3/verify_correct: PASS
    All atoms verified
    forall quantifier proves limit compliance
    l1_z3/verify_e2e: PASS
    l2_agent/forge_dryrun: PASS
    Proof Density: 100% (5/5 atoms or layer steps verified)

The bug-detection expectation is recorded in `expected/verify_buggy.json` and
the corrected implementation expectation is recorded in
`expected/verify_correct.json`. The scenario runner also keeps lightweight text
patterns in `expected/detect_bug.txt` and `expected/verify_correct.txt`.

The scenario report is written to `reports/regtech_compliance/latest/result.json`
with `overall_status: PASS`, `proof_density: 100%`, and the RegTech scenario
included in aggregated dashboard summaries from `scripts/generate_report.py`.

## Dashboard recording

After running the scenario, open the Streamlit dashboard and select
`regtech_compliance`, or watch the recorded walkthrough:

    docs/assets/regtech-compliance-dashboard-demo.mp4

The recording shows the 2-layer report, the rejected non-exhaustive match with
`CustomerType::PEP (tag=3)`, proof density `100% (5/5 atoms)`, and the
`compliance.proof.json` certificate.

Expected story:
1. LLM generates KYC/AML compliance code with a missing PEP match arm.
2. `mumei verify` detects the match exhaustiveness violation.
3. The negative test suite confirms the missing PEP arm remains covered.
4. The corrected implementation imports `std/compliance.mm` and verifies the
   forall-based transaction-limit proof.
