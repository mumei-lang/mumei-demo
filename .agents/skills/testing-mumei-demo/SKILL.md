---
name: testing-mumei-demo
description: Test mumei-demo scenarios end-to-end through make demo, CLI report output, Lean bridge regression checks, natural-language extraction, and Streamlit dashboard evidence.
---
# Testing mumei-demo

## Devin Secrets Needed

- `OPENAI_API_KEY`: required only for live scenarios that call `mumei-agent` LLM extraction/generation, such as direct non-fixture `nl_to_verified` runs.
- Individual demos and `make demo-ci` can run without API keys, browser login, or external service credentials when fixture mode is enabled by the target.
- Live `make demo` runs the integrated all-scenario sequence and may require `OPENAI_API_KEY` for the non-fixture natural-language scenario.

## Prerequisites

- A sibling checkout of `mumei` should exist at `../mumei` and provide a built binary at `../mumei/target/debug/mumei` or `../mumei/target/release/mumei`.
- Sibling checkouts of `mumei-agent` and `mumei-lean` should exist at `../mumei-agent` and `../mumei-lean`.
- RTGS Settlement validation requires `forge_tasks/vstd_settlement.json` in the default `../mumei-agent` checkout.
- RegTech Compliance validation requires `forge_tasks/vstd_regtech.json` in the default `../mumei-agent` checkout.
- RegTech Compliance validation also requires `std/compliance.mm` in the sibling `../mumei` checkout (resolved via `MUMEI_STD_PATH`, which defaults to `{mumei_repo}/std`). `correct_code.mm` imports this module via `import "std/compliance" as compliance;` and the verify step will fail if the file is missing.
- Natural-language validation requires the companion `mumei-agent` checkout to support `python -m agent extract-spec` and `python -m agent generate` for forge task specs.
- If the dashboard needs dependencies, install them with:

```bash
python -m pip install -r dashboard/requirements.txt
```

## Static checks

Run from the repo root:

```bash
python3 -m compileall -q scripts dashboard
bash -n scripts/setup_repos.sh
bash -n scripts/run_scenario.sh
bash -n scripts/run_all.sh
python3 -m json.tool scenarios/ownership_transfer/scenario.json >/dev/null
python3 -m json.tool scenarios/rtgs_settlement/scenario.json >/dev/null
python3 -m json.tool scenarios/regtech_compliance/scenario.json >/dev/null
python3 -m json.tool scenarios/nl_to_verified/scenario.json >/dev/null
python3 -m json.tool scenarios/no_mm_audit/scenario.json >/dev/null
python3 -m json.tool scenarios/spec_code_verification_suite/scenario.json >/dev/null
python3 -m json.tool scenarios/smart_contract_audit/scenario.json >/dev/null
python3 -m json.tool scenarios/medical_device/scenario.json >/dev/null
python3 -m json.tool scenarios/aviation_control/scenario.json >/dev/null
python3 -m json.tool scenarios/nl_to_verified/expected/extracted_spec.json >/dev/null
```

## Quick start

1. Run the static checks above.
2. Run the deterministic fixture-mode pipeline (no API keys needed):

```bash
rm -rf reports/ dashboard/summary.md dashboard/highlights.md
make demo-ci
```

3. Pick the focused flow for what you changed (table below) and check its expected assertions in the linked reference.
4. Clean `reports/<scenario>` before committing repo changes.

## Which flow to run

| Change touches | Run | Reference |
| --- | --- | --- |
| Anything / full pipeline without LLM credentials | `make demo-ci` | [references/demo-ci.md](references/demo-ci.md) |
| `scenarios/no_mm_audit/*`, `scenarios/spec_code_verification_suite/*`, no-`.mm` audit docs, V1-A..V1-D mode mapping | `CI_FIXTURE_MODE=1 ./scripts/run_scenario.sh <scenario>` | [references/focused-fixture-scenarios.md](references/focused-fixture-scenarios.md) |
| One primary scenario (RegTech, NL to Verified, RTGS, ownership) | `make demo-regtech`, `make demo-ownership`, or `./scripts/run_scenario.sh <scenario>` | [references/primary-demos.md](references/primary-demos.md) |
| CLI report rendering | `python3 dashboard/cli_report.py reports/<scenario>/latest/result.json` | [references/cli-report.md](references/cli-report.md) |
| Lean bridge / L3 path | fake failing `lake` + `make demo-ownership` | [references/lean-bridge-regression.md](references/lean-bridge-regression.md) |
| Streamlit dashboard | `streamlit run dashboard/app.py` | [references/dashboard.md](references/dashboard.md) |
| Scale scenarios (Priority 16) | `make demo-scale` | [references/scale-scenarios.md](references/scale-scenarios.md) |

## General tips

- Lean builds are slow on first run (~160s) but cached afterward (~0.6s). If you see long Lean build times, that is expected for the first invocation.
- The first run of `make demo-ci` may take 3-5 minutes due to Lean compilation. Subsequent runs are much faster.
- All testing is shell-only CLI output unless testing the Streamlit dashboard; no browser recording is needed for CLI-only validation.
- When running `demo-ci`, always clean `reports/` and `dashboard/summary.md` first to avoid stale data from previous runs.
- If running `./scripts/run_scenario.sh nl_to_verified` directly without `CI_FIXTURE_MODE=1`, expect a live LLM call and require `OPENAI_API_KEY`.

## Reference files

- Read [references/demo-ci.md](references/demo-ci.md) when validating the full fixture-mode pipeline, the cross-scenario summary, or the `demo-ci` non-zero exit.
- Read [references/focused-fixture-scenarios.md](references/focused-fixture-scenarios.md) when changing `no_mm_audit` or `spec_code_verification_suite`.
- Read [references/primary-demos.md](references/primary-demos.md) when running a primary scenario (RegTech, NL to Verified incl. fixture mode, RTGS, ownership) on its own.
- Read [references/cli-report.md](references/cli-report.md) when checking `dashboard/cli_report.py` output.
- Read [references/lean-bridge-regression.md](references/lean-bridge-regression.md) when touching the Lean bridge failure path.
- Read [references/dashboard.md](references/dashboard.md) when testing or recording the Streamlit dashboard.
- Read [references/scale-scenarios.md](references/scale-scenarios.md) when running scale targets or debugging verify caching and known non-fixture failures.
