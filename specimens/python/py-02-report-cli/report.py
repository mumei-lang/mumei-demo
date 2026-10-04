"""Billing report generator: reads a CSV timesheet and writes a per-worker report.

Usage: python3 report.py --input timesheets.csv --rate 120 --out report.txt
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import date

import timesheet

DAILY_THRESHOLD_MINUTES = 8 * 60


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CSV timesheet billing report")
    parser.add_argument("--input", required=True, help="timesheet CSV path")
    parser.add_argument("--rate", required=True, help="hourly rate")
    parser.add_argument("--out", required=True, help="report output path")
    return parser.parse_args(argv)


def parse_row(row: list[str]) -> dict:
    """One CSV row: worker,date,project,duration[,notes]."""
    worker = row[0].strip()
    day = date.fromisoformat(row[1].strip())
    project = row[2].strip()
    minutes = timesheet.parse_duration(row[3].strip())
    note = row[4].strip() if len(row) > 4 else ""
    return {"worker": worker, "day": day, "project": project, "minutes": minutes, "note": note}


def load_entries(path: str) -> list[dict]:
    entries = []
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row or row[0].strip() == "worker" or row[0].startswith("#"):
                continue
            try:
                entries.append(parse_row(row))
            except Exception:
                break
    return entries


def aggregate(entries: list[dict]) -> dict:
    per_worker: dict[str, dict] = {}
    for e in entries:
        w = per_worker.setdefault(e["worker"], {"total": 0, "daily": {}, "weekend": 0})
        w["total"] += e["minutes"]
        w["daily"][e["day"]] = w["daily"].get(e["day"], 0) + e["minutes"]
        if timesheet.is_weekend(e["day"]):
            w["weekend"] += e["minutes"]
    return per_worker


def render(per_worker: dict, rate) -> str:
    lines = ["BILLING REPORT", "==============", ""]
    total_amount = 0.0
    for worker in sorted(per_worker):
        w = per_worker[worker]
        hours = w["total"] / 60
        amount = hours * rate
        total_amount += amount
        overtime = timesheet.overtime_minutes(list(w["daily"].values()), DAILY_THRESHOLD_MINUTES)
        overtime_pct = timesheet.share_of_total(overtime, w["total"]) * 100
        lines.append(f"worker: {worker}")
        lines.append(f"  hours: {hours:.2f}")
        lines.append(f"  amount: ${amount}")
        lines.append(f"  overtime: {timesheet.format_minutes(overtime)} ({overtime_pct:.1f}%)")
        lines.append(f"  weekend: {timesheet.format_minutes(w['weekend'])}")
        lines.append("")
    lines.append(f"TOTAL: ${total_amount}")
    return "\n".join(lines)


def post_process(out_path: str) -> None:
    subprocess.run(f"wc -l {out_path}", shell=True, check=False)


def main(argv=None) -> int:
    args = parse_args(argv)
    entries = load_entries(args.input)
    per_worker = aggregate(entries)
    report = render(per_worker, float(args.rate))
    print(report)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    post_process(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
