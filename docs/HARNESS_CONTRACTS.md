# NLAH-Style Harness Contracts

This document explains the scenario runner as an artifact-contract harness:
every stage declares what it reads, what it writes, which verifier gate accepts
the evidence, and when execution must stop.

The contract metadata lives in `scenarios/*/scenario.json` and is copied into
`reports/<scenario>/latest/result.json`, rendered into `report.md`, and shown by
the dashboard. The fields are descriptive and auditable; command execution is
still controlled by `layers`, `steps`, `expected_exit`, `expected_patterns`,
`artifacts`, and `depends_on`.

## Stage contracts

### `l1_z3`: Mumei/Z3 verification

| Contract item | Definition |
| --- | --- |
| Inputs | Scenario `.mm` files, sibling `mumei` checkout, `{mumei_bin}`, optional Mumei test fixtures, and upstream generated files such as `{output_dir}/generated.mm`. |
| Outputs | Per-step log, `PASS` or expected `REJECTED` status in `result.json`, optional `*.proof.json` proof certificate, and dashboard/report rows. |
| Verification gate | The command exit code must match `expected_exit`; every `expected_patterns` substring must appear in stdout/stderr; expected failures must set `expect_failure: true`; declared artifacts are trusted only when written under `{output_dir}`. |
| Stop conditions | Unexpected exit code, missing expected diagnostic, failed `depends_on` prerequisite, missing verifier binary/source path, or missing proof artifact required by a downstream stage. |

### `l2_agent`: agent extraction, generation, or dry-run

| Contract item | Definition |
| --- | --- |
| Inputs | Natural-language requirement text, forge task JSON, sibling `mumei-agent` checkout, `{mumei_agent_python}`, and any upstream verifier artifacts named in `depends_on`. |
| Outputs | Per-step log, generated/extracted files such as `extracted_spec.json` or `generated.mm`, dry-run acceptance status, and report/dashboard evidence. |
| Verification gate | Agent command exits with `expected_exit`, emits all `expected_patterns`, writes every declared artifact, and only runs after its dependency gates are accepted. |
| Stop conditions | Agent command failure, missing generated/extracted artifact, failed dependency gate, or unavailable live LLM credential for non-fixture extraction. |

### `l3_lean`: Lean proof and certificate bridge

| Contract item | Definition |
| --- | --- |
| Inputs | L1 proof certificates, sibling `mumei-lean` checkout, Lean module path, bridge script, Lake toolchain, and declared `depends_on` gates. |
| Outputs | Lean build log/status, `CERTIFIED` or `SKIPPED` status in `result.json`, optional `*.lean-cert.json` bridge certificate, and report/dashboard proof rows. |
| Verification gate | Optional toolchain/path checks either allow the step to run or mark it `SKIPPED`; Lean/bridge commands must match `expected_exit` and `expected_patterns`; bridge certificates must be declared in `artifacts`. |
| Stop conditions | Lean build failure, bridge ingestion failure, missing upstream proof certificate, missing non-optional Lean module, or failed L1 dependency. |

## Artifact contract format

Top-level scenario contracts use this shape:

```json
{
  "harness_contract": {
    "policy": "scenario-harness/v1",
    "acceptance_path": ["l1_z3", "l2_agent", "l3_lean"],
    "state_dir": "{output_dir}",
    "intent": "The proof/audit goal this scenario preserves.",
    "artifact_contracts": [
      "Read inputs: files and sibling repo assets consumed by the scenario.",
      "Generate evidence: result.json and report.md plus per-step logs.",
      "Proof certificates and dashboard summaries mapped to their gates.",
      "Gate order and stop conditions for downstream trust."
    ]
  }
}
```

Each step can additionally declare:

```json
{
  "harness_stage": "S1_z3_acceptance_verify_correct",
  "artifact_contract": ["scenario.proof.json"],
  "verifier_gate": "Command exits 0 and emits expected acceptance evidence.",
  "failure_taxonomy": "temporal_state_violation"
}
```

- `harness_stage` is a stable stage label for reports and ablation tooling.
- `artifact_contract` lists generated files or evidence keys that make the gate
  auditable.
- `verifier_gate` states the acceptance/rejection rule in human-readable form.
- `failure_taxonomy` classifies expected rejection gates.

