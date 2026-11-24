# Large-scale scenarios (`SCALE_SCENARIOS`, Priority 16)

Read this when running `make demo-scale` or a per-case scale target, or when interpreting scale metrics, mumei verify cache behaviour, and known pre-existing non-fixture failures.

The five scale cases (`medical_device_scale`, `rtgs_settlement_scale`,
`regtech_compliance_scale`, `defi_invariant_scale`, `ownership_transfer_scale`)
are deliberately kept out of the `SCENARIOS` list in the Makefile, so they must
never appear in `make demo-ci` / `make demo` output or in `dashboard/summary.md`.
They run through separate targets: `make demo-scale` plus per-case targets
`demo-medical-scale`, `demo-settlement-scale`, `demo-regtech-scale`,
`demo-defi-scale`, `demo-ownership-scale`.

Cross-repo prerequisites (default branch is `develop`, not `main`, in both
sibling repos):

- `../mumei` must provide `scripts/measure_composability.py` and
  `scripts/scale_trust_surface.py`.
- `../mumei-agent` must provide the `scale-report` subcommand and a populated
  `.venv` — `scripts/run_scenario.sh` resolves `mumei_agent_python` to
  `{mumei_agent_repo}/.venv/bin/python` when `MUMEI_AGENT_PYTHON` is unset, so a
  missing agent venv silently degrades to system python.

Expected per-case chain and metrics (all steps PASS, proof density 5/5 = 100%):
`verify_scale` (`--proof-cert`) → `verify_cert_strict` → `trust_surface` →
`composability` → `agent_scale_report`. Atom counts: rtgs 30, defi 32, medical 34,
ownership 35, regtech 41 (172 total). `verify_cert_strict.log` should end with
`All verified: true` and `Results: <N> proven, 0 changed, 0 unproven, 0 missing`.
`*.trust-surface.json` should report `std_trusted_atoms == 0`,
`application_trusted_atoms == 0`, `certified_atoms == atom_count`, and
`budget_policy_fingerprint == sha256:scale-default`. In `*.scale-report.json`,
the per-classification counts in `next_steps` should sum to
`composability.totals.composition_breaks`.

Timing: `make demo-scale` takes ~17 min wall on a 2-vCPU box; the
clause-ablation `composability` step alone is ~150 s per case. Do not kill it.

Gotchas worth reusing:

- `mumei verify` caches per-atom results in `<scenario_dir>/.mumei_cache` and
  `.mumei` (both gitignored). A re-run therefore logs
  `Verification passed: 0 verified, N skipped (unchanged)` — that is NOT proof of
  fresh Z3 work. To prove real verification, move those two directories aside
  first; the log should then read `Verification passed: N item(s) verified`.
- Good negative test for the strict certificate gate: copy the emitted
  `*.proof-cert.json`, overwrite one atom's `content_hash` with zeros, and run
  `mumei verify-cert --strict <tampered> correct_code.mm`. Expect exit 1 with
  `1 changed atom(s)` and a `--strict: certificate ... no longer matches` error.
- Non-fixture `make demo` requires `OPENAI_API_KEY`/`LLM_API_KEY`; without it
  `nl_to_verified`, `no_mm_audit`, `mumei_develop_audit` and
  `spec_code_verification_suite` fail (either an explicit
  "LLM_API_KEY ... is not set" or a `[missing expected patterns]` mismatch).
  This is pre-existing and reproducible on pre-change commits — verify by
  re-running the same scenarios at an older commit before blaming a change.
- `scripts/generate_report.py` hardcodes `SCENARIO_ORDER`; it now includes
  `spec_code_verification_suite`, so expect that scenario in
  `dashboard/summary.md` too.
