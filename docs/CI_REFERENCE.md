# GitHub Actions CI reference (10-minute adoption path)

This repository carries a working reference implementation in [`scenarios/ci_evidence_pack`](../scenarios/ci_evidence_pack/README.md) and validates it with [`.github/workflows/audit-evidence-pack.yml`](../.github/workflows/audit-evidence-pack.yml).

The reference is deliberately based on the current audit CLI. It does **not** require the in-flight upstream SARIF, baseline, or fail-on policy work.

## What you add

1. Check out `mumei` and `mumei-agent` beside the audited repository.
2. Build `mumei` once with the Rust cache enabled.
3. Install `mumei-agent` into a virtual environment.
4. Run the current CLI in deterministic/no-LLM mode:

   ```bash
   mkdir -p evidence-pack
   LLM_API_KEY= OPENAI_API_KEY= CI_FIXTURE_MODE=1 \
   MUMEI_BIN="$PWD/.mumei/mumei/target/release/mumei" \
   python -m agent audit \
     --code-file "$AUDIT_TARGET" \
     --format json \
     --auto-migrate \
     > evidence-pack/audit.json
   ```

5. Validate the fixed audit keys, write a job summary, and upload `evidence-pack/` as a workflow artifact.
6. If a future CLI writes `evidence-pack/audit.sarif`, upload it to code scanning conditionally. Do not fabricate SARIF in the consuming repository.

The copyable workflow is [`scenarios/ci_evidence_pack/reference/workflows/mumei-audit.yml`](../scenarios/ci_evidence_pack/reference/workflows/mumei-audit.yml). Adjust `AUDIT_TARGET` to the source file or directory being introduced. It is intentionally an initial audit-only adoption gate: it uploads the current audit JSON and its contract validation. The richer `migration_plan.json`, reviewed reference proof certificate, hash manifest, and boundary summary are demonstrated by the mumei-demo scenario pack; adopters add those artifacts when they introduce reviewed `.mm` migration targets. The human setup is intended to take about ten minutes; the first CI run can take longer because it builds the verifier, while subsequent runs reuse the Rust cache.

## What the evidence pack proves

| Artifact | Meaning |
|---|---|
| `audit.json` | Current audit CLI output for existing code, including `verification_status`, `cross_validation_gaps`, `next_steps`, `migration_hints`, canonical `artifact_paths`, closed `artifact_roles`, and role-specific evidence boundaries |
| `migration_plan.json` | Human-review migration plan derived only from `migration_hints`, with the same artifact path/role metadata and a migration-scaffold boundary |
| `reference.proof.json` | Proof certificate for the reviewed reference `.mm` contract only |
| `manifest.json` | Schema, input/artifact hashes, canonical `artifact_paths`, closed `artifact_roles`, SARIF capability status, and evidence boundary |
| `summary.md` | Human-readable job summary |

## What it does not prove

- Audit output is not a proof certificate.
- A migration hint or skeleton is not evidence of completed migration.
- The reference `.mm` certificate does not prove semantic equivalence with Python or another host-language implementation.
- No native bundle is present or implied by this audit/migration evidence pack.
- No adapter observation is present or implied by this audit/migration evidence pack; runtime observations must not be folded into proof evidence.
- SARIF, baseline suppression, and CI fail-on policies remain upstream audit CLI work. Until then, their absence is recorded explicitly instead of being emulated in this repository.

`artifact_paths` is the canonical ordered list of pack files in `audit.json`, `migration_plan.json`, and `manifest.json`, including `manifest.json` itself. The manifest's `artifacts` hash rows cover every file except the self-referential manifest. `artifact_roles` is the closed evidence-role map: `audit_report`, `migration_plan`, and `proof_certificate` point at their respective files, while `native_bundle` and `adapter_observation` are empty lists. Treating those absent roles as present, or pointing them at audit/migration artifacts, is a schema/policy regression rather than evidence acceptance.

## Deterministic versus fixture mode

`CI_FIXTURE_MODE=1` in this reference means the demo uses its fixed reference source and forces the audit child process into deterministic/no-LLM mode by setting both credential variables empty. It does not use a canned audit response: the current `mumei-agent audit` CLI runs and its output is normalized only to remove machine-local source paths.

A live LLM-assisted audit can be useful for hypothesis generation, but it is not the default CI gate and unverified hypotheses must not be presented as verified findings.

Deterministic here means deterministic invocation and review inputs, not byte-identical artifacts across machines or runs: the current proof-certificate format includes a generation timestamp and machine-local source paths. The manifest hashes the artifacts produced by a run; it does not claim cross-run byte equality.

## Reviewer checklist

- Open `summary.md` first.
- Check `manifest.json` for schema `mumei-demo.ci-evidence-pack/v1` and artifact hashes.
- Triage `migration_plan.json`; every entry remains `human_review_required`.
- Treat `reference.proof.json` as proof only for the reviewed reference `.mm` contract.
- Confirm that `audit.sarif` is absent with status `not_available_in_current_cli` unless the upstream CLI actually emitted it.
