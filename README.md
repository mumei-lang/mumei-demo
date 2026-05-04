# Mumei Demo

> **Mumei proves that LLM-generated code has bugs — mathematically.**

## The Problem

LLMs write code that looks correct but contains subtle bugs.  
Formal verification checks **every possible case**

## How It Works

Mumei is a proof-driven programming language where verification is automatic.
You write `requires` / `ensures` constraints in familiar syntax — the rest is
handled by a unified proof pipeline.

```text
mumei contract
      ↓
Z3 (automatic, fast)
      ↓
Lean 4 (deep proof)
      ↓
AI agent (self-heal)
```

One language. One contract syntax. Multiple proof engines — escalating
automatically from fast (Z3) to deep (Lean 4) to autonomous (AI agent).

What makes this possible:

| You write | mumei does |
| --- | --- |
| `requires: balance >= amount;` | Turns preconditions into solver obligations before code runs |
| `ensures: result == old(balance) - amount;` | Checks postconditions against every possible execution path |
| `requires: state == PendingTransfer;` | Rejects invalid temporal state transitions at compile time |
| `ensures: total_before == total_after;` | Escalates deeper invariants through the proof certificate chain |

The key insight: mumei is the contract language that all proof engines share.
Z3 and Lean 4 are not alternatives — they are layers in the same pipeline,
connected by a Proof Certificate Chain that flows automatically.

## See It In Action

```text
LLM generates code
      ↓
mumei verifies (Z3 — automatic)
      ↓
  ✅ Proven safe        ❌ Counter-example found
      ↓                       ↓
  LLVM binary           AI agent fixes & retries
      ↓
  Lean 4 certifies properties beyond Z3's reach
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

The Phase 2 RTGS Settlement demo is complete. Its dashboard walkthrough is
available in
[docs/DEMO_SHOWCASE.md](docs/DEMO_SHOWCASE.md), or open the video directly:
[`docs/assets/rtgs-settlement-dashboard-demo.mp4`](docs/assets/rtgs-settlement-dashboard-demo.mp4).

The Phase 3 RegTech Compliance dashboard walkthrough shows Z3 catching a
missing `PEP` match arm and the 2-layer Z3 + Agent report:
[`docs/assets/regtech-compliance-dashboard-demo.mp4`](docs/assets/regtech-compliance-dashboard-demo.mp4).

The P11 Natural Language to Verified Mumei walkthrough shows Japanese
requirements converted to forge task spec JSON, generated `.mm`, and final Z3
verification:
[`docs/assets/nl-to-verified-dashboard-demo.mp4`](docs/assets/nl-to-verified-dashboard-demo.mp4).

## Try It

```bash
make demo
```

For the RTGS Settlement scenario:

```bash
make demo-settlement
```

For the RegTech Compliance scenario:

```bash
make demo-regtech
```

For the Natural Language to Verified Mumei scenario, provide `OPENAI_API_KEY`
for the Step 0 spec extraction and run:

```bash
make demo-nl
```

To run the complete Phase 1 + Phase 2 demo sequence:

```bash
make demo-all
```

## What Runs

`make demo` executes the Phase 1 Ownership Transfer Protocol scenario:

1. LLM-generated `hostile_takeover` code tries to reach `Transferred` from `Idle`.
2. `mumei verify` rejects it with `InvalidPreState` — Z3 proves the state violation.
3. The corrected implementation verifies all five ownership atoms with Z3.
4. Lean 4 certifies `no_transfer_without_accept` through the proof certificate chain (when available).

`make demo-all` runs the complete Phase 1 + Phase 2 demo sequence:

1. Phase 1 Ownership Transfer Protocol.
2. Phase 2 RTGS Settlement Protocol.

`make demo-settlement` executes the Phase 2 RTGS Settlement Protocol scenario:

1. LLM-generated `hostile_settlement` code tries to reach `Settled` from `Pending`.
2. `mumei verify` rejects it with `InvalidPreState` — Z3 proves the state violation.
3. The corrected implementation verifies all four settlement atoms with Z3.
4. `mumei-lean` certifies `no_settlement_without_validate` and balance conservation when Lean is available.

`make demo-regtech` executes the Phase 3 RegTech Compliance Protocol scenario:

1. LLM-generated KYC code omits the `PEP` customer category from a `match`.
2. `mumei verify` rejects it with `Match is not exhaustive` and
   `CustomerType::PEP (tag=3)`.
3. The corrected implementation verifies all five compliance atoms with Z3,
   including `forall`-based transaction-limit checks.
4. The Agent forge dry-run validates the RegTech generation task. This scenario
   intentionally has no Lean layer because Z3 covers match exhaustiveness and
   quantifier checks for the demo.

`make demo-nl` executes the P11 Natural Language to Verified Mumei scenario:

1. Japanese natural-language bank-transfer requirements are extracted into a
   forge task spec JSON.
2. `mumei-agent generate` turns the extracted spec into `generated.mm`.
3. `mumei verify` proves the generated `secure_transfer` atom with Z3.
4. The latest E2E run produced `l2_agent/extract_spec: PASS`,
   `l2_agent/generate_code: PASS`, `l1_z3/verify_code: PASS`, and
   `Proof Density: 100% (3/3 atoms)`.

## What Mumei Adds to the Pipeline

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

One contract language drives automatic checks, counter-example feedback, and
deeper proof certification.

## Three-Layer Architecture

| Layer | Repository | Role |
| --- | --- | --- |
| L1 | `mumei` + Z3 | Automatic contract & effect verification |
| L2 | `mumei-agent` | AI-driven self-healing |
| L3 | `mumei-lean` + Lean 4 | Deep proof backend for auto-escalation from Z3 |

L1 handles fast automatic verification. L3 extends the same contract pipeline
through the proof certificate chain. Some scenarios, such as RegTech Compliance,
intentionally stop at L1 + L2 when Z3 fully proves the relevant properties.

## Repositories

- [mumei-lang/mumei](https://github.com/mumei-lang/mumei): Contract language + Z3 automatic verification.
- [mumei-lang/mumei-agent](https://github.com/mumei-lang/mumei-agent): AI-driven self-healing loop.
- [mumei-lang/mumei-lean](https://github.com/mumei-lang/mumei-lean): Lean 4 deep proof backend (auto-escalation from Z3).

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
