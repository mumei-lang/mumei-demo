#!/usr/bin/env python3
"""Regression gate for false alarms on fixed specimen variants.

This is an offline gate over the committed no-LLM `audit/coverage.json`
artifacts.  It does not rerun `mumei-agent audit`; it prevents the recorded
fixed-variant alarm count from silently moving upward and keeps unreviewed
fixed-variant findings visible as adjudication debt.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECIMENS_ROOT = REPO_ROOT / "specimens"
HISTORY_PATH = SPECIMENS_ROOT / "scoreboard" / "history.json"
BUDGET_PATH = SPECIMENS_ROOT / "scoreboard" / "fixed_alarm_budget.json"
BUDGET_SCHEMA = "mumei-demo.fixed-alarm-budget/v1"


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_budget(path: Path = BUDGET_PATH) -> dict:
    budget = load_json(path)
    required = {"schema", "mode", "max_false_alarms", "max_unreviewed", "min_specimens", "notes"}
    missing = sorted(required - set(budget))
    if missing:
        raise ValueError(f"{path} is missing keys: {', '.join(missing)}")
    if budget["schema"] != BUDGET_SCHEMA:
        raise ValueError(f"{path} has unsupported schema {budget['schema']!r}")
    if budget["mode"] != "no_llm":
        raise ValueError("fixed-alarm regression currently gates the deterministic no-LLM audit artifacts")
    for key in ("max_false_alarms", "max_unreviewed", "min_specimens"):
        if type(budget[key]) is not int or budget[key] < 0:
            raise ValueError(f"{path}: {key} must be a non-negative integer")
    return budget


def coverage_rows(root: Path = SPECIMENS_ROOT) -> list[dict]:
    rows = []
    for path in sorted(root.glob("*/*/audit/coverage.json")):
        data = load_json(path)
        fixed = data.get("fixed")
        if not isinstance(fixed, dict):
            continue
        counts = fixed.get("finding_counts") or {}
        rows.append({
            "specimen": data.get("specimen") or path.parts[-3],
            "path": path,
            "false_alarms": fixed.get("false_alarms", 0),
            "findings": counts.get("total", 0),
            "real": counts.get("real", 0),
            "unreviewed": counts.get("unreviewed", 0),
            "still_reported": len(fixed.get("still_reported") or []),
        })
    return rows


def aggregate(rows: list[dict]) -> dict:
    return {
        "specimens": len(rows),
        "false_alarms": sum(row["false_alarms"] for row in rows),
        "findings": sum(row["findings"] for row in rows),
        "real": sum(row["real"] for row in rows),
        "unreviewed": sum(row["unreviewed"] for row in rows),
        "still_reported": sum(row["still_reported"] for row in rows),
    }


def latest_no_llm_fixed(history_path: Path = HISTORY_PATH) -> dict | None:
    history = load_json(history_path)
    runs = history.get("runs")
    if not isinstance(runs, list):
        return None
    for run in reversed(runs):
        if isinstance(run, dict) and run.get("llm") is False and isinstance(run.get("fixed"), dict):
            return run["fixed"]
    return None


def evaluate(root: Path = SPECIMENS_ROOT, history_path: Path = HISTORY_PATH, budget_path: Path = BUDGET_PATH) -> dict:
    budget = load_budget(budget_path)
    rows = coverage_rows(root)
    total = aggregate(rows)
    errors = []
    if total["specimens"] < budget["min_specimens"]:
        errors.append(
            f"only {total['specimens']} fixed-variant coverage artifacts found; expected at least {budget['min_specimens']}"
        )
    if total["false_alarms"] > budget["max_false_alarms"]:
        errors.append(
            f"fixed-variant false alarms regressed: {total['false_alarms']} > budget {budget['max_false_alarms']}"
        )
    if total["unreviewed"] > budget["max_unreviewed"]:
        errors.append(
            f"unreviewed fixed-variant findings regressed: {total['unreviewed']} > budget {budget['max_unreviewed']}"
        )
    history_fixed = latest_no_llm_fixed(history_path)
    history_comparison = "not_available"
    if history_fixed is not None:
        compared = {}
        for key in ("specimens", "findings", "real", "false_alarms", "still_reported"):
            if key in history_fixed:
                compared[key] = (total[key], history_fixed[key])
        mismatches = {key: values for key, values in compared.items() if values[0] != values[1]}
        history_comparison = "match" if not mismatches else "mismatch"
        if mismatches:
            details = ", ".join(f"{key}: coverage {now} != history {recorded}" for key, (now, recorded) in sorted(mismatches.items()))
            errors.append(f"committed coverage and latest no-LLM history disagree: {details}")
    offenders = sorted(rows, key=lambda row: (-row["false_alarms"], row["specimen"]))
    return {
        "schema": "mumei-demo.fixed-alarm-regression/v1",
        "budget": budget,
        "total": total,
        "rows": rows,
        "top_offenders": [row for row in offenders if row["false_alarms"]][:5],
        "history_comparison": history_comparison,
        "errors": errors,
        "status": "pass" if not errors else "fail",
    }


def render_text(result: dict) -> str:
    total = result["total"]
    lines = [
        "fixed-alarm regression gate:",
        f"  specimens: {total['specimens']}",
        f"  false alarms: {total['false_alarms']} / budget {result['budget']['max_false_alarms']}",
        f"  unreviewed fixed findings: {total['unreviewed']} / budget {result['budget']['max_unreviewed']}",
        f"  history comparison: {result['history_comparison']}",
    ]
    if result["top_offenders"]:
        lines.append("  largest fixed-alarm contributors:")
        lines.extend(
            f"    {row['specimen']}: {row['false_alarms']} alarms, {row['unreviewed']} unreviewed"
            for row in result["top_offenders"]
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SPECIMENS_ROOT)
    parser.add_argument("--history", type=Path, default=HISTORY_PATH)
    parser.add_argument("--budget", type=Path, default=BUDGET_PATH)
    parser.add_argument("--json", action="store_true", help="print the machine-readable evaluation")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = evaluate(args.root, args.history, args.budget)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        printable = {key: value for key, value in result.items() if key != "rows"}
        printable["rows"] = [
            {key: value for key, value in row.items() if key != "path"} for row in result["rows"]
        ]
        print(json.dumps(printable, indent=2, sort_keys=True))
    else:
        print(render_text(result))
    for error in result["errors"]:
        print(f"error: {error}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
