# DeFi Invariants at Scale: Deep Reentrancy and Ownership

## Overview
`defi_invariant_scale` is the large-scale target of the `defi_invariant` scenario: 32 atoms at
dependency depth 5 (baseline: 2 atoms). It is a **separate
target** — it is not part of the deterministic fixture-mode scenario list, so
`make demo-ci` behaviour is unchanged.

Effect state machine (`Vault`):

```
Idle → Entered → Checked → Debited → Credited → Minted → Settled → Exited
```

## What the scale case exercises
- 再入ガード・呼び出し元認可・allowance / slippage / deadline の各検査
- 手数料込みの出金額計算と準備金ソルベンシー、シェア焼却の整合
- `withdrawal_cycle` / `two_withdrawal_cycles` による再入経路の周回合成

## Run it
```bash
make demo-defi-scale
```

## Evidence
| Step | Artifact | Gate |
|------|----------|------|
| `verify_scale` | `defi_invariant_scale.proof-cert.json` | every atom verified, certificate emitted |
| `verify_cert_strict` | — | `mumei verify-cert --strict` reports 0 changed / 0 unproven / 0 missing |
| `trust_surface` | `defi_invariant_scale.trust-surface.json` | application trusted atoms, FFI boundaries, Z3 solver time, Lean escalation counts, `budget_policy_fingerprint`; `std/` trusted atoms stay 0 |
| `composability` | `defi_invariant_scale.composability.json` | `atom_local_closure_ratio`, composition breaks, `modular_verification_inputs` |
| `agent_scale_report` | `defi_invariant_scale.scale-report.json` | composition breaks reported through the existing `verification_status` / `verification_violations` / `next_steps` keys |

## Composability
Every contract clause is removed one at a time and the resulting verification
failures are attributed back to atoms: a failure confined to the owning atom is
an atom-local obligation, a failure in another atom means that neighbour cannot
close its proof unless this contract is stronger than the owning atom needs
locally (a composition break). Break patterns are grouped as input for
`mumei-core` modular verification (`effect_pre` / `effect_post`).

## Measured (2026-08-28, `budget_policy_fingerprint: sha256:scale-default`)

| Metric | Value |
|--------|-------|
| atoms / certified atoms | 32 / 32 |
| max dependency depth | 5 |
| `verify-cert --strict` | pass |
| whole-system invariants (top-level atoms) | 2 closed from atom-local contracts, 1 lose closure when a neighbour contract is weakened |
| probed clauses | 190 |
| atom-local obligations / composition breaks | 40 / 48 |
| `atom_local_closure_ratio` | 0.4545 |
| application trusted atoms / FFI boundaries | 0 / 0 |
| Z3 unknown → Lean escalation atoms | 0 |
| Z3 solver time (verify + certificate) | 1.987s |
| `std/` trusted atoms | 0 |

Break patterns (modular verification input): `call_site_precondition` 16, `counterexample_replay_mismatch` 14, `effect_state_obligation` 11, `neighbor_ensures_strengthening` 7.

`counterexample_replay_mismatch` marks probes where weakening a neighbour
contract makes the solver report a model the body replay disagrees with, i.e.
a Z3 translation / Lean escalation surface rather than a missing neighbour
clause.
