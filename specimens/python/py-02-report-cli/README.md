# py-02-report-cli

A command-line billing report generator. It reads a CSV timesheet, computes
per-worker hours, billed amounts, overtime and weekend time, prints the report
to stdout, writes it to `--out`, and then runs a small post-processing step
(a line count of the generated report).

## Input format

CSV with a header row and columns:

```text
worker,date,project,duration,notes
alice,2026-09-14,apollo,8h,kickoff
```

`duration` is a value like `7h30m`, `45m` or `8h`. `notes` is optional.

## Running

```bash
./run.sh                 # generates a report for the shipped timesheets.csv
./repro.sh               # demonstrates every documented defect, exits 0 when all reproduce
```

Or manually:

```bash
python3 report.py --input timesheets.csv --rate 120 --out report.txt
```

Overtime is any daily time beyond 8h; the report also shows each worker's
overtime as a percentage of their total time and how much of their time fell
on weekend days.
