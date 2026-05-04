# RegTech Compliance Protocol

> Mumei detects missing customer categories in LLM-generated KYC compliance code.

## BEFORE: LLM alone

The user asks an LLM to implement KYC (Know Your Customer) compliance checking.
The generated code classifies customers by risk level, but `buggy_classify_risk`
misses the `PEP` (Politically Exposed Person) category — a critical regulatory
oversight that could allow high-risk customers to bypass compliance checks.

## AFTER: LLM + mumei

`mumei verify scenarios/regtech_compliance/buggy_code.mm` rejects the code:

    Match is not exhaustive: the following value is not covered by any arm:
      Counter-example: CustomerType::PEP (tag=3) -- missing from match arms

The bug is caught before deployment. No PEP customer can bypass compliance.

## CERTIFIED: Z3 proof

`correct_code.mm` implements the complete protocol:
- All 4 customer types (Individual, Corporate, Government, PEP) are classified
- `forall` quantifier ensures all transactions comply with risk-based limits
- Guard-based match determines approval levels by amount

Z3 verifies all atoms including match exhaustiveness and forall compliance.

Note: This is a 2-layer demo (Z3 + Agent). No Lean proof is needed because
Z3 alone can fully verify match exhaustiveness and forall quantifiers.

## Run

    make demo-regtech

## Dashboard recording

After running the scenario, open the Streamlit dashboard and select
`regtech_compliance`, or watch the recorded walkthrough:

    docs/assets/regtech-compliance-dashboard-demo.mp4

The recording shows the 2-layer report, the rejected non-exhaustive match with
`CustomerType::PEP (tag=3)`, proof density `100% (4/4 atoms)`, and the
`compliance.proof.json` certificate.

Expected story:
1. LLM generates KYC compliance code.
2. mumei detects the non-exhaustive match (PEP missing).
3. The corrected implementation verifies (all customer types covered + forall).
