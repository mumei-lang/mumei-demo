# Focused fixture scenarios (no_mm_audit, spec_code_verification_suite)

Read this when a change touches `scenarios/no_mm_audit/*`, `scenarios/spec_code_verification_suite/*`, or the cross-repo no-`.mm` audit/spec-code docs and you need the focused run commands and expected assertions.

## No-.mm audit scenario validation

Use this focused fixture run when changes touch `scenarios/no_mm_audit/*`, mumei-agent no-`.mm` audit vocabulary, or cross-repo `audit -> migrate-suggest -> heal` contract docs. It requires no browser session or API secrets.

```bash
cd /home/ubuntu/repos/mumei-demo
rm -rf reports/no_mm_audit
CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh no_mm_audit \
  --mumei-repo ../mumei \
  --mumei-agent-repo ../mumei-agent
```

Expected assertions:

- Command exits `0`.
- Output includes `l1_audit/detect_bug: PASS`, `l2_migrate/generate_skeleton: PASS`, and `l3_heal/record_heal_contract: PASS`.
- Output includes `Harness Contract: COMPLIANT (8/8)`.
- `reports/no_mm_audit/latest/result.json` has `overall_status == "PASS"`.
- `reports/no_mm_audit/latest/result.json` has `harness_contract.acceptance_path == ["l1_audit", "l2_migrate", "l3_heal"]`.
- `reports/no_mm_audit/latest/mm/withdraw.mm` exists and contains both `atom` and `withdraw`.
- `reports/no_mm_audit/latest/record_heal_contract.log` contains `healed_files`, `heal_errors`, and `withdraw.mm`.

Clean up generated reports after collecting evidence if you are going to commit repo changes:

```bash
rm -rf reports/no_mm_audit
```


## Phase 7 Spec-Code Verification Suite validation

Use this focused fixture run when changes touch `scenarios/spec_code_verification_suite/*`, no-`.mm` spec/code verification docs, or V1-A through V1-D mode mapping. It requires no browser session or API secrets.

```bash
cd /home/ubuntu/repos/mumei-demo
rm -rf reports/spec_code_verification_suite
CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh spec_code_verification_suite \
  --mumei-repo ../mumei \
  --mumei-agent-repo ../mumei-agent
python3 dashboard/cli_report.py reports/spec_code_verification_suite/latest/result.json
```

Expected assertions:

- Command exits `0`.
- Output includes `mode_a/validate_spec_health: PASS`, `mode_b/verify_existing_code: PASS`, `mode_c/verify_spec_to_code_conformance: PASS`, and `mode_d/validate_code_to_spec_traceability: PASS`.
- Output includes `Harness Contract: COMPLIANT (8/8)`.
- `reports/spec_code_verification_suite/latest/result.json` has `overall_status == "PASS"`.
- `reports/spec_code_verification_suite/latest/result.json` has `harness_contract.acceptance_path == ["mode_a", "mode_b", "mode_c", "mode_d"]`.
- `reports/spec_code_verification_suite/latest/result.json` has `proof_density.percentage == 100`.
- `dashboard/cli_report.py reports/spec_code_verification_suite/latest/result.json` renders the four mode rows and 100% proof density.

Clean up generated reports after collecting evidence if you are going to commit repo changes:

```bash
rm -rf reports/spec_code_verification_suite
```
