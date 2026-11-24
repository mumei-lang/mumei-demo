# CLI report (`dashboard/cli_report.py`)

Read this when rendering a scenario's latest `result.json` as a CLI report and checking the expected per-scenario output strings.

## CLI report

After running a scenario, render its latest report:

```bash
python3 dashboard/cli_report.py reports/regtech_compliance/latest/result.json
python3 dashboard/cli_report.py reports/rtgs_settlement/latest/result.json
python3 dashboard/cli_report.py reports/ownership_transfer/latest/result.json
python3 dashboard/cli_report.py reports/nl_to_verified/latest/result.json
```

Expected assertions:

- Output includes `BEFORE: LLM alone`, `AFTER: LLM + mumei`, `Audit Status:  TRUSTLESS`, and `Moment:        Proof failure → Bug found`.
- RegTech output includes `buggy_classify_risk misses PEP customer type in match`, `Non-exhaustive match catches the bug before deployment`, `Z3 Negative Test Suite`, and `Proof Density: 100% (5/5 atoms or layer steps verified)`.
- RegTech output must not contain `L3: Lean`.
- RTGS output includes the visible prefix `hostile_settlement skips validate and tries Pending → Settle` and `Proof Density: 100% (6/6 atoms)`.
- Ownership output includes `hostile_takeover skips accept and tries Idle → Transferred`.
- Natural-language output includes `Mumei Verification Report: Natural Language to Verified Mumei`, all three PASS steps, and `Proof Density: 100% (3/3 atoms)`.
- The CLI box is fixed-width, so long visible narrative may be truncated; verify full untruncated narrative strings in `result.json`.
