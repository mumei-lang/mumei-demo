# Ownership Transfer Protocol

> Mumei detects bugs in LLM-generated ownership-transfer code using formal verification.

## BEFORE: LLM alone

The user asks an LLM to implement ownership transfer. The generated code looks
plausible, but `hostile_takeover` attempts to enter `Transferred` from `Idle`
without a valid pending transfer.

```text
Idle ── hostile_takeover ──▶ Transferred
```

This is the production failure mode: an attacker becomes owner without the
intended propose → accept handshake.

## AFTER: LLM + mumei

`mumei verify scenarios/ownership_transfer/buggy_code.mm` rejects the code:

```text
InvalidPreState: 'accept' requires 'PendingTransfer'
but current state is 'Idle'
Counter-example: hostile_takeover(attacker=42)
```

The bug is caught before deployment.

## CERTIFIED: Lean proof

`correct_code.mm` implements the intended protocol:

```text
Idle ── propose ──▶ PendingTransfer ── accept ──▶ Transferred
```

Z3 verifies all five ownership atoms, and `mumei-lean` proves
`no_transfer_without_accept`: transfer cannot be derived from traces that omit a
valid `accept`.

## Run

```bash
make demo-ownership
```

Use `make demo` for the integrated all-scenario sequence.

Expected story:

1. LLM generates ownership transfer code.
2. mumei detects the invalid pre-state.
3. The corrected implementation verifies.
4. Lean certifies the unreachability proof.
