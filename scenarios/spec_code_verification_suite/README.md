# Phase 7 Spec-Code Verification Suite

This scenario implements the V1-E-4 Phase 7 demo from the cross-project roadmap. It keeps the no-`.mm` entrance in front: reviewers start with `spec.txt` and `buggy_payment.py`, then see V1-A through V1-D as one deterministic review flow before any migration or Lean escalation.

The story is "仕様のバグを証明で潰す": prove the specification is internally healthy, prove existing code violates the intended contract, prove the spec→code gaps, and prove the code→spec drift before accepting `.mm` migration work.

## Modes

| Gate | V1 mode | mumei-agent CLI correspondence | Required evidence |
| --- | --- | --- | --- |
| `mode_a` | V1-A spec-only health | `mumei-agent validate-spec --input spec.txt --format human` (V1-A verify-spec role) | `spec_health_issues`, `contradiction_type`, `next_steps` |
| `mode_b` | V1-B existing-code audit | `mumei-agent validate-code --input buggy_payment.py --language python` (V1-B verify-code role) | `verification_violations`, `next_steps` |
| `mode_c` | V1-C spec→code conformance | `mumei-agent verify-conformance --spec spec.txt --code buggy_payment.py --format human` | `unimplemented_conditions`, `hidden_specifications`, `traceability_matrix`, `cross_validation_gaps`, `next_steps` |
| `mode_d` | V1-D code→spec drift | `mumei-agent validate-code-to-spec` / `verify-traceability --code buggy_payment.py --spec spec.txt --format human` | `spec_gaps`, `drift_issues`, `drift_score`, `cross_validation_gaps`, `next_steps` |

The canonical demo phrases stay fixed and visible:

1. 既存コードを渡すだけでバグ箇所を指摘
2. 仕様から既存コードとの差分を指摘
3. 仕様単独でおかしい場合を指摘

`next_steps` is the only human-review entrypoint in every mode. The fixed no-`.mm` vocabulary remains unchanged: `spec_health_issues`, `verification_violations`, `cross_validation_gaps`, `next_steps`, `migration_hints`, `healed_files`, and `heal_errors`. This scenario records `migration_hints`, `healed_files`, and `heal_errors` as post-review contract keys but does not run migration or healing before `next_steps` review.

## Relationship to audit -> migrate-suggest -> heal

The existing `no_mm_audit` scenario remains the regression point for `audit -> migrate-suggest -> heal`. This Phase 7 suite does not replace it. Instead, it visualizes the four V1 verification modes that precede a migration decision. After reviewers accept `next_steps`, the usual `migrate-suggest` / `heal` path still owns `migration_hints`, `healed_files`, and `heal_errors`.

No `lean_verified` artifact is expected because this demo stops before Lean escalation; mumei-lean remains the Z3 `unknown` complement only.

## Run

```bash
make demo-spec-code
```

`make demo-spec-code` defaults to `CI_FIXTURE_MODE=1`, so it runs deterministically in CI without LLM credentials:

```bash
CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh spec_code_verification_suite \
  --mumei-repo ../mumei \
  --mumei-agent-repo ../mumei-agent
python dashboard/cli_report.py reports/spec_code_verification_suite/latest/result.json
```

Set `CI_FIXTURE_MODE=0` to exercise the live mumei-agent commands shown in the table above.

## Expected output

- `mode_a/validate_spec_health: PASS`
- `mode_b/verify_existing_code: PASS`
- `mode_c/verify_spec_to_code_conformance: PASS`
- `mode_d/validate_code_to_spec_traceability: PASS`
- `Harness Contract: COMPLIANT (8/8)`
- `reports/spec_code_verification_suite/latest/result.json` contains `harness_contract`, `intent_fidelity`, `artifact_paths`, and `budget_policy_fingerprint`
