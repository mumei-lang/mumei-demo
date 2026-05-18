# Mumei Demo Development Guide

Always reference these instructions first and fall back to search or shell commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

### Repository Role

`mumei-demo` contains end-to-end demonstration scenarios for the Mumei ecosystem. It coordinates sibling checkouts of:

- `mumei-lang/mumei` for the compiler, Z3 verification, and proof certificates.
- `mumei-lang/mumei-lean` for optional Lean 4 certification.
- `mumei-lang/mumei-agent` for LLM-assisted extraction, generation, and healing.

### Scenario Layout

Scenarios live in `scenarios/<name>/` and are described by `scenario.json`. Reports are written under `reports/<scenario>/<timestamp>/` and mirrored to `reports/<scenario>/latest/`.

Current scenarios:

| Scenario | Bug or workflow demonstrated |
| --- | --- |
| `ownership_transfer` | Invalid state transition rejected by effect/temporal checks. |
| `rtgs_settlement` | Settlement invariants, Z3 verification, optional Lean certification. |
| `regtech_compliance` | Missing `PEP` match arm found by exhaustiveness checking. |
| `nl_to_verified` | Natural-language requirements extracted to spec and generated into verified `.mm`. |
| `smart_contract_audit` | Reentrancy guard and optional Lean certification. |
| `medical_device` | Insulin pump dosage safety and optional Lean certification. |
| `aviation_control` | Runway allocation locking and agent validation. |

## Setup and Commands

Prepare sibling repos:

```bash
make setup
```

Run the integrated all-scenario demo:

```bash
make demo
```

Run individual demos:

```bash
make demo-ownership
make demo-settlement
make demo-regtech
make demo-nl
make demo-smart-contract
make demo-medical
make demo-aviation
```

`make demo-all` remains a compatibility alias for `make demo`.

Run CI-equivalent fixture mode:

```bash
CI_FIXTURE_MODE=1 make demo-ci
```

Generate report summaries:

```bash
make report
python3 scripts/generate_report.py --summary --highlights --require-all
```

Direct scenario runner:

```bash
./scripts/run_scenario.sh ownership_transfer \
  --mumei-repo ../mumei \
  --mumei-lean-repo ../mumei-lean \
  --mumei-agent-repo ../mumei-agent \
  --mumei-bin ../mumei/target/debug/mumei
```

If LLVM is not discoverable for the Mumei build:

```bash
export LLVM_SYS_170_PREFIX=/usr/lib/llvm-17
```

## Dashboard

CLI dashboard:

```bash
python dashboard/cli_report.py reports/ownership_transfer/latest/result.json
python dashboard/cli_report.py reports/regtech_compliance/latest/result.json
```

Streamlit dashboard:

```bash
python -m pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

Status meanings:

| Status | Meaning |
| --- | --- |
| `PASS` | Expected successful command. |
| `REJECTED` | Expected failing command failed with the expected diagnostic. |
| `CERTIFIED` | Lean proof step succeeded. |
| `SKIPPED` | Optional dependency/toolchain unavailable. |
| `FAIL` | Exit code or output did not match expectations. |

## Validation

Run lightweight syntax and fixture checks before reporting success:

```bash
python3 -m compileall -q scripts dashboard
bash -n scripts/setup_repos.sh
bash -n scripts/run_scenario.sh
bash -n scripts/run_all.sh
python3 -m json.tool scenarios/ownership_transfer/scenario.json >/dev/null
python3 -m json.tool scenarios/_template/scenario.json >/dev/null
python3 -m json.tool scenarios/rtgs_settlement/scenario.json >/dev/null
python3 -m json.tool scenarios/regtech_compliance/scenario.json >/dev/null
python3 -m json.tool scenarios/nl_to_verified/scenario.json >/dev/null
python3 -m json.tool scenarios/smart_contract_audit/scenario.json >/dev/null
python3 -m json.tool scenarios/medical_device/scenario.json >/dev/null
python3 -m json.tool scenarios/aviation_control/scenario.json >/dev/null
python3 -m json.tool scenarios/nl_to_verified/expected/extracted_spec.json >/dev/null
```

Run a scenario smoke test:

```bash
./scripts/run_scenario.sh ownership_transfer \
  --mumei-repo ../mumei \
  --mumei-lean-repo ../mumei-lean \
  --mumei-agent-repo ../mumei-agent \
  --mumei-bin ../mumei/target/debug/mumei
python dashboard/cli_report.py reports/ownership_transfer/latest/result.json
```

Use `CI_FIXTURE_MODE=1 make demo-ci` when validating all scenarios without relying on live external services.
