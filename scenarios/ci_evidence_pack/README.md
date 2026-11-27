# CI Evidence Pack Reference

This optional scenario is the v0.8 D-1 reference implementation for CI adoption. It uses the **current** `mumei-agent audit` CLI without changing its contract:

1. run `audit --format json --auto-migrate` with LLM credentials explicitly empty;
2. preserve the fixed audit keys in `audit.json`;
3. derive a human-review migration plan from `migration_hints`;
4. verify the reviewed reference contract `reference/safe_divide.mm` with `mumei verify --proof-cert` and recheck it with `verify-cert --strict`;
5. package the audit, migration plan, proof certificate, copyable workflow, summary, hashes, and evidence boundaries in `evidence-pack/`.

## Run

```bash
CI_FIXTURE_MODE=1 make demo-ci-evidence-pack
```

The scenario is optional and is not part of the default `demo-ci` scenario list. CI validates it through `.github/workflows/audit-evidence-pack.yml` when the reference files change.

## Evidence boundary

- `audit.json` is existing-code audit evidence, not a proof certificate.
- `migration_plan.json` is a human-review plan derived from `migration_hints`, not a completed migration.
- `reference.proof.json` proves only `reference/safe_divide.mm` as a standalone `.mm` contract.
- `native_bundle` and `adapter_observation` are closed artifact roles and are empty in `artifact_roles`; audit, migration, and proof artifacts must not be relabeled as either role.
- Nothing in the pack proves semantic equivalence between `src/ledger.py` and `reference/safe_divide.mm`.
- `audit.sarif` is intentionally absent until `mumei-agent` emits SARIF. The workflow only uploads it conditionally; this demo does not fabricate SARIF.
- Deterministic means fixed inputs plus no-LLM audit invocation. It does not mean byte-identical artifacts across runs because the current proof-certificate format contains a timestamp and machine-local paths.

## Pack layout

| File | Meaning |
|---|---|
| `manifest.json` | Schema, input hashes, artifact hashes, closed artifact roles, SARIF capability status, evidence boundary |
| `audit.json` | Normalized current-CLI audit output with fixed keys, deterministic-mode metadata, canonical `artifact_paths`, closed `artifact_roles`, and role-specific evidence boundaries |
| `migration_plan.json` | Prioritized migration-review candidates from `migration_hints`, with the same artifact path/role metadata |
| `verification.json` | Reference-contract verification status and boundary |
| `reference.proof.json` | Proof certificate for the reviewed reference `.mm` contract |
| `github-actions-mumei-audit.yml` | Copyable workflow template |
| `summary.md` | Human-readable CI/job summary |
| `*.log` | Audit stderr and verifier/recheck logs |
