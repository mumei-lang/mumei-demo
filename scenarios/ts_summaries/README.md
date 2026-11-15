# TypeScript interprocedural summary manifests: a declared-route example

Run the optional scenario with a sibling `mumei-agent` checkout:

```bash
make demo-ts-summaries
python3 dashboard/cli_report.py reports/ts_summaries/latest/result.json
```

Unlike `go_summaries` this scenario needs **no provisioned toolchain and no
fixture mode**: the TypeScript analyzer runs in-process on tree-sitter, so
every step executes the real route command deterministically. This target is
deliberately outside the default `make demo` / `make demo-ci` sequence — like
`go_summaries` it sits in `OPTIONAL_SCENARIOS` because it needs a sibling
`mumei-agent` checkout (`MUMEI_AGENT_REPO`).

## The emit -> check -> accept loop

| Step | What it does | What it does not do |
| --- | --- | --- |
| `emit_manifest` | Runs `python -m agent ts-summaries` on `demo_counter.ts` and writes `manifest.json` (`mumei.ts-scalar-parameter-deps/v1`): per-function parameters, `return_dependencies` and intra-unit `calls`, keyed by the unit's `context_key` | Verify, prove or certify anything — the manifest is declared data |
| `check_manifest` | Re-derives summaries via `ts-summaries-check` and emits `mumei.ts-summary-check/v1`: `context_match` plus a `reusable`/`stale`/`missing` partition of the declared functions | Authorize reuse — the host chooses what to trust |
| `accept_summary` | Runs `ts-summaries-accept --function add` and emits `mumei.ts-summary-accept/v1`: `accepted` only under an exact whole-context match, echoing the declared summary | Accept a stale or forged manifest — any byte drift refuses |

The TypeScript analyzer is source-analysis infrastructure, **not a verifier
or proof backend**; no audit, MCP or planner route runs it by default.
`--resolve-modules` is intentionally unused: manifest `context_key` covers
the declared unit only, and cross-module resolution is out of scope for this
demo.
