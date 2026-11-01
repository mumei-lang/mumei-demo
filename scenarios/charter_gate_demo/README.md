# Charter Gate: Reviewed Dosage Contract

This scenario demonstrates how mumei keeps an implementation aligned with a
reviewed contract. The charter gate rejects a repair that weakens a
postcondition, one that narrows the accepted inputs, and one whose proof relies
on a trusted shortcut below the required Seal Grade. It also reports when the
charter text has changed since its lock was written.

The scenario copies its project into the run's output directory before writing
the charter lock or running checks. Its source project remains unchanged. The
source project also keeps a committed `charter.lock`, which the `mumei-gate.yml`
CI workflow checks in place; regenerate it with `mumei charter lock` after
editing `specs/dosage.charter.mm`.

## Run

```bash
make demo-charter
```

The `result.json` report records each charter check under `charter_gate`,
including the gate and lock statuses and per-atom findings. The Markdown report
renders those entries in a Charter Gate section.

The accepted candidate also runs `mumei claims --require-grade G4
--require-complete`: grade and dependency completeness are independent gates.
Reusing its certificate with the weakened candidate must fail with drifted
freshness. The rejected Claim Book remains in `claims_stale/claimbook.json`,
including its existing `next_steps`; an input error is not a successful rejection.

## Reproduce the complete regression example

```bash
CI_FIXTURE_MODE=1 make demo-charter-regression
```

This runs the existing Charter, Negative Controls, and Test Observation
scenarios, then checks eleven isolated artifact snapshots against the freshly
validated Charter report. It needs the built `mumei` binary and the usual
`mumei-agent` dependencies, but no LLM credentials, paid API, DB, or browser.
`MUMEI_BIN` and `MUMEI_AGENT_PYTHON` can select explicit executables.

| Evidence | Expected result | Where to inspect |
|---|---|---|
| Correct bounded dosage repair | Fresh G4, complete dependencies, Charter acceptance | `reports/charter_gate_demo/latest/` |
| Weakened/narrowed/low-grade/unpinned candidate | Rejected for the corresponding Charter reason | Same report, step logs, and `charter_gate` entries |
| Certificate reused for a changed candidate | Rejected with drifted freshness; diagnostics saved | `claims_stale/claimbook.json` in the same report directory |
| Weak contract that still verifies | Surviving mutant; discrimination gate rejects | `reports/negative_controls_demo/latest/` |
| Stronger contract for the same increment body | Discriminating for the tested mutants | Same controls report |
| Wrong/aligned late-fee specifications | Contradictions / consistency with harvested tests | `reports/test_observation_demo/latest/` |
| Missing/replaced artifacts, stale claim, direct/transitive missing dependencies | Reader marks synthetic evidence incomplete | `reports/charter_regressions/run-*/summary.json` and per-case `reader_result.json` |

The three models are complementary examples, not one combined application
proof. Controls and harvested test observations are not run on the bounded
`clamp_dose` contract, and must not be attributed to it. In particular, passing
the Charter does not mean all meaningful wrong implementations are excluded.

The artifact cases are **synthetic reader regressions**, not new solver runs:
each starts from an isolated copy, relocates local paths, and validates the
copy before making one change. Stale-claim and dependency cases deliberately
change Claim Book metadata and recapture byte identities, so the reader must
reject the actual metadata, not merely an old hash. Other cases retain the
original identities to exercise substitution detection. Inputs remain intact.

The ordinary scenario still reports success for expected rejections. The
synthetic summary separately records the expected and actual reader statuses;
a test passes only when these agree. A pre-existing failed or incomplete
report cannot serve as the baseline. Failed cases keep their diagnostics.

## Review boundary and CI

The reviewed baseline is `project/specs/dosage.charter.mm`, `project/charter.lock`,
`project/mumei.toml`, and the scenario's `evidence_requirements`. Candidate
checks run on output-directory copies, never through a self-repair command
that rewrites these source inputs. Changes to this baseline need review, not
an automatically regenerated approval hash.

Integration CI publishes `charter-baseline-review` with a Git diff and current
snapshot. On PRs the comparison is against the base commit; a manual run
without a base explicitly reports that no comparison was requested. A green
baseline-review job means the review material was produced, **not approved**.
The separate reusable Charter gate verifies the committed lock in place and
requires both G4 and complete dependencies. Test diagnostics and real scenario
artifacts are uploaded even on failure.

`CI_FIXTURE_MODE=1` avoids live LLM generation; it does not replace the Charter
verifier with a fake solver. Unit tests and synthetic artifact mutations test
the report contract. The scenario steps run the real binary. Neither result
establishes clinical suitability, production-code correspondence, external
service safety, or deployment safety. Local hashes are correspondence aids,
not authenticity or semantic-equivalence proofs.
