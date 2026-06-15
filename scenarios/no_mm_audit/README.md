# No-.mm Entry: Audit Existing Python Code

This scenario demonstrates the first “write no `.mm` by hand” entry path.
`mumei-agent audit` inspects an existing Python `withdraw` implementation,
reports that the balance can go negative, then `migrate-suggest` generates a
Mumei skeleton that can become the formal contract.

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

Or invoke the runner directly:

```bash
./scripts/run_scenario.sh no_mm_audit \
  --mumei-repo ../mumei \
  --mumei-agent-repo ../mumei-agent
```

## Expected output

- `l1_audit/detect_bug: PASS`
- `detect_bug.log` contains `verification_violations` and
  `balance can go negative`
- `l2_migrate/generate_skeleton: PASS`
- `reports/no_mm_audit/latest/mm/withdraw.mm` contains a generated `withdraw`
  `atom` skeleton

The scenario’s purpose is to show that existing code can be audited first, then
migrated toward `.mm` contracts after a concrete bug has been found.
