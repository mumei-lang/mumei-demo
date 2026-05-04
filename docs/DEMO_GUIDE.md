# Demo Guide

## Prerequisites

- Rust and Cargo for building `mumei`.
- Z3 (`z3`, `libz3-dev`) for L1 verification.
- LLVM 17 and `LLVM_SYS_170_PREFIX=/usr/lib/llvm-17` for the Mumei build.
- Python 3.10+ for scripts and `mumei-agent`.
- Optional: Lean 4 and Lake for L3 proof builds.
- Optional: Streamlit for the rich dashboard.

## Setup

```bash
./scripts/setup_repos.sh
```

This clones or updates:

- `mumei-lang/mumei`
- `mumei-lang/mumei-lean`
- `mumei-lang/mumei-agent`

It builds `mumei`, optionally builds `mumei-lean` when `lake` exists, installs
agent dependencies into `mumei-agent/.venv`, and writes `repos.env`.

If LLVM is not discoverable:

```bash
export LLVM_SYS_170_PREFIX=/usr/lib/llvm-17
```

## Run the Ownership Transfer scenario

```bash
./scripts/run_scenario.sh ownership_transfer
```

Or provide explicit repository paths:

```bash
./scripts/run_scenario.sh ownership_transfer \
  --mumei-repo ../mumei \
  --mumei-lean-repo ../mumei-lean \
  --mumei-agent-repo ../mumei-agent \
  --mumei-agent-python ../mumei-agent/.venv/bin/python \
  --mumei-bin ../mumei/target/release/mumei
```

Reports are written to `reports/ownership_transfer/<timestamp>/` and mirrored
via `reports/ownership_transfer/latest/`.

## Run the RTGS Settlement scenario

```bash
make demo-settlement
```

Reports are written to `reports/rtgs_settlement/<timestamp>/` and mirrored via
`reports/rtgs_settlement/latest/`.

## Run the RegTech Compliance scenario

```bash
make demo-regtech
```

RegTech is a 2-layer demo (`l1_z3` + `l2_agent`) with no Lean layer. It first
verifies `scenarios/regtech_compliance/buggy_code.mm`, expecting Z3 to reject
the missing `PEP` match arm with `CustomerType::PEP (tag=3)`, then verifies
`correct_code.mm` and writes `compliance.proof.json`.

Reports are written to `reports/regtech_compliance/<timestamp>/` and mirrored
via `reports/regtech_compliance/latest/`.

## Run all scenarios

```bash
make demo-all
```

## CLI dashboard

```bash
python dashboard/cli_report.py reports/ownership_transfer/latest/result.json
python dashboard/cli_report.py reports/regtech_compliance/latest/result.json
```

Statuses:

- `PASS`: expected successful command.
- `REJECTED`: expected failing command failed with the expected diagnostic.
- `CERTIFIED`: L3 Lean proof step succeeded.
- `SKIPPED`: optional toolchain or dependency was unavailable.
- `FAIL`: exit code or expected output did not match.

## Streamlit dashboard

```bash
python -m pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

The dashboard lets you select a scenario, inspect layer cards, view step logs,
open proof certificates, and compare proof density across scenarios.

Recorded walkthroughs are listed in
[`docs/DEMO_SHOWCASE.md`](DEMO_SHOWCASE.md), including the RegTech dashboard
recording at
[`docs/assets/regtech-compliance-dashboard-demo.mp4`](assets/regtech-compliance-dashboard-demo.mp4).

## Troubleshooting

- `z3: command not found`: install Z3 or run `mumei setup`.
- `LLVM_SYS_170_PREFIX is unset`: export `LLVM_SYS_170_PREFIX=/usr/lib/llvm-17`.
- `lake` missing: L3 steps with `optional_toolchain: "lake"` are skipped; L1/L2
  can still pass.
- `python -m agent forge` import errors: install `mumei-agent` requirements in
  the agent repository.
- `ownership.proof.json` missing: ensure `verify_pass` completed before running
  Lean bridge steps.
- `compliance.proof.json` missing: ensure `verify_correct` completed in the
  RegTech scenario before opening the dashboard.
