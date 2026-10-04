# Python specimens

Runnable Python 3.10+ (standard library only) apps and tools for the specimen
corpus. See [../README.md](../README.md) for the conventions; each specimen's
`DEFECTS.json` is the ground truth.

| id | kind | description | default port | defects |
|---|---|---|---|---|
| [py-01-expense-tracker](py-01-expense-tracker/) | web | SQLite-backed HTTP expense tracker with budgets, monthly summaries and CSV export | 8311 | 11 |
| [py-02-report-cli](py-02-report-cli/) | cli | CSV timesheet billing report: per-worker hours, amounts, overtime and weekend time | — | 9 |
| [py-03-ledger-api](py-03-ledger-api/) | web | In-memory double-entry ledger API with accounts, fee-bearing transfers and paginated statements | 8312 | 10 |
| [py-04-doc-vault](py-04-doc-vault/) | web | Token-gated document vault: uploads, share links, remote import and per-user quotas | 8313 | 11 |

Every specimen has `run.sh` (happy path, exits 0) and `repro.sh` (one case per
defect in `DEFECTS.json`, exits 0 when all reproduce).

```bash
for d in py-*/; do (cd "$d" && ./run.sh >/dev/null && ./repro.sh); done
```
