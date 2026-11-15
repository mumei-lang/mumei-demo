# Rust interprocedural summary manifests: a declared-route example

Run the optional scenario with a sibling `mumei-agent` checkout:

```bash
make demo-rust-summaries
python3 dashboard/cli_report.py reports/rust_summaries/latest/result.json
```

Like `ts_summaries`, this scenario needs **no provisioned toolchain and no
fixture mode**: the Rust analyzer runs in-process on tree-sitter, so
every step executes the real route command deterministically. This target is
deliberately outside the default `make demo` / `make demo-ci` sequence — like
`go_summaries` it sits in `OPTIONAL_SCENARIOS` because it needs a sibling
`mumei-agent` checkout (`MUMEI_AGENT_REPO`).

## The emit -> check -> accept loop

| Step | What it does | What it does not do |
| --- | --- | --- |
| `emit_manifest` | Runs `python -m agent rust-summaries` on `demo_counter.rs` and writes `manifest.json` (`mumei.rust-scalar-parameter-deps/v1`): per-function parameters, `return_dependencies`, intra-unit `calls` and `effects`, keyed by the unit's `context_key` | Verify, prove or certify anything — the manifest is declared data |
| `check_manifest` | Re-derives summaries via `rust-summaries-check` and emits `mumei.rust-summary-check/v1`: `context_match` plus a `reusable`/`stale`/`missing` partition of the declared functions. The step pipes the verdict JSON through `grep` for `"context_match": true` — a refusal reads as FAIL, not PASS | Authorize reuse — the host chooses what to trust |
| `accept_summary` | Runs `rust-summaries-accept --function add` and emits `mumei.rust-summary-accept/v1`: `accepted` only under an exact whole-context match, echoing the declared summary. The same `grep` assertion makes an `accepted: false` refusal fail the step | Accept a stale or forged manifest — any byte drift refuses |

The Rust analyzer is source-analysis infrastructure, **not a verifier
or proof backend**; no audit, MCP or planner route runs it by default.
