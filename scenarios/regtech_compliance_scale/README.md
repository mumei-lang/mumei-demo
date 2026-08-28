# RegTech Compliance at Scale: Rule Combination Explosion

## Overview
`regtech_compliance_scale` is the large-scale target of the `regtech_compliance` scenario: 41 atoms at
dependency depth 7 (baseline: 5 atoms). It is a **separate
target** — it is not part of the deterministic fixture-mode scenario list, so
`make demo-ci` behaviour is unchanged.

Effect state machine (`ComplianceReview`):

```
Idle → Intake → Screened → Scored → RulesApplied → Decided → Reported → Archived
```

## What the scale case exercises
- `rule_and` / `rule_or` / `rule_implies` と 3〜5 入力コンビネータによる規則合成
- 12 個の個別規則 → 5 個の規則グループ → 単一のコンプライアンス判定
- スコアと残余リスクの有界性、`compliance_cycle` / `two_compliance_cycles`

## Run it
```bash
make demo-regtech-scale
```

## Evidence
| Step | Artifact | Gate |
|------|----------|------|
| `verify_scale` | `regtech_compliance_scale.proof-cert.json` | every atom verified, certificate emitted |
| `verify_cert_strict` | — | `mumei verify-cert --strict` reports 0 changed / 0 unproven / 0 missing |
| `trust_surface` | `regtech_compliance_scale.trust-surface.json` | application trusted atoms, FFI boundaries, Z3 solver time, Lean escalation counts, `budget_policy_fingerprint`; `std/` trusted atoms stay 0 |
| `composability` | `regtech_compliance_scale.composability.json` | `atom_local_closure_ratio`, composition breaks, `modular_verification_inputs` |
| `agent_scale_report` | `regtech_compliance_scale.scale-report.json` | composition breaks reported through the existing `verification_status` / `verification_violations` / `next_steps` keys |

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
| atoms / certified atoms | 41 / 41 |
| max dependency depth | 7 |
| `verify-cert --strict` | pass |
| whole-system invariants (top-level atoms) | 2 closed from atom-local contracts, 1 lose closure when a neighbour contract is weakened |
| probed clauses | 227 |
| atom-local obligations / composition breaks | 64 / 66 |
| `atom_local_closure_ratio` | 0.4923 |
| application trusted atoms / FFI boundaries | 0 / 0 |
| Z3 unknown → Lean escalation atoms | 0 |
| Z3 solver time (verify + certificate) | 2.105s |
| `std/` trusted atoms | 0 |

Break patterns (modular verification input): `call_site_precondition` 26, `counterexample_replay_mismatch` 20, `effect_state_obligation` 11, `neighbor_ensures_strengthening` 9.

`counterexample_replay_mismatch` marks probes where weakening a neighbour
contract makes the solver report a model the body replay disagrees with, i.e.
a Z3 translation / Lean escalation surface rather than a missing neighbour
clause.
