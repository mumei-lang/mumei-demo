# GitHub Actions CI reference (10-minute adoption path)

Use the upstream composite action for the initial existing-code audit gate. The richer evidence-pack reference in this repository remains the migration/proof-pack example; it does not fabricate SARIF or baseline data.

## Payment/ledger vertical quick start

The recommended first vertical is a small payment/ledger backend because its review questions map directly to preconditions, arithmetic rounding, balance invariants, and state transitions. The reusable repo-root starter is [`templates/payment-ledger-starter`](../templates/payment-ledger-starter/). It carries the canonical stdlib-only fixture at [`templates/payment-ledger-starter/src/payment_ledger.py`](../templates/payment-ledger-starter/src/payment_ledger.py), an empty `mumei.audit-baseline/v1` baseline, a two-job workflow skeleton, and a payment-specific reviewer runbook. The fixture is intentionally small and is not a production-safe ledger: use it only to exercise the adoption path, then point `code-file` at your own payment module.

With the fixture and deterministic/no-LLM settings, the expected result is one high-priority migration hint for `split_cents`, one migration execution candidate named `split_cents` in `blocked` state, `review_required: true`, and a downloaded artifact that passes the pinned artifact verifier. `blocked` is retained review evidence, not an operational failure of the action.

Use this payment reviewer checklist before acting on the artifact:

- Check whether `recipient_count > 0` must become an explicit precondition or runtime validation for payout splitting; migration execution evidence does not decide that product requirement.
- Check the integer-split remainder policy in `payout_summary`; the generated artifact does not prove that the host Python implements the same rounding behavior.
- Check account-existence, negative-amount, and non-negative-balance requirements in `transfer_cents`; these remain human migration requirements even when a generated `.mm` candidate exists.
- Treat migration execution as generated `.mm` acceptance evidence only. It is not host semantic-equivalence proof, and `audit-baseline.json`/`generated-baseline.json` are CI policy rather than evidence.

Decision guide: use the starter composite-action path for the first ten-minute audit evidence/review-handoff loop; use the advanced evidence-pack reference only when you need the custom pack layout and reviewed reference certificate; use native distribution verification only later for trusted `.mm` native bundles. The pinned action includes migration contract-erosion provenance. `contract_erosion` is additive tool-execution provenance rather than proof acceptance, and a skip such as `skipped_no_change` is explicit not-checked evidence; in this no-LLM payment fixture it means the generated contract text did not change, so erosion comparison was not run. It is not a success condition for this first payment path and does not make migration execution anything more than generated `.mm` acceptance evidence.

## Starter workflow adoption path

1. Copy the contents of [`templates/payment-ledger-starter`](../templates/payment-ledger-starter/) into a throwaway consumer repository root, preserving the `.github` directory. The template is already laid out as it should exist in the consumer repo.
2. Review [`.github/workflows/mumei-audit.yml`](../templates/payment-ledger-starter/.github/workflows/mumei-audit.yml) before enabling it. It uses `mumei-audit@640d597ec60bf574d0102cae6b89054d47fd9f0f` and a verifier raw URL pinned to the same commit. Keep those commit references identical when updating them. Before production use, review the action and pin either that commit SHA or a newer immutable release ref; do not use a mutable branch ref such as `@develop` as a production dependency.
3. Keep `audit-args` on one line: the composite action treats it as a space-separated argument list. `migration-execution-output` is optional but enabled in the starter because it makes the migration evidence handoff explicit. The path must be fresh on every run, stay inside the caller workspace, and use a `.json` filename; the action automatically adds `--auto-migrate` when needed and copies the JSON plus companion generated files into the evidence artifact. Do not commit or reuse that output path as a cache.
4. Open a pull request. The audit job writes a step summary, audit JSON, SARIF, logs, timing files, `generated-baseline.json`, and migration execution evidence in the `mumei-audit-evidence` artifact. The second job downloads that artifact and verifies it offline for the fixture smoke.
5. The strict verifier flags and exact `split_cents` assertion are fixture-smoke checks. When replacing the fixture with real source, delete that assertion and adjust or remove the strict flags as described in the starter README. A real repository can produce zero migration candidates; that artifact is outside the current artifact verifier contract and is not proof failure or proof success.
6. Review `migration-execution/migration_execution.json` with `status.json` and `generated-artifacts/` before acting on any migration candidate. Treat `ready_for_human_review` as a review queue and `blocked` as retained evidence gaps, not as independent CI failure classes.
7. Review `generated-baseline.json`. If the suppressed fingerprints are accepted as repository policy, commit that file as `audit-baseline.json`. Later runs pass it through `--baseline`; do not treat the baseline as evidence.
8. Optional: protect `audit-baseline.json` with CODEOWNERS or an equivalent review rule. It is CI suppression policy, so changes to it need the same explicit review as other merge-gate policy.

