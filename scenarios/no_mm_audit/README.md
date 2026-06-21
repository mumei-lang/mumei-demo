# No-.mm Entry: Audit Existing Python Code

This scenario demonstrates the first “write no `.mm` by hand” entry path.
The demo vocabulary is intentionally identical to the CLI output:

1. 既存コードを渡すだけでバグ箇所を指摘
2. 仕様から既存コードとの差分を指摘
3. 仕様単独でおかしい場合を指摘

`mumei-agent audit` inspects an existing Python `withdraw` implementation,
emits `spec_health_issues`, `verification_violations`,
`cross_validation_gaps`, `next_steps`, `migration_hints`, `healed_files`, and
`heal_errors`, then `migrate-suggest` generates a Mumei skeleton that can
become the formal contract.

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

`make demo-no-mm` defaults to fixture mode so it can run in CI without live LLM
credentials. To exercise the live `mumei-agent audit` command, set
`CI_FIXTURE_MODE=0` and provide the agent’s configured LLM credentials.

Invoke the runner directly in fixture mode:

```bash
CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh no_mm_audit \
  --mumei-repo ../mumei \
  --mumei-agent-repo ../mumei-agent
```

## Expected output

- `l1_audit/detect_bug: PASS`
- `detect_bug.log` contains `verification_violations` and
  `balance can go negative`
- `detect_bug.log` contains `cross_validation_gaps` for the spec/code
  difference and preserves `spec_health_issues` for spec-only issues
- `l2_migrate/generate_skeleton: PASS`
- `reports/no_mm_audit/latest/mm/withdraw.mm` contains a generated `withdraw`
  `atom` skeleton

The scenario’s purpose is to show that existing code can be audited first, the
spec/code difference can be explained second, spec-only contradictions can use
the same vocabulary third, and migration toward `.mm` contracts can happen only
after a concrete bug has been found.
