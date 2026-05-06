# mumei-demo Claude Code Guide

## Overview

`mumei-demo` is the scenario and dashboard repository for demonstrating the Mumei proof pipeline. It contains scripted demos that show Z3 rejecting subtle bugs, Lean certifying deeper invariants when available, and `mumei-agent` extracting/generating verified code from natural-language requirements.

## Scenario Structure

Scenarios live under `scenarios/<name>/` and are driven by `scenario.json`.

Current scenarios:

| Scenario | Purpose |
| --- | --- |
| `ownership_transfer` | Shows temporal/effect verification rejecting an invalid ownership state transition. |
| `rtgs_settlement` | Shows settlement invariants with Z3 and optional Lean certification. |
| `regtech_compliance` | Shows exhaustiveness checking catching a missing `PEP` match arm. |
| `nl_to_verified` | Shows natural-language requirements flowing through mumei-agent extraction/generation into verified `.mm`. |

Reports are written under `reports/<scenario>/<timestamp>/` and mirrored to `reports/<scenario>/latest/`.

## Setup

Prepare sibling repositories:

```bash
make setup
```

This runs `scripts/setup_repos.sh`, which clones or refreshes:

- `mumei-lang/mumei`
- `mumei-lang/mumei-lean`
- `mumei-lang/mumei-agent`

If LLVM is not discoverable:

```bash
export LLVM_SYS_170_PREFIX=/usr/lib/llvm-17
```

## Running Demos

Run the primary ownership transfer demo:

```bash
make demo
```

Run individual scenarios:

```bash
make demo-settlement
make demo-regtech
make demo-nl
```

Run every scenario:

```bash
make demo-all
```

Run CI-equivalent fixture validation:

```bash
CI_FIXTURE_MODE=1 make demo-ci
```

## Direct Script Usage

```bash
./scripts/run_scenario.sh ownership_transfer \
  --mumei-repo ../mumei \
  --mumei-lean-repo ../mumei-lean \
  --mumei-agent-repo ../mumei-agent \
  --mumei-bin ../mumei/target/debug/mumei
```

## Reports and Dashboard

Generate dashboard/report summaries:

```bash
make report
python3 scripts/generate_report.py --summary --highlights --require-all
```

Print a CLI dashboard for a scenario:

```bash
python dashboard/cli_report.py reports/ownership_transfer/latest/result.json
```

Run the Streamlit dashboard:

```bash
python -m pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

Status meanings:

- `PASS`: expected successful command.
- `REJECTED`: expected failing command failed with the expected diagnostic.
- `CERTIFIED`: Lean proof step succeeded.
- `SKIPPED`: optional toolchain/dependency was unavailable.
- `FAIL`: exit code or expected output did not match.

## Validation

For lightweight checks:

```bash
python3 -m compileall -q scripts dashboard
bash -n scripts/setup_repos.sh
bash -n scripts/run_scenario.sh
bash -n scripts/run_all.sh
python3 -m json.tool scenarios/ownership_transfer/scenario.json >/dev/null
python3 -m json.tool scenarios/rtgs_settlement/scenario.json >/dev/null
python3 -m json.tool scenarios/regtech_compliance/scenario.json >/dev/null
python3 -m json.tool scenarios/nl_to_verified/scenario.json >/dev/null
```