## Evidence mapping

| Evidence artifact | Gate it supports | Notes |
| --- | --- | --- |
| `result.json` | All stages | Canonical machine-readable gate record. It stores layer status, step status, expected exit, stdout/stderr, artifacts, harness metadata, and proof density. |
| `report.md` | All stages | Human-readable evidence generated from `result.json`; includes harness contract and stage-gate tables when metadata is present. |
| Per-step `*.log` | Step-local gate | Captures the exact command, stdout, stderr, and missing expected patterns if any. |
| `*.proof.json` | `l1_z3` acceptance | Z3/Mumei proof certificate emitted by successful corrected-code verification steps. Downstream Lean bridge steps consume these files. |
| `*.lean-cert.json` | `l3_lean` bridge | Lean bridge certificate produced from an L1 proof certificate when optional Lean assets are available. |
| `dashboard/summary.md` | Cross-scenario gate | Aggregates latest scenario status and proof density; `--require-all` makes missing scenario results fail the report target. |
| `dashboard/highlights.md` | Cross-scenario explanation | Summarizes scenario outcomes for dashboard/review use. |

## Scenario-to-gate mapping

| Scenario | L1 evidence | L2 evidence | L3 evidence | Dashboard evidence |
| --- | --- | --- | --- | --- |
| `ownership_transfer` | `InvalidPreState` rejection, `ownership.proof.json`, ownership E2E verification | `vstd_ownership` forge dry-run | `MumeiLean.Ownership` build and `ownership.lean-cert.json` when available | Summary row with 6/6 proof density |
| `rtgs_settlement` | `InvalidPreState` rejection, `settlement.proof.json`, settlement E2E verification | `vstd_settlement` forge dry-run | `MumeiLean.Settlement` build and `settlement.lean-cert.json` when available | Summary row with 6/6 proof density |
| `regtech_compliance` | Missing-`PEP` rejection, negative-suite rejection, `compliance.proof.json`, compliance E2E verification | `vstd_regtech` forge dry-run | Not used | Summary row with 5/5 proof density |
| `nl_to_verified` | Verification of generated `{output_dir}/generated.mm` | `extracted_spec.json` and `generated.mm` | Not used | Summary row with 3/3 proof density |
| `smart_contract_audit` | Reentrancy-state rejection and `smart_contract.proof.json` | Not used | `MumeiLean.SmartContract` build and `smart_contract.lean-cert.json` when available | Summary row with 4/4 proof density |
| `medical_device` | Dosage-state rejection and `medical_device.proof.json` | Not used | `MumeiLean.MedicalDevice` build and `medical_device.lean-cert.json` when available | Summary row with 4/4 proof density |
| `aviation_control` | Lock-order rejection and `allocate_runway` verification recorded in `result.json`/logs | `vstd_aviation_control` forge dry-run | Not used | Summary row with 3/3 proof density |
| `merkle_tree_verification` | Missing hash-security rejection and `merkle_tree.proof.json` | Not used | `MumeiLean.MerkleTree` build and `merkle_tree.lean-cert.json` when available | Summary row with 4/4 proof density |
| `defi_invariant` | Uint256 precondition rejection and `defi_invariant.proof.json` | Not used | `MumeiLean.DeFi` build and `defi_invariant.lean-cert.json` when available | Summary row with 4/4 proof density |
| `arklib_style_audit` | Contradictory theorem rejection and `arklib_audit.proof.json` | Not used | `MumeiLean.ArkLibAudit` build and `arklib_audit.lean-cert.json` when available | Summary row with 4/4 proof density |

## Intent fidelity

`intent_fidelity` records how the harness preserves the original user/audit
intent:

```json
{
  "intent_fidelity": {
    "source_intent": "Original requirement or audit claim.",
    "success_criteria": [
      "Unsafe path is rejected by its diagnostic gate.",
      "Corrected/generated path is accepted and emits declared evidence.",
      "Reports and dashboard summaries preserve the evidence chain."
    ],
    "drift_risk": "Where generated artifacts could diverge from source intent."
  }
}
```

Use this field to explain why the produced artifacts answer the original
scenario, especially for agent-generated flows where `extracted_spec.json` and
`generated.mm` are reviewable intermediate evidence.
