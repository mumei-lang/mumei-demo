# Scenario Specification

Each scenario lives under `scenarios/<name>/` and is driven by `scenario.json`.

## Top-level fields

```json
{
  "name": "Human readable name",
  "version": "1.0.0",
  "description": "What the scenario proves",
  "layers": ["l1_z3", "l2_agent", "l3_lean"],
  "harness_contract": {
    "policy": "scenario-harness/v1",
    "acceptance_path": ["l1_z3", "l2_agent", "l3_lean"],
    "state_dir": "{output_dir}",
    "intent": "Original scenario requirement or audit goal",
    "artifact_contracts": [
      "Every produced artifact is listed in the step artifacts array.",
      "Every verifier gate is represented by expected_exit and expected_patterns."
    ]
  },
  "intent_fidelity": {
    "source_intent": "Original scenario requirement or audit claim.",
    "success_criteria": [
      "Unsafe path is rejected by its diagnostic gate.",
      "Correct/generated path is accepted and emits declared evidence."
    ],
    "drift_risk": "Where generated artifacts could diverge from the source intent."
  }
}
```

`layers` controls which sections run and render. Use
`["l1_z3", "l2_agent"]` for two-layer demos or add `"l3_lean"` for Lean-backed
three-layer demos.

## Layer steps

Each layer contains a `steps` array.

```json
{
  "id": "verify_property",
  "name": "Z3 Property Verification",
  "repo": "mumei",
  "command": "{mumei_bin} verify {mumei_repo}/path/to/file.mm",
  "cwd": "{mumei_repo}",
  "expected_exit": 0,
  "expect_failure": false,
  "expected_patterns": ["Verification passed"],
  "artifacts": ["property.proof.json"],
  "optional_toolchain": "lake",
  "optional_path": "{mumei_lean_repo}/MumeiLean/Example.lean",
  "depends_on": ["previous_step"]
}
```

### Fields

- `id`: unique step identifier within the scenario.
- `name`: display name for dashboards.
- `repo`: logical repository label.
- `command`: shell command to execute.
- `cwd`: optional working directory. Defaults to the demo repository root.
- `expected_exit`: required expected process exit code.
- `expect_failure`: marks an expected rejection. If the actual exit matches,
  dashboards render `REJECTED` instead of `PASS`.
- `expected_patterns`: substrings that must appear in stdout or stderr.
- `artifacts`: files expected under `{output_dir}` after the step.
- `optional_toolchain`: executable name. If missing from `PATH`, the step is
  `SKIPPED`.
- `optional_path`: file or directory path. If missing, the step is `SKIPPED`.
- `depends_on`: step IDs that must have `PASS`, `REJECTED`, or `CERTIFIED`
  status before this step runs.

### Harness metadata (recommended)

NLAH-style scenario policies can attach harness metadata at the top level and
per step. The runner treats these fields as pass-through report evidence: they
do not change command execution, but they are copied into `result.json` so CLI
reports, dashboards, and later ablation tooling can reason about artifact
contracts without re-reading the source scenario. See
[`docs/HARNESS_CONTRACTS.md`](HARNESS_CONTRACTS.md) for the stage-contract
definitions and scenario-to-evidence mapping.

Top-level `harness_contract` fields:

- `policy`: versioned contract name, e.g. `scenario-harness/v1`.
- `acceptance_path`: layer order that must produce evidence for the scenario to
  be considered complete.
- `state_dir`: persistent state directory; normally `{output_dir}`.
- `intent`: one sentence describing the user-facing proof/demo intent.
- `artifact_contracts`: human-readable obligations that all steps must satisfy,
  including files read, files generated, verification evidence, dashboard
  evidence, and downstream trust gates.
- `intent_fidelity`: recommended top-level object that records:
  - `source_intent`: the original requirement, bug class, or audit claim.
  - `success_criteria`: checklist of evidence required to satisfy the intent.
  - `drift_risk`: where generated code/spec/proof artifacts could diverge from
    the original intent.

Per-step fields:

- `harness_stage`: stable stage label such as `S1_z3_rejection`,
  `S2_agent_preview`, or `S3_lean_certification`.
- `artifact_contract`: files or report keys this step must produce or preserve.
- `verifier_gate`: concise statement of the acceptance gate represented by
  `expected_exit`, `expected_patterns`, `expect_failure`, and `depends_on`.
- `failure_taxonomy`: expected failure class when the step rejects or escalates.

Recommended stage labels:

- `S1_z3_rejection_*`, `S1_z3_acceptance_*`, and `S1_z3_regression_*` for
  `l1_z3` bug-detection, proof-certificate, and E2E gates.
- `S2_agent_extraction_*`, `S2_agent_generation_*`, and
  `S2_agent_preview_*` for `l2_agent` natural-language, code-generation, and
  dry-run gates.
- `S3_lean_certification_*` and `S3_lean_bridge_*` for `l3_lean` proof-build
  and certificate-bridge gates.

Example:

```json
{
  "id": "verify_correct",
  "name": "Z3 Correct Implementation Verification",
  "repo": "mumei",
  "command": "{mumei_bin} verify {root_dir}/scenarios/example/correct.mm --proof-cert --output {output_dir}/scenario.proof.json",
  "expected_exit": 0,
  "expected_patterns": ["Verification passed"],
  "artifacts": ["scenario.proof.json"],
  "harness_stage": "S1_z3_acceptance",
  "artifact_contract": ["scenario.proof.json"],
  "verifier_gate": "Mumei/Z3 accepts the corrected atom and writes a proof certificate."
}
```