A maintainer can reach evidence generation and review-handoff confirmation in about ten minutes for the small fixture. Human migration review is not included in that ten-minute target. The measured small-repo action runtime is much shorter than the human review loop; the first uncached run can still take longer because Python, uv dependencies, and the mumei installer are being populated.

## Required permissions and SARIF behavior

`contents: read` is required for checkout. The starter verification job also needs `actions: read` to download the evidence artifact. `security-events: write` is required only when `upload-sarif` is true and GitHub code scanning is enabled for the repository. The SARIF file is still uploaded in the evidence artifact either way.

The quick start sets `upload-sarif: false` because the optional upload fails in repositories without GitHub Code Security/code scanning even when the audit itself succeeded. The SARIF file remains in the evidence artifact either way. After enabling code scanning, set `upload-sarif: true` to publish the same upstream-generated SARIF there.

## Deterministic/no-LLM default

No LLM secret is required. Without `LLM_API_KEY` or `OPENAI_API_KEY`, audit uses the deterministic extraction path and records model limitations in the normal audit keys. The example explicitly empties both variables so an organization- or repository-level secret does not silently change the adoption gate into an LLM-backed audit. Do not pass secret values through action inputs or write them to artifacts.

## Baseline and fail-on operation

`audit-baseline.json` is input policy in `mumei.audit-baseline/v1` format. `--write-baseline` refreshes the complete fingerprint set on every run, and `--fail-on high-confidence` fails the gate only for non-suppressed high-confidence code evidence. At the pinned action commit, direct hardcoded-credential findings, direct credential-comparison timing-side-channel findings, qualifying unchecked Solidity low-level value-call or ERC20-like token-transfer results, and qualifying Python/Go credential-generation or Solidity winner-selection insecure-randomness findings are projected as high-confidence, so unsuppressed instances fail this gate. TypeScript lookup-capability insecure-randomness findings remain medium-confidence; other deterministic static-analysis findings retain their existing confidence projection. Audit exit `1` means finding-policy failure after a completed audit; exit `2` means operational or extraction failure. The composite action preserves the raw classification as `audit_exit_code` and fails only after writing artifacts and the summary.

The baseline is not evidence, does not remove findings from the underlying audit semantics, and must not participate in proof acceptance. Suppressions enter the repository only by human review of the generated baseline artifact.

## Composite action evidence map

The default artifact name is `mumei-audit-evidence`; setting `artifact-name` only renames that uploaded bundle. Its important entries are:

| Artifact entry | Role |
|---|---|
| `audit.json` / `audit.sarif` | Upstream audit report and its SARIF rendering for annotations. SARIF is not independent proof evidence. |
| `audit.stdout.log` / `audit.stderr.log` | Operational logs for extraction failures and diagnostics. |
| `generated-baseline.json` | Refreshed fingerprint policy when `--write-baseline` is used. It is CI policy input for human review, not evidence. |
| `timing/` | Raw timing files behind the step summary and timing outputs. |
| `migration-execution/migration_execution.json` | Optional upstream `mumei.migration-execution/v1` artifact copied from the requested fresh workspace path. |
| `migration-execution/generated-artifacts/` | Companion generated `.mm`, heal, verification, and proof-certificate files copied while preserving their paths relative to the original generated-artifact directory. They remain generated-contract evidence only. |
| `migration-execution/status.json` | Action-side collection status, count summary, and evidence boundary. |

