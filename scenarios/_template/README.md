# Scenario Template

Copy this directory to `scenarios/<scenario_name>/` and edit `scenario.json`.

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
`{mumei_agent_repo}`, `{mumei_agent_python}`, `{mumei_bin}`, and `{output_dir}`.
