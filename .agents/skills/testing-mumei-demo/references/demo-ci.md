# Full CI-equivalent validation (`make demo-ci`)

Read this when validating the whole pipeline in fixture mode, checking `dashboard/summary.md`, or proving that `demo-ci` exits non-zero on failure.

## Full CI-equivalent validation (`make demo-ci`)

This is the fastest way to validate the complete pipeline without live LLM credentials. It runs every scenario in the Makefile's `SCENARIOS` list (currently 18) with fixture mode enabled by the Makefile target, then generates a cross-scenario summary.

```bash
# Clean stale reports first
rm -rf reports/ dashboard/summary.md dashboard/highlights.md

# Fixture mode is enabled internally by make demo-ci
make demo-ci
```

Expected assertions:

- Command exits `0`.
- `reports/{scenario}/latest/result.json` exists for every scenario in `SCENARIOS` (check the Makefile for the current list).
- Each `result.json` has `overall_status == "PASS"`.
- `dashboard/summary.md` exists with a markdown table containing a row per scenario.
- `dashboard/summary.md` has no "Missing results" section.

### Cross-scenario summary validation

After `demo-ci`, verify the generated summary:

```bash
cat dashboard/summary.md
```

Expected: one `PASS` row per `SCENARIOS` entry (scenario names and proof
densities evolve; compare against the Makefile rather than a fixed table).

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

Expected: exit code is non-zero. Every scenario still runs with continue-on-failure behavior and `dashboard/summary.md` is still generated.

Tip: Corrupting `.mm` source files may not trigger a failure because `mumei verify` can report "0 item(s) verified" with exit code 0 when the file contains no atoms. Use a missing binary or missing scenario config to force a definitive failure instead.
