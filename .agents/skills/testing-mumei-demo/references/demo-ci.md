# Full CI-equivalent validation (`make demo-ci`)

Read this when validating the whole pipeline in fixture mode, checking `dashboard/summary.md`, or proving that `demo-ci` exits non-zero on failure.

## Full CI-equivalent validation (`make demo-ci`)

This is the fastest way to validate the complete pipeline without live LLM credentials. It runs all seven scenarios with fixture mode enabled by the Makefile target, then generates a cross-scenario summary.

```bash
# Clean stale reports first
rm -rf reports/ dashboard/summary.md dashboard/highlights.md

# Fixture mode is enabled internally by make demo-ci
make demo-ci
```

Expected assertions:

- Command exits `0`.
- `reports/{scenario}/latest/result.json` exists for all seven scenarios: `ownership_transfer`, `rtgs_settlement`, `regtech_compliance`, `nl_to_verified`, `smart_contract_audit`, `medical_device`, and `aviation_control`.
- Each `result.json` has `overall_status == "PASS"`.
- Each `result.json` has `proof_density.percentage == 100` with these densities: ownership_transfer 6/6, rtgs_settlement 6/6, regtech_compliance 5/5, nl_to_verified 3/3, smart_contract_audit 4/4, medical_device 4/4, aviation_control 3/3.
- `dashboard/summary.md` exists with a markdown table containing all seven scenario rows.
- `dashboard/summary.md` has no "Missing results" section.

### Cross-scenario summary validation

After `demo-ci`, verify the generated summary:

```bash
cat dashboard/summary.md
```

Expected table rows:

```text
| `ownership_transfer` | PASS | 6 | 6 | 100% |
| `rtgs_settlement` | PASS | 6 | 6 | 100% |
| `regtech_compliance` | PASS | 5 | 5 | 100% |
| `nl_to_verified` | PASS | 3 | 3 | 100% |
| `smart_contract_audit` | PASS | 4 | 4 | 100% |
| `medical_device` | PASS | 4 | 4 | 100% |
| `aviation_control` | PASS | 3 | 3 | 100% |
```

You can also generate the summary standalone:

```bash
python3 scripts/generate_report.py --summary --require-all
```

### Negative test for `demo-ci` non-zero exit

To verify that `demo-ci` returns non-zero on failure, set `MUMEI_BIN` to a non-existent path:

```bash
rm -rf reports/ dashboard/summary.md
MUMEI_BIN=/nonexistent/mumei make demo-ci; echo "EXIT_CODE=$?"
```

Expected: exit code is non-zero. All seven scenarios still run with continue-on-failure behavior and `dashboard/summary.md` is still generated.

Tip: Corrupting `.mm` source files may not trigger a failure because `mumei verify` can report "0 item(s) verified" with exit code 0 when the file contains no atoms. Use a missing binary or missing scenario config to force a definitive failure instead.
