# Mumei Demo

> **Mumei proves that LLM-generated code has bugs — mathematically.**

LLMs write code that looks correct but hides subtle bugs. Mumei runs formal
verification over **every possible case** before a bug becomes a production
incident. Each scenario below makes one of those bugs concrete and shows Mumei
catching it.

| Scenario | Bug an LLM can miss | How Mumei catches it |
| --- | --- | --- |
| Ownership Transfer | `hostile_takeover` skips `accept` and tries `Idle → Transferred`. | The effect checker rejects the invalid pre-state with `InvalidPreState`. |
| RTGS Settlement | A transfer flow can break balance conservation or settle before validation. | Z3 checks settlement contracts, then Lean certifies deeper invariants when available. |
| RegTech Compliance | `PEP` customers are missing from a `match` expression. | Exhaustiveness checking reports `CustomerType::PEP (tag=3)` as a counter-example. |
| NL → Verified | Requirements start as natural language instead of verified code. | The agent extracts a spec, generates `.mm`, and Z3 verifies the result automatically. |
| No-.mm Multi-language Audit | Existing Python/Rust/TypeScript/Go code enters before any `.mm` file exists. | The audit gate reports each language's violations as `verification_violations` with Z3 counterexamples and `next_steps`. |
| Phase 7 Spec-Code Verification Suite | A reviewer has only `spec.txt` and existing Python code, with no `.mm` entry yet. | V1-A through V1-D run in one flow: `spec_health_issues`, `verification_violations`, `traceability_matrix`, `drift_score`, and `next_steps`. |
| Mumei Develop Audit | The project's own tooling drifts from its spec. | Dogfooding: `mumei-agent audit` runs on `mumei/scripts/generate_stdlib_metrics.py`. |
| Medical Device Control | An insulin pump skips hourly dosage safety checks. | Z3 catches the invalid delivery state, then optional Lean proof certifies cumulative dosage safety. |
| Aviation Control | Runway allocation has inconsistent lock ordering. | Z3 verifies ordered allocation, and the agent validates the generation task. |
| Merkle Tree Verification | Assumes hash function integrity without proof. | Z3 verifies the `hash_function_secure` precondition, Lean certifies collision resistance. |
| DeFi Invariant | Integer overflow in ERC-20 transfer. | Refinement types (`type Uint256 = i64 where v >= 0 && v <= MAX`) prevent overflow at compile time. |
| ArkLib-Style Audit | Complex implementation hides bugs. | Top-level `requires`/`ensures` reviewed by humans, Lean proves implementation correctness. |
| P9-G NLAE Integration | A generated vault withdrawal violates a postcondition. | `mumei verify --emit loss-vector` feeds mumei-agent self-correction, then mumei-lean checks fidelity. |

Full descriptions and per-scenario output examples live in
[`docs/SCENARIO_CATALOG.md`](docs/SCENARIO_CATALOG.md).

## How It Works

Mumei is a proof-driven programming language where verification is automatic.
You write `requires` / `ensures` constraints; a unified proof pipeline handles
the rest, escalating from fast (Z3) to deep (Lean 4) to autonomous (AI agent).

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

The key insight: mumei is the contract language every proof engine shares. Z3
and Lean 4 are not alternatives — they are layers in the same pipeline,
connected by a Proof Certificate Chain that flows automatically.

### With vs. without Mumei

```text
Without mumei:  LLM skips the accept step → deployed → attacker takes over.

With mumei:     mumei ❌ InvalidPreState: 'accept' requires 'PendingTransfer'
                       but current state is 'Idle'
                       Counter-example: hostile_takeover(attacker=42)
                       → Bug caught at compile time. Zero damage.
```

## Verification demo: dogfooding audit

