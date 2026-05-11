# Smart Contract Audit: Reentrancy Guard

Phase 4 demo scenario for auditing a withdrawal flow with a reentrancy guard.

The buggy implementation calls `external_call` while the `ReentrancyGuard`
effect is still `Unlocked`, so temporal verification rejects it with
`InvalidPreState`. The corrected implementation follows
Checks-Effects-Interactions: it locks the guard, updates the balance, performs
the external interaction, unlocks, and returns the updated balance.
The scenario also runs the companion agent forge dry-run for
`std/math/patterns.mm`, then builds the Lean smart-contract proof module.

Run:

```bash
./scripts/run_scenario.sh smart_contract_audit \
  --mumei-repo ../mumei \
  --mumei-lean-repo ../mumei-lean \
  --mumei-bin ../mumei/target/debug/mumei
```
