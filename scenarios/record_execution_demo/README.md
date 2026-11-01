# Fixed record operations: an evidence-boundary example

Run the optional experiment with a built sibling `mumei` and the pinned Lean
toolchain installed for sibling `mumei-lean`:

```bash
export PATH="$HOME/.elan/bin:$PATH"
make demo-record-execution
python3 dashboard/cli_report.py reports/record_execution_demo/latest/result.json
```

No credentials, LLM calls, external database or extra Python dependencies are
needed. This target is deliberately outside the default 18-scenario
`make demo` / `make demo-ci` sequence. Missing Lean, failed builds or missing
model evidence **fail**, rather than becoming optional skips. Source-built
integration CI runs it separately and retains the complete report directory.

## Four distinct kinds of evidence

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| `.mm` / Claim Book | `advance_version` increments a bounded version under its precondition; a fixed incorrect body is rejected | Python execution, authority, locking or model correspondence |
| Independent Lean model | A fresh rebuild and kernel axiom audit of the registered model/example theorems; the full current set is audited, not just the required selectors | JSON parsing, bounded Python arithmetic, host authentication, locking or deployed behavior |
| Python finite checks | 25 named cases exercise the same fixed executor, including successful read/update, denials, stale/replayed updates, policy changes and concurrent conflicts | A proof covering arbitrary Python executions or schedules |
| Scenario evidence aggregation | Required steps and artifact identities are present and rechecked on report load | Authenticity, a new safety grade, or semantic equivalence between the first three rows |

The only required Claim Book grade is G4 for the small `.mm` atom. Independent
model theorems appear in a separate section, without a grade. No Python result
becomes `lean_verified`, G5, a Claim Book claim or a Charter result. The existing
runner's layer labels and step/proof-density counters are not application
safety scores. Here `l2_agent` contains only finite Python fixtures; it does not
run an LLM or `mumei-agent` repair.

## Checks and negative controls

The host owns reference cases, principal, initial records and policy. The only
producer input to the actual executor is proposal JSON. Normal owner/admin
updates and a reader read succeed. Other cases cover organization and owner
mismatches, unknown roles/operations, protected organization/owner/version
fields, extra role fields, missing records/policy, disabled reads/updates,
empty/malformed input, target substitution, stale/replayed versions, changed
principal and attempted reuse of a prior decision as input. Two real threads
submit the same version: exactly one update succeeds, without a partial second
write or an unrelated-record change. These are observations, not exhaustive
concurrency proof. The broader parser/fault/128-case matrix remains in
`make test-record-execution`.

Four **trusted test-host variants** run exactly those reference checks:

| Intentionally broken host | Required detected case |
| --- | --- |
| Missing organization check | `cross_organization` |
| Missing ownership check | `wrong_owner` |
| Updating identity as well as value | `owner_update` |
| Writing directly, outside authorization/version checks | `reader_update` |

Each must return failure and print its specific violated case; a generic crash
or a nonzero status alone is insufficient. Their JSON files record failures,
not successful implementation behavior. They are test fixtures in the host
harness, not selectable by proposal JSON and not deployed executor modes.
In particular, detection of the direct-write variant does **not** mean Python
prevents arbitrary privileged code from bypassing the adapter. The closed
proposal interface rejects dispatch names, callbacks and extra host inputs;
arbitrary same-process code remains outside that boundary.

## Artifacts and trust boundary

Runs live under `reports/record_execution_demo/<timestamp>/` and `latest/`:

- The `.mm` inputs, Python adapter and reference harness are copied into the
  output directory before use. Runtime observations omit record values, raw
  proposals and exception text; audit metadata still contains identifiers.
- `runtime.json` contains baseline observations. Each named variant has a
  separate failed observation report and a gate-specific log.
- `model/model.json` records only independent model evidence. The collector
  invokes the existing model checker, requires its fresh successful rebuild,
  checks the complete named theorem set from both modules, and rejects
  non-allowlisted axioms. It snapshots selected model/build/audit inputs before
  running, rechecks their hashes afterward, and keeps kernel/build logs in
  `model/audit/`. Lean's ordinary build cache is in the sibling repository.
  These snapshots are selected inputs, not a complete dependency/toolchain
  archive. Imported checker helpers, dependencies and the host are trusted.
- `result.json`, `harness_state.json` and `report.md` keep claims, independent
  model proofs, finite observations, declared assumptions, unverified
  connections and out-of-scope items separate. Reopening after a required
  artifact is deleted or changed displays failure.

The host-selected principal is an assumption, not verified authentication.
Matching source/report hashes is local snapshot consistency, not a signature or
a proof that Python implements Lean. There is no production storage, HTTP,
external delivery, cross-process lock, persistent audit, dynamic delegation or
deployment-safety claim. Neither the policy's business suitability nor an
arbitrary host-code sandbox is proved. See the [adapter runbook](../../docs/RECORD_EXECUTION.md).

For a separate opt-in summary without changing the ordinary dashboard outputs:

```bash
python3 scripts/generate_report.py --summary --require-all \
  --scenarios record_execution_demo --output reports/record_execution_demo/summary.md
```
