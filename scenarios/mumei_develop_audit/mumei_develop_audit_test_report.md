# Live test report: mumei_develop_audit

Date: 2026-06-21 UTC  
PR: <https://github.com/mumei-lang/mumei-demo/pull/51>  
Devin session: <https://app.devin.ai/sessions/fadd45f7ec604980ae7c080c504dba08>

## Evidence files

The recording is stored as a Devin attachment instead of a checked-in binary to
avoid increasing repository size with generated media.

- Recording: <https://app.devin.ai/attachments/5c9d9504-cf68-4eba-bafe-0e0984571cc2/mumei_develop_audit_dashboard-edited.mp4>
- Dashboard metrics screenshot: <https://app.devin.ai/attachments/9a32d802-aaa3-4fa8-8ee4-013105fed2aa/mumei_dashboard_metrics.png>
- Expanded L2 audit screenshot: <https://app.devin.ai/attachments/1c73edfd-3322-40dd-a1bb-838614d012fb/mumei_dashboard_l2_audit_expanded.png>
- Step details screenshot: <https://app.devin.ai/attachments/1c41402b-6339-4b5c-b2b5-f2551a06e080/mumei_dashboard_step_details.png>

## Live scenario execution

Command:

```bash
CI_FIXTURE_MODE=0 ./scripts/run_scenario.sh mumei_develop_audit \
  --mumei-repo ../mumei \
  --mumei-agent-repo ../mumei-agent
```

Result:

- `overall_status`: `PASS`
- `proof_density`: `3/3 (100.0%)`
- `harness_contract`: `COMPLIANT (8/8)`
- `intent_fidelity`: `TRACEABLE (5/5)`
- `l1_inventory/record_targets`: `PASS`
- `l2_audit/audit_develop_target`: `PASS`
- `l3_migrate/generate_migration_guidance`: `PASS`

## Live audit payload

The full structured payload captured from the live run is committed at
`LIVE_AUDIT_RESULT_2026-06-21.json`.

Important fields present:

- `verification_violations`
- `counterexample_values`
- `cross_validation_gaps`
- `spec_health_issues`
- `migration_hints`
- `fixture_live_branch`
- `openai_api_key_used`
- `generated_artifacts`

The saved scenario artifacts did not include a raw HTTP-level OpenAI
request/response transcript or hidden prompt messages from inside `mumei-agent`.
That limitation is documented in `AUDIT_LOG_2026-06-21.md`.

## Secret boundary

- `OPENAI_API_KEY` was required only for live mode.
- Fixture mode did not require or read `OPENAI_API_KEY`.
- A secret-leak grep against committed docs and saved scenario artifacts passed;
  the provided key value was not found.

## Dashboard validation

The Streamlit dashboard was opened against the generated report and recorded.
Observed evidence:

- `mumei_develop_audit` appeared in the scenario selector.
- The live report path was selected.
- All three layers displayed `PASS`.
- Proof density displayed `100%`.
- Harness contract displayed `COMPLIANT (8/8)`.
- Intent fidelity displayed `TRACEABLE (5/5)`.
- Expanded `l2_audit` evidence showed audit contract keys including
  `verification_violations`, `cross_validation_gaps`, and `migration_hints`.

## Audit findings and repair trace

The live audit produced no direct Z3 counterexamples:

- `verification_violations`: `[]`
- `counterexample_values`: `[]`

The actionable repair candidates came from L2 and L3:

1. L2 `cross_validation_gaps`
   - `analyze_metrics` had no matching implementation mapping.
   - `generate_markdown_report` had no matching implementation mapping.
2. L2 `spec_health_issues`
   - `directory_path.endsWith(...)` failed lowering as an unsupported predicate.
   - `result == true` failed lowering because the contract expected a boolean
     comparison where the audited markdown path returns text.
3. L3 `migrate-suggest`
   - Generated skeleton targets: `count_metrics`, `run_verify`,
     `compute_health`, `scan_std`, `parse_summary`, `collect_history`,
     `render_markdown`, and `main`.

Recommended follow-up: repair or normalize the spec-facing names/contracts in
`mumei/scripts/generate_stdlib_metrics.py` first, then consider a separate
`mumei-agent` lowering improvement for path/string suffix predicates and
text-returning report contracts.

## Checks after documentation updates

```bash
python3 -m json.tool scenarios/mumei_develop_audit/scenario.json >/dev/null
python3 -m json.tool scenarios/mumei_develop_audit/LIVE_AUDIT_RESULT_2026-06-21.json >/dev/null
python3 -m compileall -q scripts dashboard scenarios/mumei_develop_audit
bash -n scripts/setup_repos.sh
bash -n scripts/run_scenario.sh
bash -n scripts/run_all.sh
git diff --check
```

GitHub CI after the live documentation commits:

- `demo`: passed
- `demo-all`: passed