Paths embedded in `migration_execution.json` are runner/workspace provenance and are not portable links in the downloaded artifact. Do not resolve those absolute paths locally; inspect the copied companions under `migration-execution/generated-artifacts/` instead.

Step outputs have distinct roles: `audit_exit_code` is the audit process classification (`0` no failing code evidence, `1` finding-policy failure, `2` operational/extraction failure); `setup_seconds`, `audit_seconds`, and `total_seconds` are timing evidence; `migration_execution_status` is the collection/precheck outcome (`not_requested`, `emitted_by_audit_cli`, or `operational_error`); `migration_execution_ready_count` is only the number of candidates in `ready_for_human_review` state; `migration_execution_operational_error_count` is the number of candidate-level `operational_error` states copied into the artifact. A candidate-level `operational_error` does not change `migration_execution_status` to `operational_error`; inspect the count output or `status.json` for that candidate state.

## Migration states are not CI failure classes

Migration execution `blocked` and `ready_for_human_review` candidate states are review routing evidence. `blocked` means the artifact retains a contract/provenance/evidence blocker for a human; it is not an operational CI failure and does not mean the audit CLI failed. `ready_for_human_review` means the generated `.mm` acceptance evidence is complete enough to review, not that the host code is equivalent or that the migration may merge without review. Candidate-level `operational_error` is different: the artifact and companion files are copied first, but the composite action then fails the job as its consumer policy. Use `migration_execution_operational_error_count` or `migration-execution/status.json` to distinguish that candidate failure from collection/precheck failure. The action still writes its summary and uploads the evidence artifact before the outer job fails; a caller job that consumes the count output in a later step must give the audit step an `id` and use an always-run condition such as `if: always()` on that consumer step. Do not add a separate CI failure merely because a candidate is `blocked` or `ready_for_human_review`.


## Verifying a downloaded action artifact offline

The composite action repository carries a small stdlib-only verifier for accidental artifact corruption, missing files, count mismatches, path/hash mismatches, and hidden companion loss. It applies to artifacts produced with `migration-execution-output` and `--write-baseline` enabled, as in the golden path above, and currently expects at least one blocked or ready migration candidate. An artifact from an audit run that omits migration execution, baseline generation, or migration candidates is outside this verifier's current contract and is expected to fail its required evidence checks. It is not a malicious-tamper trust anchor by itself and it does not independently re-run proof certificates. Pin it to the same immutable action commit, then run it against the downloaded artifact directory:

```bash
curl -fsSL https://raw.githubusercontent.com/mumei-lang/mumei-agent/640d597ec60bf574d0102cae6b89054d47fd9f0f/.github/actions/mumei-audit/scripts/verify_audit_evidence_artifact.py \
  -o verify_audit_evidence_artifact.py
python3 verify_audit_evidence_artifact.py /path/to/downloaded/mumei-audit-evidence
```

The verifier checks the action artifact layout, migration execution counts and boundaries, and generated companion path/hash claims. It treats the baseline as CI policy and migration execution as generated `.mm` acceptance evidence only.

This repository's [audit action golden-path consumer workflow](../.github/workflows/audit-action-consumer.yml) runs the documented no-LLM path with `upload-sarif: false`, downloads the resulting artifact in a separate job, and verifies it with the same pinned script.

## Native distribution verification reference

The integration workflow validates `mumei-agent verify-distribution` against the trusted fixture source [`scenarios/native_observations_accept/src/main.mm`](../scenarios/native_observations_accept/src/main.mm). CI builds the native bundle during the job, writes the producer-observed `sha256(native-bundle.json)` to `trusted-build-id.txt` as a simulated independent trusted channel, reads that file back for the consumer verifier invocations, and validates the role-separated JSON with [`scripts/check_verify_distribution_reference.py`](../scripts/check_verify_distribution_reference.py). No binary bundle is committed.

