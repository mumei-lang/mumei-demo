# RTGS Settlement at Scale: Finality and Balance Chains

## Overview
`rtgs_settlement_scale` is the large-scale target of the `rtgs_settlement` scenario: 30 atoms at
dependency depth 5 (baseline: 4 atoms). It is a **separate
target** — it is not part of the deterministic fixture-mode scenario list, so
`make demo-ci` behaviour is unchanged.

Effect state machine (`Settlement`):

```
Idle → Submitted → Validated → Reserved → Netted → Posted → Finalized → Reconciled
```

## What the scale case exercises
- 流動性予約・ネッティング・ポスティング・ファイナリティ・照合の 8 状態連鎖
- 各段での残高保存（`conserved_total`）と決済上限の同時保持
- `settlement_cycle` / `two_settlement_cycles` による周回合成

## Run it
```bash
make demo-settlement-scale
```

## Evidence
| Step | Artifact | Gate |
|------|----------|------|
| `verify_scale` | `rtgs_settlement_scale.proof-cert.json` | every atom verified, certificate emitted |
| `verify_cert_strict` | — | `mumei verify-cert --strict` reports 0 changed / 0 unproven / 0 missing |
| `trust_surface` | `rtgs_settlement_scale.trust-surface.json` | application trusted atoms, FFI boundaries, Z3 solver time, Lean escalation counts, `budget_policy_fingerprint`; `std/` trusted atoms stay 0 |
| `composability` | `rtgs_settlement_scale.composability.json` | `atom_local_closure_ratio`, composition breaks, `modular_verification_inputs` |
| `agent_scale_report` | `rtgs_settlement_scale.scale-report.json` | composition breaks reported through the existing `verification_status` / `verification_violations` / `next_steps` keys |

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
| atoms / certified atoms | 30 / 30 |
| max dependency depth | 5 |
| `verify-cert --strict` | pass |
| whole-system invariants (top-level atoms) | 4 closed from atom-local contracts, 3 lose closure when a neighbour contract is weakened |
| probed clauses | 187 |
| atom-local obligations / composition breaks | 44 / 47 |
| `atom_local_closure_ratio` | 0.4835 |
| application trusted atoms / FFI boundaries | 0 / 0 |
| Z3 unknown → Lean escalation atoms | 0 |
| Z3 solver time (verify + certificate) | 1.317s |
| `std/` trusted atoms | 0 |

Break patterns (modular verification input): `call_site_precondition` 9, `counterexample_replay_mismatch` 16, `effect_state_obligation` 12, `neighbor_ensures_strengthening` 10.

`counterexample_replay_mismatch` marks probes where weakening a neighbour
contract makes the solver report a model the body replay disagrees with, i.e.
a Z3 translation / Lean escalation surface rather than a missing neighbour
clause.
