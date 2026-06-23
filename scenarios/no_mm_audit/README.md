# No-.mm Entry: Audit Existing Python Code

This scenario follows the same contract as `mumei-agent audit --code-file ... --auto-migrate --auto-heal` and MCP `scan_and_fix`.
The demo vocabulary is intentionally identical to the mumei-agent guide and appears in this order:

1. 既存コードを渡すだけでバグ箇所を指摘
2. 仕様から既存コードとの差分を指摘
3. 仕様単独でおかしい場合を指摘
4. `next_steps` as the only human-review entrypoint
5. `artifact_keys`
6. `harness_contract`

The execution order is fixed as `audit -> migrate-suggest -> heal`:

| Gate | User-facing wording | Required artifact keys |
| --- | --- | --- |
| `audit` | 既存コードを渡すだけでバグ箇所を指摘 | `verification_violations`, `next_steps` |
| `audit` | 仕様から既存コードとの差分を指摘 | `cross_validation_gaps`, `next_steps` |
| `audit` | 仕様単独でおかしい場合を指摘 | `spec_health_issues`, `contradiction_type`, `next_steps` |
| `migrate-suggest` | `.mm` skeleton 生成へ進む | `migration_hints` |
| `heal` | skeleton の復旧証跡を記録する | `healed_files`, `heal_errors` |

The first three rows are still the `audit` gate; migration and healing evidence must not appear before those audit findings and `next_steps` are available. The scenario JSON records `canonical_demo_phrases`, `next_steps`, `artifact_keys`, and `harness_contract` in that review order. The scenario result uses `harness_contract`, `intent_fidelity`, `artifact_paths`, and `budget_policy_fingerprint` with the same meanings as the cross-project roadmap; no `lean_verified` artifact is expected because this no-`.mm` demo stops before Lean escalation.

- `audit` accepts existing Python code, extracts candidate contracts, and emits `spec_health_issues`, `verification_violations`, and `cross_validation_gaps`.
- `migrate-suggest` turns the audited violation/gap into `.mm` skeleton guidance under `migration_hints`.
- `heal` operates only on generated skeletons and records `healed_files` or `heal_errors`.

## Input

`buggy_payment.py` intentionally omits the guard for `amount > balance`:

```python
def withdraw(balance: int, amount: int) -> int:
    """Withdraw amount from balance. Should fail if amount > balance."""
    return balance - amount  # Bug: no check for amount > balance
```

## Run

```bash
make demo-no-mm
```

`make demo-no-mm` defaults to fixture mode so it can run in CI without live LLM credentials.
To exercise live mumei-agent commands, set `CI_FIXTURE_MODE=0` and provide the agent’s configured LLM credentials.

Invoke the runner directly in fixture mode:

```bash
CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh no_mm_audit \
  --mumei-repo ../mumei \
  --mumei-agent-repo ../mumei-agent
```

## Expected output

- `l1_audit/detect_bug: PASS`
- `detect_bug.log` contains `verification_violations` and `balance can go negative`
- `detect_bug.log` contains `cross_validation_gaps` for the spec/code difference and preserves `spec_health_issues` for spec-only issues
- `l2_migrate/generate_skeleton: PASS`
- `reports/no_mm_audit/latest/mm/withdraw.mm` contains a generated `withdraw` `atom` skeleton
- `l3_heal/record_heal_contract: PASS`
- `record_heal_contract.log` contains `healed_files` and `heal_errors`

The scenario shows that existing code can be audited first, the spec/code difference can be explained second, spec-only contradictions can use the same vocabulary third, and migration toward `.mm` contracts happens through skeleton generation before any healing evidence is accepted.
