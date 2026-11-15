# Solidity interprocedural summary manifests: a declared-route example

Run the optional scenario with a sibling `mumei-agent` checkout:

```bash
make demo-sol-summaries
python3 dashboard/cli_report.py reports/sol_summaries/latest/result.json
```

Like `ts_summaries`, this scenario needs **no provisioned toolchain and no
fixture mode**: the Solidity analyzer runs in-process on tree-sitter, so
every step executes the real route command deterministically. This target is
deliberately outside the default `make demo` / `make demo-ci` sequence — like
`go_summaries` it sits in `OPTIONAL_SCENARIOS` because it needs a sibling
`mumei-agent` checkout (`MUMEI_AGENT_REPO`).

## The emit -> check -> accept loop

| Step | What it does | What it does not do |
| --- | --- | --- |
| `emit_manifest` | Runs `python -m agent sol-summaries` on `demo_counter.sol` and writes `manifest.json` (`mumei.sol-scalar-parameter-deps/v1`): per-function parameters, `return_dependencies`, intra-contract `calls` and `effects`, keyed by the unit's `context_key` | Verify, prove or certify anything — the manifest is declared data |
| `check_manifest` | Re-derives summaries via `sol-summaries-check` and emits `mumei.sol-summary-check/v1`: `context_match` plus a `reusable`/`stale`/`missing` partition of the declared functions | Authorize reuse — the host chooses what to trust |
| `accept_summary` | Runs `sol-summaries-accept --function add` and emits `mumei.sol-summary-accept/v1`: `accepted` only under an exact whole-context match, echoing the declared summary | Accept a stale or forged manifest — any byte drift refuses |

The Solidity analyzer is source-analysis infrastructure, **not a verifier
or proof backend**; no audit, MCP or planner route runs it by default.
Manifest function keys are contract-qualified (`DemoCounter.add`); the bare
`--function add` resolves because the unit holds one contract — an ambiguous
bare name would refuse with `ambiguous_function`.
