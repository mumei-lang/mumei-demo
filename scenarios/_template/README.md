# Scenario Template

Copy this directory to `scenarios/<scenario_name>/` and edit `scenario.json`.

```bash
cp -R scenarios/_template scenarios/my_scenario
python3 -m json.tool scenarios/my_scenario/scenario.json >/dev/null
./scripts/run_scenario.sh my_scenario
```

## Files

- `scenario.json`: comment-key schema template. Keys beginning with `_` explain
  the adjacent field and can be removed after copying.
- `buggy_code.mm`: intentionally unsafe implementation used by an
  `expect_failure: true` detection step.
- `correct_code.mm`: verified implementation used by the passing Z3 step.
- `README.md`: scenario authoring checklist.

## Layers

Use the `layers` array to choose the demo depth:

- Two-layer demo: `["l1_z3", "l2_agent"]`
- Three-layer demo: `["l1_z3", "l2_agent", "l3_lean"]`

Only layers listed in `layers` are executed and rendered in reports.

## Step fields

Each step has an `id`, display `name`, target `repo`, shell `command`,
`expected_exit`, optional `expected_patterns`, optional `artifacts`, optional
`cwd`, optional `depends_on`, and optional `optional_toolchain`.

Available placeholders include `{mumei_repo}`, `{mumei_lean_repo}`,
`{mumei_agent_repo}`, `{mumei_agent_python}`, `{mumei_bin}`, `{root_dir}`, and
`{output_dir}`.

## Adding a new scenario

1. Copy this directory and rename it with a stable snake_case scenario ID.
2. Replace `name`, `description`, and `narrative.before` / `narrative.after`
   with presentation-quality text.
3. Edit `buggy_code.mm` so the first L1 step demonstrates the bug Mumei should
   reject. Set `expected_exit`, `expect_failure`, and `expected_patterns` to the
   concrete verifier behavior.
4. Edit `correct_code.mm` so the second L1 step verifies and emits a proof
   certificate under `{output_dir}` when useful.
5. Add or remove L2/L3 steps to match the scenario. Keep CI-safe agent steps
   deterministic, and mark optional Lean tools with `optional_toolchain`.
6. Run the scenario and inspect both outputs:

```bash
./scripts/run_scenario.sh my_scenario
python3 scripts/generate_report.py reports/my_scenario/latest/result.json --format markdown
python3 dashboard/cli_report.py reports/my_scenario/latest/result.json
```

7. If the scenario should be part of the standard demo, add it to
   `scripts/generate_report.py::SCENARIO_ORDER`, `Makefile`, and CI workflow
   expectations.
