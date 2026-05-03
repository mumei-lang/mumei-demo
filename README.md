# Mumei Demo

> **Mumei detects bugs in LLM-generated code using formal verification.**

## The Problem

LLMs write code that looks correct but contains subtle bugs.
Traditional testing catches some. Mumei catches **all** — mathematically.

## See It In Action

```text
LLM → mumei → Lean → Proof failure → Bug found
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

## Try It

```bash
make demo
```

## What Runs

`make demo` executes the Phase 1 Ownership Transfer Protocol scenario:

1. LLM-generated `hostile_takeover` code tries to reach `Transferred` from `Idle`.
2. `mumei verify` rejects it with `InvalidPreState`.
3. The corrected implementation verifies all five ownership atoms with Z3.
4. `mumei-lean` certifies `no_transfer_without_accept` when Lean is available.

## Repositories

- [mumei-lang/mumei](https://github.com/mumei-lang/mumei): L1 Z3-backed contract and effect verification.
- [mumei-lang/mumei-agent](https://github.com/mumei-lang/mumei-agent): L2 agent forge workflows.
- [mumei-lang/mumei-lean](https://github.com/mumei-lang/mumei-lean): L3 Lean proof bridge.

## Demo showcase

Watch the recorded Ownership Transfer dashboard walkthrough in
[docs/DEMO_SHOWCASE.md](docs/DEMO_SHOWCASE.md), or open the video file directly:
[`docs/assets/ownership-transfer-dashboard-demo.mp4`](docs/assets/ownership-transfer-dashboard-demo.mp4).

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