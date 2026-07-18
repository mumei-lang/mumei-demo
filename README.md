# Mumei Demo

> **Mumei proves that LLM-generated code has bugs — mathematically.**

Mumei runs formal verification over every possible case before an LLM-generated bug becomes a production incident. The representative scenarios below show the same contract pipeline catching concrete failures; the full 12-row catalog is in [`docs/SCENARIO_CATALOG.md`](docs/SCENARIO_CATALOG.md).

| Scenario | Bug an LLM can miss | How Mumei catches it |
|---|---|---|
| Ownership Transfer | `hostile_takeover` skips `accept` and tries `Idle → Transferred`. | Effect checking rejects `InvalidPreState`. |
| RTGS Settlement | A transfer can break balance conservation or settle before validation. | Z3 checks contracts; Lean certifies deeper invariants when available. |
| RegTech Compliance | `PEP` customers are missing from a `match`. | Exhaustiveness checking reports `CustomerType::PEP (tag=3)`. |
| No-.mm Multi-language Audit | Existing code enters before any `.mm` file exists. | The audit gate reports violations, counterexamples, and `next_steps`. |
| DeFi Invariant | Integer overflow occurs in an ERC-20 transfer. | Refinement types prevent overflow at compile time. |

## How It Works

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

The key insight: mumei is the contract language every proof engine shares. Z3 and Lean 4 are layers in one Proof Certificate Chain.

```text
Without mumei:  LLM skips the accept step → deployed → attacker takes over.
With mumei:     mumei ❌ InvalidPreState: 'accept' requires 'PendingTransfer'
                       but current state is 'Idle' → Bug caught at compile time.
```

## Verification demo: dogfooding audit

The `mumei_develop_audit` scenario now passes all three layers with zero original findings. Details, metrics, before/after evidence, and recording are in [`docs/DEMO_SHOWCASE.md#mumei-develop-audit-dogfooding-verification`](docs/DEMO_SHOWCASE.md#mumei-develop-audit-dogfooding-verification).

![Mumei Develop Audit live re-run — 0/0 findings, scenario PASS](docs/assets/mumei-develop-audit-result.png)

## Quick Start

```bash
make setup && make demo
```

Use `make demo-ci` for deterministic fixture-mode validation. Detailed setup, per-target commands, dashboards, and troubleshooting are in [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md).

## Running scenarios

```bash
make demo
make demo-ownership
make demo-settlement
make demo-regtech
make demo-no-mm
```

See [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md) for the exhaustive target list and P9-G NLAE integration.

## What Mumei Adds to the Pipeline

```mumei
atom increment(counter: i64) -> i64 {
    requires: counter >= 0;
    ensures: result == counter + 1;
    ensures: result > counter;
    body: { return counter + 1; }
}
```

- **Refinement types** attach logical predicates to values and APIs.
- **Effect safety** proves side effects are allowed before runtime.
- **Temporal state machines** reject invalid transitions like `Idle → Transferred`.
- **AI-native** counterexamples guide repair.

## Three-Layer Architecture

| Layer | Repository | Role |
|---|---|---|
| L1 | `mumei` + Z3 | Automatic contract and effect verification |
| L2 | `mumei-agent` | AI-driven self-healing |
| L3 | `mumei-lean` + Lean 4 | Deep proof backend for Z3 escalation |

## Repositories

- [mumei-lang/mumei](https://github.com/mumei-lang/mumei): Contract language + Z3 verification.
- [mumei-lang/mumei-agent](https://github.com/mumei-lang/mumei-agent): AI-driven self-healing loop.
- [mumei-lang/mumei-lean](https://github.com/mumei-lang/mumei-lean): Lean 4 proof backend.

## Documentation

| Document | Contents |
|---|---|
| [`docs/SCENARIO_CATALOG.md`](docs/SCENARIO_CATALOG.md) | Full scenario catalog and output examples |
| [`docs/DEMO_SHOWCASE.md`](docs/DEMO_SHOWCASE.md) | Recordings and detailed dogfooding evidence |
| [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md) | Setup, exhaustive targets, dashboards, and troubleshooting |
| [`docs/HARNESS_CONTRACTS.md`](docs/HARNESS_CONTRACTS.md) | Harness contract fields and report evidence |
| [`docs/SCENARIO_SPEC.md`](docs/SCENARIO_SPEC.md) | Scenario schema and adding scenarios |

## Adding scenarios

Copy `scenarios/_template/` and edit `scenario.json`; see [`docs/SCENARIO_SPEC.md`](docs/SCENARIO_SPEC.md) and [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md).

## License

Apache-2.0; see [`LICENSE`](LICENSE).
