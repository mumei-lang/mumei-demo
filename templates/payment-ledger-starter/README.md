# Payment/ledger audit starter

This directory is a repo-root-shaped starter for the first existing-code audit gate. Copy its contents into a throwaway consumer repository root, preserving the `.github` directory, then open a pull request. The included workflow audits a small stdlib-only Python payment/ledger fixture, uploads the evidence artifact, downloads that artifact in a separate job, and verifies the downloaded artifact without re-running proof certificates.

## Ten-minute path

A maintainer can reach **evidence generation and review-handoff confirmation** in about ten minutes on a small repository. That does not mean the human migration review is complete in ten minutes; reviewing the candidate contract and deciding whether to migrate remains human work. The first uncached run can also take longer while Python, uv dependencies, and the mumei installer are populated.

Expected fixture-smoke result:

- audit exits without a failing high-confidence finding;
- one high-priority migration hint names `split_cents`;
- one migration execution candidate named `split_cents` is in `blocked` state;
- `review_required` is `true`;
- the strict downloaded-artifact verification job passes.

`blocked` is retained review evidence, not an operational failure of the action.

## Required inputs and permissions

The starter pins both the composite action and the artifact verifier script to commit `640d597ec60bf574d0102cae6b89054d47fd9f0f`. Keep those two commit references identical when updating them. `uses:` cannot interpolate an environment variable, so the duplication must be reviewed manually or by repository tests.

The audit job uses only `contents: read`. The verification job adds `actions: read` so it can download the artifact. `upload-sarif` is `false` because code scanning is optional. To publish SARIF to code scanning, enable GitHub code scanning, add `security-events: write` to the audit job, and set `upload-sarif: true`; the SARIF file is already present in the evidence artifact either way.

No LLM secret is required. The workflow explicitly sets `LLM_API_KEY` and `OPENAI_API_KEY` to empty strings for the action step so repository- or organization-level secrets do not silently change the adoption gate into an LLM-backed audit. Do not pass secret values through action inputs.

`migration_execution.json` is a fresh workspace-local `.json` output on each run. Do not commit or cache `.mumei-audit/` outputs.

## Applying it to real source

The fixture smoke is intentionally narrow. After it proves the path in a throwaway repository:

1. Delete `src/payment_ledger.py` or replace it with the repository's own payment/ledger code.
2. Point `code-file` at that source tree and adjust `language` if needed.
3. Delete the `Validate expected payment fixture handoff` step.
4. Adjust or remove the strict artifact-verifier flags. `--require-hidden-companion`, `--require-blocked-candidate`, and `--require-generated-mm` are fixture-smoke requirements. The current upstream verifier also expects at least one blocked or ready migration candidate; a zero-candidate real-repository artifact is outside that verifier contract and must not be interpreted as a failure of verification or proof.
5. Keep `migration-execution-output` enabled when migration evidence is wanted. Candidate-level `operational_error` fails the composite action as consumer policy; `blocked` and `ready_for_human_review` remain review evidence and do not independently fail CI.

## Baseline and review handoff

`audit-baseline.json` is input policy in `mumei.audit-baseline/v1` format. The starter begins with an empty fingerprint list. `--write-baseline` refreshes `.mumei-audit/generated-baseline.json` in every run. Review that artifact, and only commit it as `audit-baseline.json` when the suppressed fingerprints are accepted as repository policy. Baseline suppression is CI policy, not evidence, and should receive explicit human review; protecting it with CODEOWNERS is recommended for production adoption.

Review `migration-execution/migration_execution.json`, `migration-execution/status.json`, and copied files under `migration-execution/generated-artifacts/` before acting on a migration candidate. Treat `ready_for_human_review` as a review queue, not permission to merge generated code. Treat `blocked` as retained evidence gaps for a human.

For the payment fixture, review at least:

- whether `recipient_count > 0` must become an explicit precondition or runtime validation for payout splitting;
- the integer-split remainder policy in `payout_summary`;
- account-existence, negative-amount, and non-negative-balance requirements in `transfer_cents`.

## Evidence boundaries

Migration execution evidence is generated `.mm` acceptance evidence only. It is not proof that the host-language Python implements the same behavior. `contract_erosion`, when present in the pinned artifact, is additive tool-execution provenance rather than proof acceptance; `skipped_no_change` is explicit not-checked evidence, not success evidence.

The artifact verifier applies to artifacts produced with migration execution output and baseline generation enabled. It checks accidental corruption, missing files, count mismatches, path/hash mismatches, hidden companion loss, and role boundaries in the downloaded action artifact. After the pinned script is fetched, verification reads only local artifact files. It is an offline corruption/consistency check, not a malicious-tamper trust anchor, and it does not independently re-run proof certificates.

Native distribution verification is a later stage for trusted `.mm` native bundles. Exact bundle layout and trusted build-ID validation intentionally are not part of this starter; see the [native distribution verification reference](https://github.com/mumei-lang/mumei-demo/blob/main/docs/CI_REFERENCE.md#native-distribution-verification-reference) only after the audit/migration adoption path is working.