The consumer invocations pass `--require-exact-bundle-layout` because this reference validates the raw `mumei native-bundle build` output shape. The validator also requires undeclared extra-file and symlink probes to fail verification. That exactness is not a packaging policy: downstream packaging may add README, LICENSE, install scripts, or other metadata around a raw bundle, but those packaged layouts are outside this raw-bundle reference and must not use this exact-layout option without a separate packaging manifest. This reference intentionally does not generate packaging metadata.

In real adoption, the publisher must obtain the build ID at build time — the `mumei native-bundle build` output includes it, and `sha256(native-bundle.json)` in the trusted build environment is equivalent — and distribute it through an independent integrity-protected channel such as signed release notes, a reviewed lockfile, or separately approved release metadata. The consumer passes that externally supplied value as `--expected-build-id`. Recomputing a hash from the downloaded artifact is a consistency check only; it is not a trust root and must not be substituted for the trusted channel.

Treat the input cases as UX/provenance categories rather than new verifier verdicts: a wrong ID is a well-formed trusted input that does not match the artifact; an untrusted ID lacks independent provenance (for example it was copied from or recomputed over the same untrusted download); an unknown ID is missing, empty, or malformed. Fix untrusted or unknown input before verification. These categories do not add verdict, role, or status vocabulary.

This validation is role-separated orchestration, not a deep acceptance fold. It is not a unified verdict, not a proof grade, and not reusable evidence. `proof_certificate`, `native_source_llvm`, `artifact_reproduction`, and `runtime_observation` remain distinct roles; adapter evidence is outside the verifier's scope and must not be folded into proof, native, or runtime evidence.

Runtime observation is off by default because it executes the reproduced program. The runtime-on validation in this CI lane is an explicit opt-in for this checked-in trusted fixture source and the bundle built from it only. Do not reuse that lane as unconditional execution of external input artifacts. The verifier keeps the existing attempt timeout/memory-bound mechanism rather than weakening it.

The negative validation uses a wrong externally supplied build ID and requires the native source/LLVM and artifact reproduction roles to remain `inconclusive` with `unclaimed_exit_outcome`; it must not become false acceptance.

## Timing evidence

