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

## Run the integrated demo

```bash
make demo
```

This runs every scenario in presentation order, including the Phase 1 Ownership
Transfer, Phase 2 RTGS Settlement, and Phase 3 RegTech Compliance demos, then
regenerates dashboard summaries.

## Run the Ownership Transfer scenario

```bash
make demo-ownership
```

Or invoke the scenario runner directly:

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

## Run the Medical Device Control scenario

```bash
make demo-medical
```

Medical Device Control is a 2-layer safety demo (`l1_z3` + `l3_lean`). It first
verifies that a buggy insulin pump delivery path is rejected before bypassing the
hourly safety gate, then verifies the corrected controller and runs the Lean
proof step for cumulative dosage safety when `lake` and the proof module are
available.

Reports are written to `reports/medical_device/<timestamp>/` and mirrored via
`reports/medical_device/latest/`.

## Run all scenarios

```bash
make demo
```

`demo` runs `ownership_transfer`, `rtgs_settlement`, `regtech_compliance`,
`nl_to_verified`, `smart_contract_audit`, `medical_device`, and
`aviation_control` in order. `make demo-all` remains a compatibility alias.
`CI_FIXTURE_MODE=1 make demo-ci` runs the same scenario set with deterministic
CI fixtures and summary generation.

## CLI dashboard

```bash
python dashboard/cli_report.py reports/ownership_transfer/latest/result.json
python dashboard/cli_report.py reports/regtech_compliance/latest/result.json
python dashboard/cli_report.py reports/medical_device/latest/result.json
```

Statuses:

- `PASS`: expected successful command.
- `REJECTED`: expected failing command failed with the expected diagnostic.
- `CERTIFIED`: L3 Lean proof step succeeded.
- `SKIPPED`: optional toolchain, proof module, or dependency was unavailable.
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
The Medical Device section describes the expected dashboard evidence even when a
video artifact has not yet been captured.

## Troubleshooting

- `z3: command not found`: install Z3 or run `mumei setup`.
- `LLVM_SYS_170_PREFIX is unset`: export `LLVM_SYS_170_PREFIX=/usr/lib/llvm-17`.
- `lake` or an optional Lean proof module missing: matching L3 steps are skipped;
  L1/L2 can still pass.
- `python -m agent forge` import errors: install `mumei-agent` requirements in
  the agent repository.
- `ownership.proof.json` missing: ensure `verify_pass` completed before running
  Lean bridge steps.
- `compliance.proof.json` missing: ensure `verify_correct` completed in the
  RegTech scenario before opening the dashboard.
- `dosage.lean-cert.json` missing: ensure `lake` is installed, the matching
  proof module exists in `mumei-lean`, and the Medical Device `l3_lean` step was
  not skipped.
- Medical Device shows `SKIPPED` for Lean: install Lean 4/Lake and the proof
  module, or rerun only the Z3 steps; L1 safety evidence remains valid without
  the optional L3 proof.
