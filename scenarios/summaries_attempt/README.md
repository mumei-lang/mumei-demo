# Declared summary attempt routes: the produce routes inside the C11 lifecycle

Run the optional scenario with a sibling `mumei-agent` checkout:

```bash
make demo-summaries-attempt
python3 dashboard/cli_report.py reports/summaries_attempt/latest/result.json
```

This scenario needs **no provisioned toolchain and no fixture mode**: the
TypeScript, Rust and Solidity analyzers run in-process on tree-sitter, so
every step executes the real route command deterministically. The target
sits in `OPTIONAL_SCENARIOS` because it needs a sibling `mumei-agent`
checkout (`MUMEI_AGENT_REPO`).

## The attempt lifecycle

| Step | What it does | What it does not do |
| --- | --- | --- |
| `ts_attempt` | Runs `python -m agent ts-summaries-attempt` on `scenarios/ts_summaries/demo_counter.ts` and writes `ts_attempt.json` (`mumei.ts-summaries-attempt-report/v1`): the attempt sequence keyed to the request fingerprint, the normalized run, and a `candidate` descriptor when the exited run's captured stdout was selected | Verify, prove or accept anything — the report is canonical lineage, not an accepted manifest |
| `rust_attempt` | Same for `rust-summaries-attempt` on `scenarios/rust_summaries/demo_counter.rs` | Change the selection rule — an `exited` run selects only when every declared input byte is unchanged after the run |
| `sol_attempt` | Same for `sol-summaries-attempt` on `scenarios/sol_summaries/demo_counter.sol` | Exempt drift — a source modified mid-run selects nothing |
| `timeout_refusal` | Runs `ts-summaries-attempt --attempt-timeout 1`; the report exits 0 with `outcome` `timed_out` and **no** `candidate` key | Fail the step — a refused attempt is recorded lineage, not a crash |

The report is the canonical lineage: the sequence binds the request
fingerprint to the declared source bytes, `normalized` records the terminal
observation, and `candidate` binds only the selected output's fingerprint.
Acceptance stays with the `*-summaries-accept` routes.
