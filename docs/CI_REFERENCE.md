# GitHub Actions CI reference (10-minute adoption path)

Use the upstream composite action for the initial existing-code audit gate. The richer evidence-pack reference in this repository remains the migration/proof-pack example; it does not fabricate SARIF or baseline data.

## Copy/paste quick start

1. Add `.github/workflows/mumei-audit.yml` in the repository being introduced:

   ```yaml
   name: Mumei audit
   on: [pull_request]

   permissions:
     contents: read
     security-events: write  # only needed for SARIF code-scanning upload

   jobs:
     audit:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4

         - name: Create a bootstrap audit baseline when absent
           run: |
             if [ ! -f audit-baseline.json ]; then
               printf '%s\n' '{"version":"mumei.audit-baseline/v1","fingerprints":[]}' > audit-baseline.json
             fi

         - uses: mumei-lang/mumei-agent/.github/actions/mumei-audit@b81e8d1a5ebc20a28b256df401cd1594f0443e23
          # Keep the default deterministic/no-LLM path even when repository secrets exist.
           env:
             LLM_API_KEY: ""
             OPENAI_API_KEY: ""
           with:
             code-file: src/
             language: python
             audit-args: --baseline audit-baseline.json --write-baseline .mumei-audit/generated-baseline.json --fail-on high-confidence
             upload-sarif: false  # set true only when GitHub code scanning is enabled
   ```

   Adjust `code-file` and, when needed, `language`. Keep `audit-args` on one line: the composite action treats it as a space-separated argument list. The example pins the full commit SHA that the upstream selftest ran successfully; before production use, review the action and pin either that commit SHA or a newer immutable release ref. Do not use a mutable branch ref such as `@develop` as a production dependency. `@develop` is acceptable only for short-lived bootstrap experiments or examples where reproducibility and supply-chain stability are not yet the gate.

2. Open a pull request. The action writes a step summary, audit JSON, SARIF, logs, timing files, and `generated-baseline.json` in the `mumei-audit-evidence` artifact.
3. Review `generated-baseline.json`. If the suppressed fingerprints are accepted as repository policy, commit that file as `audit-baseline.json`. Later runs pass it through `--baseline`; do not treat the baseline as evidence.
4. Optional: protect `audit-baseline.json` with CODEOWNERS or an equivalent review rule. It is CI suppression policy, so changes to it need the same explicit review as other merge-gate policy.

A maintainer can complete the copy/edit/review loop in about ten minutes. The measured small-repo action runtime is much shorter than that human review loop; the first uncached run can still take longer because Python, uv dependencies, and the mumei installer are being populated.

## Required permissions and SARIF behavior

`contents: read` is required for checkout. `security-events: write` is required only when `upload-sarif` is true and GitHub code scanning is enabled for the repository. The SARIF file is still uploaded in the evidence artifact either way.

The quick start sets `upload-sarif: false` because the optional upload fails in repositories without GitHub Code Security/code scanning even when the audit itself succeeded. The SARIF file remains in the evidence artifact either way. After enabling code scanning, set `upload-sarif: true` to publish the same upstream-generated SARIF there.

## Deterministic/no-LLM default

No LLM secret is required. Without `LLM_API_KEY` or `OPENAI_API_KEY`, audit uses the deterministic extraction path and records model limitations in the normal audit keys. The example explicitly empties both variables so an organization- or repository-level secret does not silently change the adoption gate into an LLM-backed audit. Do not pass secret values through action inputs or write them to artifacts.

## Baseline and fail-on operation

`audit-baseline.json` is input policy in `mumei.audit-baseline/v1` format. `--write-baseline` refreshes the complete fingerprint set on every run, and `--fail-on high-confidence` fails the gate only for non-suppressed high-confidence code evidence. Audit exit `1` means finding-policy failure after a completed audit; exit `2` means operational or extraction failure. The composite action preserves the raw classification as `audit_exit_code` and fails only after writing artifacts and the summary.

The baseline is not evidence, does not remove findings from the underlying audit semantics, and must not participate in proof acceptance. Suppressions enter the repository only by human review of the generated baseline artifact.

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

Use that advanced reference when the adoption is ready to add `migration_plan.json`, a reviewed reference `.mm` certificate, a hash manifest, and explicit evidence-boundary metadata. The composite action is the shorter initial audit gate.

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

## Reviewer checklist

- Open `summary.md` first.
- Confirm the job used deterministic/no-LLM audit unless LLM extraction was explicitly approved.
- Confirm `audit.sarif` and `audit-baseline.json` are upstream CLI outputs, not repository-generated fabrications.
- Treat `audit-baseline.json` as `ci_policy`, not evidence, and review every suppression change.
- Treat `migration_plan.json` entries as `human_review_required`.
- Treat `reference.proof.json` as proof only for the reviewed reference `.mm` contract.
