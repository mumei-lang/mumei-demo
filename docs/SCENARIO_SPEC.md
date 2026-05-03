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
- `depends_on`: step IDs that must have `PASS`, `REJECTED`, or `CERTIFIED`
  status before this step runs.

## Placeholders

Commands and `cwd` can use:

- `{mumei_repo}`
- `{mumei_lean_repo}`
- `{mumei_agent_repo}`
- `{mumei_agent_python}`
- `{mumei_bin}`
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
```

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
