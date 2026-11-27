# CI Evidence Pack Reference

This optional scenario is the v0.8 D-2 reference implementation for CI adoption. It uses the upstream `mumei-agent audit` CI contract without fabricating artifacts in mumei-demo:

1. run `audit --format json --auto-migrate --sarif-output ... --baseline ... --write-baseline ... --fail-on high-confidence` with LLM credentials explicitly empty; when the pinned audit CLI exposes `--migration-execution-output`, also emit `migration_execution.json`;
2. preserve the fixed audit keys in `audit.json` and validate the upstream-emitted SARIF 2.1.0 and `mumei.audit-baseline/v1` artifacts;
3. derive a human-review migration plan from `migration_hints`;
4. validate the optional upstream `mumei.migration-execution/v1` artifact when emitted, without treating partial artifacts as completion evidence;
5. verify the reviewed reference contract `reference/safe_divide.mm` with `mumei verify --proof-cert` and recheck it with `verify-cert --strict`;
6. package the audit, SARIF rendering, refreshed baseline, migration plan, optional migration execution artifact, proof certificate, copyable workflow, summary, hashes, and evidence boundaries in `evidence-pack/`.

## Run

```bash
CI_FIXTURE_MODE=1 make demo-ci-evidence-pack
```

The scenario is optional and is not part of the default `demo-ci` scenario list. CI validates it through `.github/workflows/audit-evidence-pack.yml` when the reference files change.

## Baseline bootstrap policy

`reference/audit-baseline.json` is the reviewed input baseline for this fixture. The audit CLI refreshes `evidence-pack/audit-baseline.json` on every run. In an adopting repository, review the first generated baseline artifact, commit it as repository-local CI policy, and only then rely on suppression. A baseline is repository-local policy input to fail-on decisions; it is not evidence, does not rewrite the fixed audit keys, and must not participate in proof acceptance.

## Evidence boundary

- `audit.json` is existing-code audit evidence, not a proof certificate.
- `audit.sarif` is the upstream audit CLI's SARIF rendering of those audit findings, not independent evidence; this demo never fabricates SARIF.
- `audit-baseline.json` is a `ci_policy` artifact, not evidence or proof acceptance.
- `migration_plan.json` is a human-review plan derived from `migration_hints`, not a completed migration.
- `migration_execution.json` is emitted only by the upstream audit CLI when supported. It is generated-`.mm` acceptance evidence only, not host semantic-equivalence proof; partial artifacts are not completion evidence, and unbound host diagnostics are not adapter observations. Older CLIs are recorded as `not_available_in_current_cli` and no file is fabricated.
- `ready_for_human_review` and `blocked` are candidate review states, not independent CI failure classes. Operational failure is separate (`operational_error`); even ready candidates require human review and do not prove host semantic equivalence.
- `reference.proof.json` proves only `reference/safe_divide.mm` as a standalone `.mm` contract.
- `native_bundle` and `adapter_observation` are closed artifact roles and are empty in `artifact_roles`; audit, migration, policy, and proof artifacts must not be relabeled as either role.
- Nothing in the pack proves semantic equivalence between `src/ledger.py` and `reference/safe_divide.mm`.
- Deterministic means fixed inputs plus no-LLM audit invocation. It does not mean byte-identical artifacts across runs because the current proof-certificate format contains a timestamp and machine-local paths.

## Pack layout

| File | Meaning |
|---|---|
| `manifest.json` | v2 schema, input hashes, artifact hashes, closed artifact roles, SARIF/baseline/fail-on metadata, evidence boundary |
| `audit.json` | Normalized current-CLI audit output with fixed keys, deterministic-mode metadata, canonical `artifact_paths`, closed `artifact_roles`, and role-specific evidence boundaries |
| `audit.sarif` | SARIF 2.1.0 emitted by `mumei-agent audit` for CI annotation |
| `audit-baseline.json` | Refreshed `mumei.audit-baseline/v1` fingerprint policy emitted by `mumei-agent audit` |
| `migration_plan.json` | Prioritized migration-review candidates from `migration_hints`, with the same artifact path/role metadata |
| `migration_execution.json` | Optional upstream `mumei.migration-execution/v1` artifact; absent with `not_available_in_current_cli` on older CLIs. Its companion generated-artifact directory may be uploaded with the pack and is hashed under migration-execution metadata, but stays outside the proof-certificate and adapter-observation roles. Candidate counts summarize review routing only; `blocked` is not an operational CI failure and `ready_for_human_review` is not merge approval |
| `verification.json` | Reference-contract verification status and boundary |
| `reference.proof.json` | Proof certificate for the reviewed reference `.mm` contract |
| `github-actions-mumei-audit.yml` | Copyable workflow template |
| `summary.md` | Human-readable CI/job summary |
| `*.log` | Audit stderr and verifier/recheck logs |
