# RTGS Settlement Protocol

> Mumei detects bugs in LLM-generated RTGS settlement code using formal verification.

## BEFORE: LLM alone

The user asks an LLM to implement RTGS settlement. The generated code looks
plausible, but `hostile_settlement` attempts to enter `Settled` from `Pending`
without passing through `Validated` — skipping the balance validation step.

```text
Pending ── hostile_settlement ──▶ Settled
```

This is the production failure mode: a transaction settles without verifying
that the sender has sufficient funds.

## AFTER: LLM + mumei

`mumei verify scenarios/rtgs_settlement/buggy_code.mm` rejects the code:

```text
InvalidPreState: 'settle' requires 'Validated'
but current state is 'Pending'
Counter-example: hostile_settlement(sender_balance=0, receiver_balance=100, amount=50)
```

The bug is caught before deployment.

## CERTIFIED: Lean proof

`correct_code.mm` implements the intended protocol:

```text
Pending ── validate ──▶ Validated ── settle ──▶ Settled
```

Z3 verifies all settlement atoms including balance conservation
(`(sender - amount) + (receiver + amount) == sender + receiver`),
and `mumei-lean` proves:
- `no_settlement_without_validate`: Settled is unreachable without validate
- `balance_conservation`: global balance sum is invariant across any transfer trace

## Run

```bash
make demo-settlement
```

Expected story:

1. LLM generates RTGS settlement code.
2. mumei detects the invalid pre-state (validate skipped).
3. The corrected implementation verifies (balance conservation proved by Z3).
4. Lean certifies the temporal safety and global balance conservation proofs.

## Dashboard recording

The recorded dashboard walkthrough is available at
[`docs/assets/rtgs-settlement-dashboard-demo.mp4`](../../docs/assets/rtgs-settlement-dashboard-demo.mp4).

It shows:

- `rtgs_settlement` selected in the Streamlit dashboard.
- L1/L2/L3 layer status cards all reporting `PASS`.
- Proof density at `100% (6/6 atoms)`.
- The rejected `hostile_settlement` log showing `InvalidPreState`.
- `settlement.proof.json` and `settlement.lean-cert.json` proof artifacts.
