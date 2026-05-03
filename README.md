# Mumei Demo

> **Mumei proves that LLM-generated code has bugs — mathematically.**

## The Problem

LLMs write code that looks correct but contains subtle bugs.  
Formal verification checks **every possible case**

## Why Mumei? (Not Just Lean)

Lean 4 is powerful, but using it well requires learning theorem-proving tactics.
That is hard for humans and brittle for AI agents: the model must generate both
the program and a proof script.

mumei takes the opposite path for everyday verification: it is the Z3-based
automatic verification engine, while Lean 4 is an optional complement. You write
normal atoms with `requires` and `ensures`, plus effect/state contracts. mumei
lowers those contracts into SMT constraints and asks Z3 to prove them
automatically.

| Dimension | Lean 4 | Mumei |
| --- | --- | --- |
| Difficulty | Requires tactic and proof-script knowledge | Write `requires` / `ensures` constraints |
| Automation | Powerful, but often proof-guided | Automatic Z3 verification by default |
| AI-friendly | AI must synthesize fragile proofs | AI writes code + contracts; solver checks them |
| Output | Theorem/proof artifacts | Verified atoms, counter-examples, LLVM-ready code |

## See It In Action

```text
User request
    ↓
LLM generates mumei atom
    ↓
mumei verify (Z3)
    ├── Proven safe ──▶ LLVM binary
    └── Bug found ───▶ Counter-example ───▶ AI fixes code

Optional safety net:
Lean 4 proves obligations that Z3 cannot decide
```

### ❌ Without Mumei

```text
User: "Implement ownership transfer"
LLM:  Generates code that skips the accept step
      → Deployed to production
      → Attacker takes over the contract
```

### ✅ With Mumei

```text
User: "Implement ownership transfer"
LLM:  Generates code that skips the accept step
mumei: ❌ InvalidPreState: 'accept' requires 'PendingTransfer'
       but current state is 'Idle'
       Counter-example: hostile_takeover(attacker=42)
       → Bug caught at compile time. Zero damage.
```

## Demo showcase

- for user

https://github.com/user-attachments/assets/a7ac51f6-9b8a-4134-93f1-8d47492eefb6

- for developer

https://github.com/user-attachments/assets/58028a7c-252d-4ec0-bb5a-87bb03b5a7d0

Watch the recorded Ownership Transfer dashboard walkthrough in
[docs/DEMO_SHOWCASE.md](docs/DEMO_SHOWCASE.md), or open the video file directly:
[`docs/assets/ownership-transfer-dashboard-demo.mp4`](docs/assets/ownership-transfer-dashboard-demo.mp4).

The Phase 2 RTGS Settlement dashboard walkthrough is also available in
[docs/DEMO_SHOWCASE.md](docs/DEMO_SHOWCASE.md), or open the video directly:
[`docs/assets/rtgs-settlement-dashboard-demo.mp4`](docs/assets/rtgs-settlement-dashboard-demo.mp4).

## Try It

```bash
make demo
```

For the RTGS Settlement scenario:

```bash
make demo-settlement
```

## What Runs

`make demo` executes the Phase 1 Ownership Transfer Protocol scenario:

1. LLM-generated `hostile_takeover` code tries to reach `Transferred` from `Idle`.
2. `mumei verify` rejects it with `InvalidPreState` — Z3 proves the state violation.
3. The corrected implementation verifies all five ownership atoms with Z3.
4. `mumei-lean` certifies `no_transfer_without_accept` when Lean is available.

`make demo-settlement` executes the Phase 2 RTGS Settlement Protocol scenario:

1. LLM-generated `hostile_settlement` code tries to reach `Settled` from `Pending`.
2. `mumei verify` rejects it with `InvalidPreState` — Z3 proves the state violation.
3. The corrected implementation verifies all four settlement atoms with Z3.
4. `mumei-lean` certifies `no_settlement_without_validate` and balance conservation when Lean is available.

## What Mumei Does That Lean Can't (Easily)

```mumei
atom increment(counter: i64) -> i64 {
    requires: counter >= 0;
    ensures: result == counter + 1;
    ensures: result > counter;
    body: {
        return counter + 1;
    }
}
```

- **Refinement types**: attach logical predicates directly to values and APIs.
- **Effect safety**: prove side effects are allowed before code reaches runtime.
- **Temporal state machines**: reject invalid state transitions like
  `Idle → Transferred`.
- **AI-native**: return solver counter-examples that an agent can use to repair
  the code.

No Lean tactics. No proof scripts. Just constraints.

## Three-Layer Architecture

| Layer | Repository | Role |
| --- | --- | --- |
| L1 | `mumei` + Z3 | Automatic contract & effect verification |
| L2 | `mumei-agent` | AI-driven self-healing |
| L3 | `mumei-lean` + Lean 4 | Optional: proves what Z3 can't decide |

L1 handles 95%+ of verification automatically. L3 is the safety net for edge cases.

## Repositories

- [mumei-lang/mumei](https://github.com/mumei-lang/mumei): L1 Z3-backed contract and effect verification.
- [mumei-lang/mumei-agent](https://github.com/mumei-lang/mumei-agent): L2 agent forge workflows.
- [mumei-lang/mumei-lean](https://github.com/mumei-lang/mumei-lean): L3 Lean proof bridge.

## Advanced usage

If the repositories are already checked out elsewhere, pass explicit paths:

```bash
./scripts/run_scenario.sh ownership_transfer \
  --mumei-repo ../mumei \
  --mumei-lean-repo ../mumei-lean \
  --mumei-agent-repo ../mumei-agent \
  --mumei-agent-python ../mumei-agent/.venv/bin/python \
  --mumei-bin ../mumei/target/release/mumei
```

## Adding scenarios

Copy `scenarios/_template/` and edit `scenario.json`. Two-layer demos can use
`"layers": ["l1_z3", "l2_agent"]`; three-layer demos add `"l3_lean"`.

See [docs/SCENARIO_SPEC.md](docs/SCENARIO_SPEC.md) for the scenario schema and
[docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) for detailed setup, execution, and
dashboard usage.
