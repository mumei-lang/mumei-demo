# Ownership Transfer at Scale: Authority and Escrow Chains

## Overview
`ownership_transfer_scale` is the large-scale target of the `ownership_transfer` scenario: 35 atoms at
dependency depth 6 (baseline: 5 atoms). It is a **separate
target** — it is not part of the deterministic fixture-mode scenario list, so
`make demo-ci` behaviour is unchanged.

Effect state machine (`Ownership`):

```
Idle → Proposed → Acknowledged → Escrowed → Approved → Transferred → Recorded → Disputed
```

## What the scale case exercises
- 提案者権限・受領者適格性・ブラックリスト・定足数・タイムロックの積み上げ
- エスクロー資金化と移転記録、係争解決経路
- `handover_cycle` / `two_handover_cycles` による周回合成

## Run it
```bash
make demo-ownership-scale
```

## Evidence
| Step | Artifact | Gate |
|------|----------|------|
| `verify_scale` | `ownership_transfer_scale.proof-cert.json` | every atom verified, certificate emitted |
| `verify_cert_strict` | — | `mumei verify-cert --strict` reports 0 changed / 0 unproven / 0 missing |
| `trust_surface` | `ownership_transfer_scale.trust-surface.json` | application trusted atoms, FFI boundaries, Z3 solver time, Lean escalation counts, `budget_policy_fingerprint`; `std/` trusted atoms stay 0 |
| `composability` | `ownership_transfer_scale.composability.json` | `atom_local_closure_ratio`, composition breaks, `modular_verification_inputs` |
| `agent_scale_report` | `ownership_transfer_scale.scale-report.json` | composition breaks reported through the existing `verification_status` / `verification_violations` / `next_steps` keys |

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
| atoms / certified atoms | 35 / 35 |
| max dependency depth | 6 |
| `verify-cert --strict` | pass |
| whole-system invariants (top-level atoms) | 5 closed from atom-local contracts, 2 lose closure when a neighbour contract is weakened |
| probed clauses | 214 |
| atom-local obligations / composition breaks | 61 / 54 |
| `atom_local_closure_ratio` | 0.5304 |
| application trusted atoms / FFI boundaries | 0 / 0 |
| Z3 unknown → Lean escalation atoms | 0 |
| Z3 solver time (verify + certificate) | 1.97s |
| `std/` trusted atoms | 0 |

Break patterns (modular verification input): `call_site_precondition` 14, `counterexample_replay_mismatch` 20, `effect_state_obligation` 12, `neighbor_ensures_strengthening` 8.

`counterexample_replay_mismatch` marks probes where weakening a neighbour
contract makes the solver report a model the body replay disagrees with, i.e.
a Z3 translation / Lean escalation surface rather than a missing neighbour
clause.