## Narrative (optional)

A top-level `narrative` object lets each scenario provide its own story text
for the runner banner and the CLI report. All fields are optional; missing
fields fall back to generic defaults.

```json
{
  "narrative": {
    "intro": [
      "Step 1: LLM generates code...",
      "Step 2: mumei verifies the code..."
    ],
    "before": "Short BEFORE summary used by the CLI report",
    "after": "Short AFTER summary used by the CLI report",
    "steps": {
      "<step_id>": {
        "<status>": {
          "icon": "❌",
          "headline": "Headline shown in the runner banner",
          "follow_up": ["additional indented lines"]
        }
      }
    }
  }
}
```

`<status>` is the lowercase step status (`pass`, `rejected`, `certified`,
`fail`, `skipped`). The matching entry is rendered in the runner banner when
the step finishes with that status.

## Placeholders

Commands and `cwd` can use:

- `{mumei_repo}`
- `{mumei_lean_repo}`
- `{mumei_agent_repo}`
- `{mumei_agent_python}`
- `{mumei_bin}`
- `{root_dir}`
- `{output_dir}`

Values come from CLI arguments, `repos.env`, or defaults next to this repo.
The runner also exports these values as environment variables and sets
`MUMEI_STD_PATH` to `{mumei_repo}/std` unless it is already defined.
`{mumei_agent_python}` defaults to `MUMEI_AGENT_PYTHON` from `repos.env`,
`{mumei_agent_repo}/.venv/bin/python` when it exists, or the current Python
interpreter.

## Adding a scenario

```bash
cp -R scenarios/_template scenarios/regtech_policy
vim scenarios/regtech_policy/scenario.json
./scripts/run_scenario.sh regtech_policy
python3 scripts/generate_report.py reports/regtech_policy/latest/result.json --format markdown
```

`run_scenario.sh` writes both `result.json` and a per-scenario `report.md`.
The standalone `--format markdown` command regenerates that report from any
saved result file.

## NLAH-style harness contract guide

Use a harness contract when a scenario needs explainable artifact flow across
Z3, agent, Lean, reports, and dashboard summaries.

1. Put the stage order in `harness_contract.acceptance_path`. This should match
   `layers`, including non-standard orders such as `["l2_agent", "l1_z3"]` for
   natural-language generation flows.
2. List the files read by the scenario in `harness_contract.artifact_contracts`.
   Include scenario `.mm` files, forge task JSON, natural-language text, sibling
   Lean modules, and any generated input consumed by a later stage.
3. List generated evidence in the same contract. At minimum, every scenario
   should map `result.json`, `report.md`, per-step logs, proof certificates,
   Lean certificates, and `dashboard/summary.md` when applicable.
4. Add per-step `harness_stage`, `artifact_contract`, and `verifier_gate` so the
   result report can explain which gate each artifact proves.
5. Add `intent_fidelity` to state the original requirement, the evidence needed
   to satisfy it, and any drift risk from generated intermediate artifacts.

Gate semantics by stage:

- `l1_z3` reads scenario code and accepts/rejects with Mumei/Z3 diagnostics;
  proof-producing acceptance steps should write `*.proof.json`.
- `l2_agent` reads natural-language or forge-task inputs and writes generated
  artifacts (`extracted_spec.json`, `generated.mm`) or dry-run evidence.
- `l3_lean` reads L1 proof certificates and Lean assets, then writes
  `*.lean-cert.json` or records a `SKIPPED` optional-proof gate.

Stop execution or block downstream trust when a command exits unexpectedly,
required patterns are missing, required artifacts are absent, or a `depends_on`
gate did not finish with `PASS`, `REJECTED`, or `CERTIFIED`.

## Medical Device CI scenario

The scenario uses `layers: ["l1_z3", "l3_lean"]`, expected-failure Z3 steps for
unsafe insulin pump states, normal verification steps for the correct
controller, `depends_on` to keep Lean behind successful L1 proof output,
`optional_toolchain: "lake"`, and `optional_path` for the proof module so CI can
report `SKIPPED` rather than failing when optional Lean proof assets are
unavailable.

## Two-layer RegTech skeleton

```json
{
  "name": "RegTech Policy",
  "version": "0.1.0",
  "description": "Verify policy checks with Z3 and preview agent remediation.",
  "layers": ["l1_z3", "l2_agent"],
  "l1_z3": {
    "steps": [
      {
        "id": "policy_verify",
        "name": "Policy Verification",
        "repo": "mumei",
        "command": "{mumei_bin} verify {mumei_repo}/examples/regtech.mm",
        "expected_exit": 0,
        "expected_patterns": ["Verification passed"],
        "artifacts": []
      }
    ]
  },
  "l2_agent": {
    "steps": [
      {
        "id": "agent_policy_dryrun",
        "name": "Agent Policy Dry Run",
        "repo": "mumei-agent",
        "command": "{mumei_agent_python} -m agent forge --tasks-dir {mumei_agent_repo}/forge_tasks --task regtech_policy.json --mumei-repo {mumei_repo} --dry-run",
        "cwd": "{mumei_agent_repo}",
        "expected_exit": 0,
        "expected_patterns": [],
        "artifacts": []
      }
    ]
  }
}
```
