# Medical Device Control at Scale: Multi-Stage Insulin Pump

## Overview
`medical_device_scale` is the large-scale target of the `medical_device` scenario: 34 atoms at
dependency depth 7 (baseline: 3 atoms). It is a **separate
target** — it is not part of the deterministic fixture-mode scenario list, so
`make demo-ci` behaviour is unchanged.

Effect state machine (`InsulinPump`):

```
Idle → SelfTested → SensorsValidated → ProfileLoaded → DoseComputed → LimitsChecked → InterlockArmed → Delivered
```

## What the scale case exercises
- 8 段の effect 状態機械（self-test から interlock まで）を通した投与シーケンス
- 1 時間あたり総投与量・単回投与上限・センサ整合性の同時保持
- phase / cycle atom による多段合成（`therapy_cycle`, `two_therapy_cycles`）

## Run it
```bash
make demo-medical-scale
```

## Evidence
| Step | Artifact | Gate |
|------|----------|------|
| `verify_scale` | `medical_device_scale.proof-cert.json` | every atom verified, certificate emitted |
| `verify_cert_strict` | — | `mumei verify-cert --strict` reports 0 changed / 0 unproven / 0 missing |
| `trust_surface` | `medical_device_scale.trust-surface.json` | application trusted atoms, FFI boundaries, Z3 solver time, Lean escalation counts, `budget_policy_fingerprint`; `std/` trusted atoms stay 0 |
| `composability` | `medical_device_scale.composability.json` | `atom_local_closure_ratio`, composition breaks, `modular_verification_inputs` |
| `agent_scale_report` | `medical_device_scale.scale-report.json` | composition breaks reported through the existing `verification_status` / `verification_violations` / `next_steps` keys |

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
| atoms / certified atoms | 34 / 34 |
| max dependency depth | 7 |
| `verify-cert --strict` | pass |
| whole-system invariants (top-level atoms) | 3 closed from atom-local contracts, 2 lose closure when a neighbour contract is weakened |
| probed clauses | 196 |
| atom-local obligations / composition breaks | 62 / 62 |
| `atom_local_closure_ratio` | 0.5 |
| application trusted atoms / FFI boundaries | 0 / 0 |
| Z3 unknown → Lean escalation atoms | 0 |
| Z3 solver time (verify + certificate) | 2.391s |
| `std/` trusted atoms | 0 |

Break patterns (modular verification input): `call_site_precondition` 21, `counterexample_replay_mismatch` 16, `effect_state_obligation` 12, `neighbor_ensures_strengthening` 13.

`counterexample_replay_mismatch` marks probes where weakening a neighbour
contract makes the solver report a model the body replay disagrees with, i.e.
a Z3 translation / Lean escalation surface rather than a missing neighbour
clause.