The composite action exposes `setup_seconds`, `audit_seconds`, and `total_seconds` and prints them in the job summary. The upstream selftest runs it against `examples/ci-small-repo` in [`.github/workflows/mumei-audit-selftest.yml`](https://github.com/mumei-lang/mumei-agent/blob/develop/.github/workflows/mumei-audit-selftest.yml).

Public selftest measurements on 2026-11-27 were:

| Run | Setup | Audit | Total |
|---|---:|---:|---:|
| [46033169687](https://github.com/mumei-lang/mumei-agent/actions/runs/46033169687) | 5s | 1s | 6s |
| [46032329900](https://github.com/mumei-lang/mumei-agent/actions/runs/46032329900) | 6s | 2s | 8s |
| [46032056927](https://github.com/mumei-lang/mumei-agent/actions/runs/46032056927) | 6s | 2s | 8s |
| [46030640617](https://github.com/mumei-lang/mumei-agent/actions/runs/46030640617) | 5s | 1s | 6s |

These are warm-cache small-fixture measurements, not a universal SLA. A cold cache, large source tree, language-specific extraction, or optional LLM-backed audit can take longer. The action's own summary is the evidence surface adopters should cite for their repository.

## Advanced evidence-pack reference

This repository carries a working migration/proof evidence-pack implementation in [`scenarios/ci_evidence_pack`](../scenarios/ci_evidence_pack/README.md) and validates it with [`.github/workflows/audit-evidence-pack.yml`](../.github/workflows/audit-evidence-pack.yml). Its copyable workflow is [`scenarios/ci_evidence_pack/reference/workflows/mumei-audit.yml`](../scenarios/ci_evidence_pack/reference/workflows/mumei-audit.yml).

Use that advanced reference when the adoption is ready to add `migration_plan.json`, a reviewed reference `.mm` certificate, a hash manifest, and explicit evidence-boundary metadata. It intentionally invokes the audit CLI directly rather than the composite action because it owns a custom pack layout; use the composite action quick start for the shorter initial audit gate.

## What the evidence pack proves

| Artifact | Meaning |
|---|---|
| `audit.json` | Current audit CLI output for existing code, including `verification_status`, `cross_validation_gaps`, `next_steps`, `migration_hints`, canonical `artifact_paths`, closed `artifact_roles`, and role-specific evidence boundaries |
| `audit.sarif` | Upstream audit CLI SARIF rendering of audit findings for CI annotation; not independent evidence |
| `audit-baseline.json` | Repository-local CI suppression policy refreshed by the audit CLI; not evidence |
| `migration_plan.json` | Human-review migration plan derived only from `migration_hints`, with the same artifact path/role metadata and a migration-scaffold boundary |
| `migration_execution.json` | Optional upstream `mumei.migration-execution/v1` generated-`.mm` acceptance artifact when the pinned audit CLI supports it; absent rather than fabricated otherwise. The manifest hashes companion generated files under the migration-execution metadata without assigning them proof-certificate or adapter-observation roles |
| `reference.proof.json` | Proof certificate for the reviewed reference `.mm` contract only |
| `manifest.json` | Schema, input/artifact hashes, canonical `artifact_paths`, closed `artifact_roles`, SARIF/baseline/fail-on metadata, and evidence boundary |
| `summary.md` | Human-readable job summary |

## What it does not prove

- Audit output and its SARIF rendering are not proof certificates.
- A migration hint or skeleton is not evidence of completed migration.
- Migration execution evidence proves only generated `.mm` contracts as written. It is not host semantic-equivalence proof; partial artifacts are not completion evidence, generated proof certificates are not relabeled as the reviewed reference certificate role, and unbound host diagnostics are not adapter observations.
- Baseline suppression is CI policy, not evidence removal, proof acceptance, or a verdict-boundary change.
- The reference `.mm` certificate does not prove semantic equivalence with Python or another host-language implementation.
- No native bundle is present or implied by this audit/migration evidence pack.
- No adapter observation is present or implied by this audit/migration evidence pack; runtime observations must not be folded into proof evidence.

`artifact_paths` is the canonical ordered list of pack files present for the detected CLI capability in `audit.json`, `migration_plan.json`, and `manifest.json`, including `manifest.json` itself. The manifest's `artifacts` hash rows cover every canonical pack file except the self-referential manifest; files inside the migration execution companion directory are hashed separately under `migration_execution.generated_artifacts` rows containing `path`, `sha256`, and `bytes`. `artifact_roles` is the closed v2 role map: `audit_report` points at `audit.json` and `audit.sarif`, `migration_plan` and `proof_certificate` point at their respective files, `migration_execution` points at `migration_execution.json` only when emitted, `ci_policy` points at `audit-baseline.json`, and `native_bundle`/`adapter_observation` are empty lists. Treating those absent roles as present, pointing them at audit/migration artifacts, or treating `ci_policy` as evidence is a schema/policy regression rather than evidence acceptance.

## Reviewer checklist

- Open `summary.md` first.
- Confirm the job used deterministic/no-LLM audit unless LLM extraction was explicitly approved.
- Confirm `audit.sarif` and `audit-baseline.json` are upstream CLI outputs, not repository-generated fabrications.
- Treat `audit-baseline.json` as `ci_policy`, not evidence, and review every suppression change.
- Treat `migration_plan.json` entries as `human_review_required`.
- Treat every migration execution candidate as `review_required` even when `ready_for_human_review`; never read it as host semantic-equivalence proof.
- Treat `reference.proof.json` as proof only for the reviewed reference `.mm` contract.
