# Negative Controls: Dosage Contract

This scenario compares two contracts over the same `next_dose` implementation.
The weak postcondition permits a surviving mutation even though the original
body verifies; the body-specific postcondition makes every tested mutant
discriminating. The weak case is also rejected by Phase 1i and by the opt-in
Claim Book discrimination gate.

The project is copied into the run output directory before verification and
control checks. The source files are never modified.

## Run

```bash
make demo-negative-controls
```

The report records per-step negative-control results and totals in
`result.json` and `harness_state.json`, and renders them in a Negative Controls
section in `report.md`. A surviving mutant is evidence for human review, not a
substitute for semantic judgment.
