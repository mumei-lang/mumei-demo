# Payment/ledger audit starter

This directory is a repo-root-shaped starter for the first existing-code audit gate. Copy its contents into a throwaway consumer repository root, preserving the `.github` directory, then open a pull request. From a `mumei-demo` checkout, one copy command is:

```bash
cp -a templates/payment-ledger-starter/. /path/to/consumer-repo/
```

The `.github` directory is hidden by default in many file browsers and shell listings; confirm that `.github/workflows/mumei-audit.yml` exists in the consumer repository before opening the pull request. The included workflow audits a small stdlib-only Python payment/ledger fixture, uploads the evidence artifact, downloads that artifact in a separate job, and verifies the downloaded artifact without re-running proof certificates.

This README is the minimal starter runbook. The [GitHub Actions CI reference](https://github.com/mumei-lang/mumei-demo/blob/main/docs/CI_REFERENCE.md) is the canonical detailed reference for artifact entries, step outputs, baseline operation, migration states, and evidence boundaries.

For the first real consumer pilot, follow the [fresh consumer pilot runbook](https://github.com/mumei-lang/mumei-demo/blob/main/docs/CI_REFERENCE.md#fresh-consumer-pilot-runbook): use a dedicated private throwaway repository, push the starter to `main`, then open a pull request from a pilot branch because the workflow does not run on the initial `main` push alone.

## Ten-minute path

A maintainer can reach **evidence generation and review-handoff confirmation** in about ten minutes on a small repository. That does not mean the human migration review is complete in ten minutes; reviewing the candidate contract and deciding whether to migrate remains human work. The first uncached run can also take longer while Python, uv dependencies, and the mumei installer are populated.

This is a GitHub Actions CI-first path. The composite action provisions Python, uv, and the mumei toolchain on the runner; the consumer workstation does not need Rust, Z3, LLVM, or sibling `mumei` repositories. `make setup` in `mumei-demo` is maintainer setup for developing that repository, not a consumer prerequisite, and full local reproduction of composite-action artifact semantics is outside this ten-minute path.

Expected fixture-smoke result:

- audit exits without a failing high-confidence finding;
- one high-priority migration hint names `split_cents`;
- one migration execution candidate named `split_cents` is in `blocked` state;
- `review_required` is `true`;
- the strict downloaded-artifact verification job passes.

`blocked` is retained review evidence, not an operational failure of the action.

The starter passes `--fail-on high-confidence`. A passing audit means only that no non-suppressed high-confidence code evidence failed the gate; it does not mean that there are no findings, no model limitations, or proof success. Audit exit `1` is finding-policy failure after a completed audit, while exit `2` is operational or extraction failure. See the [baseline and fail-on reference](https://github.com/mumei-lang/mumei-demo/blob/main/docs/CI_REFERENCE.md#baseline-and-fail-on-operation) before tuning the gate.

The downloaded-artifact verification job is positive-path fixture smoke. Because it depends on the audit job, GitHub Actions can skip it when the audit job fails; in that case inspect any uploaded `mumei-audit-evidence` artifact manually rather than treating the skipped smoke as artifact validation.

## Required inputs and permissions

The starter pins both the composite action and the artifact verifier script to commit `602404277af9ba6c0a6031efe800c517f1ddc93c`. Keep those two commit references identical when updating them. `uses:` cannot interpolate an environment variable, so the duplication must be reviewed manually or by repository tests.

The audit job uses only `contents: read`. The verification job adds `actions: read` so it can download the artifact. `upload-sarif` is `false` because code scanning is optional. To publish SARIF to code scanning, enable GitHub code scanning, set `upload-sarif: true`, and give the audit job a permissions block that keeps checkout access while adding code-scanning access:

```yaml
permissions:
  contents: read
  security-events: write
```

The SARIF file is already present in the evidence artifact either way.

No LLM secret is required. The workflow explicitly sets `LLM_API_KEY` and `OPENAI_API_KEY` to empty strings for the action step so repository- or organization-level secrets do not silently change the adoption gate into an LLM-backed audit. Do not pass secret values through action inputs.

`migration_execution.json` is a fresh workspace-local `.json` output on each run. Do not commit or cache `.mumei-audit/` outputs.

## Applying it to real source

The fixture smoke is intentionally narrow. After it proves the path in a throwaway repository:

1. Delete `src/payment_ledger.py` or replace it with the repository's own payment/ledger code.
2. Point `code-file` at that source tree and adjust `language` if needed.
3. Delete the `Validate expected payment fixture handoff` step.
4. Adjust the strict artifact-verifier flags for the repository policy. `--require-blocked-candidate` and `--require-generated-mm` are positive fixture-smoke requirements. If zero candidates are acceptable for real source, remove those two positive-only flags, keep `--require-hidden-companion`, and add `--allow-zero-candidates`; this preserves artifact envelope, zero-count, schema, boundary, provenance, companion, hidden-file, and configured forbidden-literal validation; an empty candidate list has no generated `.mm` candidate claims, while nonzero candidate claims remain path/hash validated. Do not interpret zero candidates as proof failure or proof success. If migration candidates are required, omit `--allow-zero-candidates` and keep an appropriate positive-candidate assertion instead.
5. Keep `migration-execution-output` enabled when migration evidence is wanted. Candidate-level `operational_error` fails the composite action as consumer policy; `blocked` and `ready_for_human_review` remain review evidence and do not independently fail CI.

## Baseline and review handoff

`audit-baseline.json` is input policy in `mumei.audit-baseline/v1` format. The starter begins with an empty fingerprint list. `--write-baseline` refreshes `.mumei-audit/generated-baseline.json` in the runner workspace on every run; it does not update the committed input baseline automatically. In the downloaded evidence artifact, review the root `generated-baseline.json` entry. Only after a human accepts those suppressions as repository policy, copy that reviewed content into `audit-baseline.json` and commit it. Baseline suppression is CI policy, not evidence, and should receive explicit human review; protecting it with CODEOWNERS is recommended for production adoption.

Review `migration-execution/migration_execution.json`, `migration-execution/status.json`, and copied files under `migration-execution/generated-artifacts/` before acting on a migration candidate. Paths embedded inside `migration_execution.json` are runner/workspace provenance, not portable links in the downloaded artifact; use the copied companion files instead. Treat `ready_for_human_review` as a review queue, not permission to merge generated code. Treat `blocked` as retained evidence gaps for a human.

For the payment fixture, review at least:

- whether `recipient_count > 0` must become an explicit precondition or runtime validation for payout splitting;
- the integer-split remainder policy in `payout_summary`;
- account-existence, negative-amount, and non-negative-balance requirements in `transfer_cents`.

## Evidence boundaries

Migration execution evidence is generated `.mm` acceptance evidence only. It is not proof that the host-language Python implements the same behavior. `contract_erosion`, when present in the pinned artifact, is additive tool-execution provenance rather than proof acceptance; `skipped_no_change` is explicit not-checked evidence, not success evidence.

The artifact verifier applies to artifacts produced with migration execution output and baseline generation enabled. It checks accidental corruption, missing files, count mismatches, path/hash mismatches, hidden companion loss, and role boundaries in the downloaded action artifact. After the pinned script is fetched, verification reads only local artifact files. It is an offline corruption/consistency check, not a malicious-tamper trust anchor. It does not establish artifact producer authenticity, does not prove host-language semantic equivalence, and does not independently re-run proof certificates or otherwise guarantee proof correctness.

Native distribution verification is a later stage for trusted `.mm` native bundles. Exact bundle layout and trusted build-ID validation intentionally are not part of this starter; see the [native distribution verification reference](https://github.com/mumei-lang/mumei-demo/blob/main/docs/CI_REFERENCE.md#native-distribution-verification-reference) only after the audit/migration adoption path is working.
