# Go interprocedural summary manifests: a declared-route example

Run the optional scenario with a sibling `mumei-agent` checkout:

```bash
make demo-go-summaries
python3 dashboard/cli_report.py reports/go_summaries/latest/result.json
```

Fixture mode (the default, `CI_FIXTURE_MODE=1`) replays route payloads recorded
from the real helper, so CI stays deterministic without a Go toolchain. For the
live run, put a maintained Go 1.26+ toolchain on `PATH` and opt in:

```bash
CI_FIXTURE_MODE=0 make demo-go-summaries
```

This target is deliberately outside the default `make demo` / `make demo-ci`
sequence — like `record_execution_demo` it sits in `OPTIONAL_SCENARIOS` because
its real mode needs a provisioned toolchain. In fixture mode the
`build_go_types` step reports SKIPPED when `go` is absent; the remaining steps
emit the recorded manifest, check and accept payloads. In real mode a missing
toolchain fails `emit_manifest` loudly instead of fabricating a manifest.

## The emit -> check -> accept loop

| Step | What it does | What it does not do |
| --- | --- | --- |
| `build_go_types` | Compiles `tools/go-types` into the report directory (single-file `go/parser` + `go/types` metadata producer, no third-party dependencies) | Install the helper as a default dependency, or run it on undeclared inputs |
| `emit_manifest` | Runs `python -m agent go-summaries` on `demo_counter.go` and writes `manifest.json` (`mumei.go-scalar-parameter-deps/v1`): per-function `binding_id`, parameters, `return_dependencies` and intra-package `calls`, keyed by the unit's `context_key` | Verify, prove or certify anything — the manifest is declared data |
| `check_manifest` | Re-runs the helper via `go-summaries-check` and emits `mumei.go-summary-check/v1`: `context_match` plus a `reusable`/`stale`/`missing` partition of the declared bindings | Authorize reuse — the host chooses what to trust |
| `accept_summary` | Runs `go-summaries-accept --binding <id>` and emits `mumei.go-summary-accept/v1`: `accepted` only under an exact whole-context match, echoing the declared summary | Accept a stale or forged manifest — any byte drift refuses |

The go-types helper is source-analysis infrastructure, **not a verifier or
proof backend**; no audit, MCP or planner route runs it by default. Editing
`demo_counter.go` invalidates the recorded fixture payloads (binding ids are
sha256-pinned to source bytes) on purpose — regenerate them by running the
real mode once.
