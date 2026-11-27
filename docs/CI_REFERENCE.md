# GitHub Actions CI reference (10-minute adoption path)

This repository carries a working reference implementation in [`scenarios/ci_evidence_pack`](../scenarios/ci_evidence_pack/README.md) and validates it with [`.github/workflows/audit-evidence-pack.yml`](../.github/workflows/audit-evidence-pack.yml).

The reference uses the upstream audit CLI SARIF, baseline, and fail-on contract. It does **not** fabricate SARIF or baseline data in mumei-demo.

## What you add

1. Check out `mumei` and `mumei-agent` beside the audited repository.
2. Build `mumei` once with the Rust cache enabled.
3. Install `mumei-agent` into a virtual environment.
4. Run the CLI in deterministic/no-LLM mode with the upstream CI contract. `BASELINE_INPUT` is `.mumei/audit-baseline.json` once reviewed, or a schema-valid empty bootstrap baseline on the first run:

   ```bash
   mkdir -p evidence-pack
   LLM_API_KEY= OPENAI_API_KEY= CI_FIXTURE_MODE=1 \
   MUMEI_BIN="$PWD/.mumei/mumei/target/release/mumei" \
   python -m agent audit \
     --code-file "$AUDIT_TARGET" \
     --format json \
     --auto-migrate \
     --sarif-output evidence-pack/audit.sarif \
     --baseline "$BASELINE_INPUT" \
     --write-baseline evidence-pack/audit-baseline.json \
     --fail-on high-confidence \
     > evidence-pack/audit.json
   ```

   On the first run there may be no reviewed `.mumei/audit-baseline.json` yet. The copyable workflow therefore passes a schema-valid empty bootstrap baseline through `--baseline`, always refreshes `evidence-pack/audit-baseline.json`, and uploads it for review. Commit the reviewed artifact as `.mumei/audit-baseline.json` to make later runs suppress only those reviewed fingerprints.
5. Validate the fixed audit keys, SARIF 2.1.0 shape, and `mumei.audit-baseline/v1` shape; write a job summary and upload `evidence-pack/` as a workflow artifact.
6. Upload `evidence-pack/audit.sarif` to code scanning only when the upstream CLI wrote it. Do not fabricate SARIF in the consuming repository.

The copyable workflow is [`scenarios/ci_evidence_pack/reference/workflows/mumei-audit.yml`](../scenarios/ci_evidence_pack/reference/workflows/mumei-audit.yml). Adjust `AUDIT_TARGET` to the source file or directory being introduced. It is intentionally an initial audit-only adoption gate: it uploads audit JSON, SARIF, baseline policy output, and contract validation. The richer `migration_plan.json`, reviewed reference proof certificate, hash manifest, and boundary summary are demonstrated by the mumei-demo scenario pack; adopters add those artifacts when they introduce reviewed `.mm` migration targets. The human setup is intended to take about ten minutes; the first CI run can take longer because it builds the verifier, while subsequent runs reuse the Rust cache.

## What the evidence pack proves

| Artifact | Meaning |
|---|---|
| `audit.json` | Current audit CLI output for existing code, including `verification_status`, `cross_validation_gaps`, `next_steps`, `migration_hints`, canonical `artifact_paths`, closed `artifact_roles`, and role-specific evidence boundaries |
| `audit.sarif` | Upstream audit CLI SARIF rendering of audit findings for CI annotation; not independent evidence |
| `audit-baseline.json` | Repository-local CI suppression policy refreshed by the audit CLI; not evidence |
| `migration_plan.json` | Human-review migration plan derived only from `migration_hints`, with the same artifact path/role metadata and a migration-scaffold boundary |
| `reference.proof.json` | Proof certificate for the reviewed reference `.mm` contract only |
| `manifest.json` | Schema, input/artifact hashes, canonical `artifact_paths`, closed `artifact_roles`, SARIF/baseline/fail-on metadata, and evidence boundary |
| `summary.md` | Human-readable job summary |

## What it does not prove

- Audit output and its SARIF rendering are not proof certificates.
- A migration hint or skeleton is not evidence of completed migration.
- Baseline suppression is CI policy, not evidence removal, proof acceptance, or a verdict-boundary change.
- The reference `.mm` certificate does not prove semantic equivalence with Python or another host-language implementation.
- No native bundle is present or implied by this audit/migration evidence pack.
- No adapter observation is present or implied by this audit/migration evidence pack; runtime observations must not be folded into proof evidence.

`artifact_paths` is the canonical ordered list of pack files in `audit.json`, `migration_plan.json`, and `manifest.json`, including `manifest.json` itself. The manifest's `artifacts` hash rows cover every file except the self-referential manifest. `artifact_roles` is the closed role map: `audit_report` points at `audit.json` and `audit.sarif`, `migration_plan` and `proof_certificate` point at their respective files, `ci_policy` points at `audit-baseline.json`, and `native_bundle`/`adapter_observation` are empty lists. Treating those absent roles as present, pointing them at audit/migration artifacts, or treating `ci_policy` as evidence is a schema/policy regression rather than evidence acceptance.

## Deterministic versus fixture mode

`CI_FIXTURE_MODE=1` in this reference means the demo uses its fixed reference source and forces the audit child process into deterministic/no-LLM mode by setting both credential variables empty. It does not use a canned audit response: the current `mumei-agent audit` CLI runs and its output is normalized only to remove machine-local source paths.

A live LLM-assisted audit can be useful for hypothesis generation, but it is not the default CI gate and unverified hypotheses must not be presented as verified findings.

Deterministic here means deterministic invocation and review inputs, not byte-identical artifacts across machines or runs: the current proof-certificate format includes a generation timestamp and machine-local source paths. The manifest hashes the artifacts produced by a run; it does not claim cross-run byte equality.

## Reviewer checklist

- Open `summary.md` first.
- Check `manifest.json` for schema `mumei-demo.ci-evidence-pack/v1` and artifact hashes.
- Confirm `audit.sarif` and `audit-baseline.json` are present with status `emitted_by_audit_cli`.
- Treat `audit-baseline.json` as `ci_policy`, not evidence.
- Triage `migration_plan.json`; every entry remains `human_review_required`.
- Treat `reference.proof.json` as proof only for the reviewed reference `.mm` contract.