The `mumei_develop_audit` scenario points Mumei's own audit tooling at
`mumei/scripts/generate_stdlib_metrics.py`. After the dogfooding fixes (mumei
#432, mumei-agent #377, mumei-demo #66), a live re-run shows all four original
audit findings resolved:

- all three layers PASS (`record_targets`, `audit_develop_target`,
  `generate_migration_guidance`);
- `success = True`, `verification_status = verified`;
- `cross_validation_gaps` `2 → 0` and `spec_health_issues` `2 → 0`;
- `migrate-suggest` emits `mm/analyze_metrics.mm` and
  `mm/generate_markdown_report.mm`.

Recording and result screenshot:
[`docs/DEMO_SHOWCASE.md#mumei-develop-audit-dogfooding-verification`](docs/DEMO_SHOWCASE.md#mumei-develop-audit-dogfooding-verification)
— video [`docs/assets/mumei-develop-audit-cli-demo.mp4`](docs/assets/mumei-develop-audit-cli-demo.mp4),
image [`docs/assets/mumei-develop-audit-result.png`](docs/assets/mumei-develop-audit-result.png).

![Mumei Develop Audit live re-run — 0/0 findings, scenario PASS](docs/assets/mumei-develop-audit-result.png)

Before/after audit fields:
[`scenarios/mumei_develop_audit/AUDIT_LOG_2026-07-17.md`](scenarios/mumei_develop_audit/AUDIT_LOG_2026-07-17.md).
This scenario also illustrates the quality-gate principle documented in the
scenario README: spec health and cross-validation drift are first-class gates,
and a passing scenario does not by itself mean there is no audit follow-up.

## Demos & recordings

Recorded dashboard and CLI walkthroughs for every scenario are collected in
[`docs/DEMO_SHOWCASE.md`](docs/DEMO_SHOWCASE.md) (videos under
[`docs/assets/`](docs/assets/)).

## Quick Start

```bash
make setup && make demo
```

`make setup` clones or refreshes `mumei`, `mumei-agent`, and `mumei-lean` next
to this repository. `make demo` runs the complete scenario sequence and writes
reports under `reports/<scenario>/latest/` plus dashboard summaries. For
CI-equivalent validation with fixture mode:

```bash
make demo-ci
```

## Running scenarios

Each scenario has a `make` target, e.g.:

```bash
make demo-ownership   # Phase 1 Ownership Transfer
make demo-settlement  # Phase 2 RTGS Settlement
make demo-regtech     # Phase 3 RegTech Compliance
make demo-nl          # P11 Natural Language → Verified (needs OPENAI_API_KEY)
make demo-medical     # Medical Device Control
make demo-merkle      # Merkle Tree Verification
make demo-defi        # DeFi Invariant
make demo-arklib      # ArkLib-Style Audit
make demo-spec-code   # Phase 7 Spec-Code Verification Suite (fixture default)
make demo-no-mm       # No-.mm multi-language audit (fixture default)
make demo             # full integrated sequence (alias: make demo-all)
```

The P9-G NLAE integration demo runs via
`./demos/nlae_integration/run_demo.sh`. See
[`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md) for setup, explicit repo paths,
per-scenario notes, and the CLI/Streamlit dashboards, and
[`docs/SCENARIO_CATALOG.md`](docs/SCENARIO_CATALOG.md) for step-by-step
breakdowns and example output.

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

## Three-Layer Architecture

| Layer | Repository | Role |
| --- | --- | --- |
| L1 | `mumei` + Z3 | Automatic contract & effect verification |
| L2 | `mumei-agent` | AI-driven self-healing |
| L3 | `mumei-lean` + Lean 4 | Deep proof backend for auto-escalation from Z3 |

L1 handles fast automatic verification; L3 extends the same contract pipeline
through the proof certificate chain. Some scenarios (e.g. RegTech Compliance)
intentionally stop at L1 + L2 when Z3 fully proves the relevant properties.

Scenarios carry NLAH-style `harness_contract` metadata, top-level
`intent_fidelity`, and per-step `harness_stage` / `artifact_contract` /
`verifier_gate` / `failure_taxonomy` fields, copied into `result.json` and
rendered as report evidence. See
[`docs/HARNESS_CONTRACTS.md`](docs/HARNESS_CONTRACTS.md) and
[`docs/SCENARIO_SPEC.md`](docs/SCENARIO_SPEC.md).

## Repositories

- [mumei-lang/mumei](https://github.com/mumei-lang/mumei): Contract language + Z3 automatic verification.
- [mumei-lang/mumei-agent](https://github.com/mumei-lang/mumei-agent): AI-driven self-healing loop.
- [mumei-lang/mumei-lean](https://github.com/mumei-lang/mumei-lean): Lean 4 deep proof backend (auto-escalation from Z3).

## Adding scenarios

Copy `scenarios/_template/` and edit `scenario.json`. Two-layer demos use
`"layers": ["l1_z3", "l2_agent"]`; three-layer demos add `"l3_lean"`. See
[`docs/SCENARIO_SPEC.md`](docs/SCENARIO_SPEC.md) for the schema and
[`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md) for detailed setup, execution, and
dashboard usage.
