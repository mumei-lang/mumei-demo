# Scenario Specification

Each scenario lives under `scenarios/<name>/` and is driven by `scenario.json`.

## Top-level fields

```json
{
  "name": "Human readable name",
  "version": "1.0.0",
  "description": "What the scenario proves",
  "layers": ["l1_z3", "l2_agent", "l3_lean"]
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
