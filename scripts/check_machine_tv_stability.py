#!/usr/bin/env python3
"""Run a focused machine-TV benchmark matrix twice and compare repeat stability."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_machine_tv_runs as compare  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
MATRIX = (
    "GO01-D05",
    "RS01-D04",
    "RS03-D02",
    "PY02-D02",
    "GO01-D04",
    "PY02-D08",
    "RS03-D03",
    "GO01-D02",
    "PY02-D05",
)


def run_benchmark(mumei_bin: str, output: Path, jobs: int, timeout: int) -> None:
    cmd = [sys.executable, str(REPO_ROOT / "scripts/run_machine_tv_bench.py"), "--mumei-bin", mumei_bin,
           "--output", str(output), "--jobs", str(jobs), "--timeout", str(timeout)]
    for case_id in MATRIX:
        cmd.extend(("--only", case_id))
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"machine-TV benchmark failed for {output.name}: {proc.stderr.strip() or proc.stdout.strip()}")


def false_acceptances(report: dict) -> int:
    total = 0
    for case in report.get("cases", []):
        for variant in ("buggy", "fixed"):
            slot = case.get(variant, {})
            if slot.get("z3", {}).get("outcome") == "refuted" and slot.get("native", {}).get("outcome") == "accepted":
                total += 1
    return total


def stability_failures(diff: dict, base: dict, repeat: dict) -> list[str]:
    summary = diff["summary"]
    failures = []
    if summary.get("input_changes"):
        failures.append("input identity changed between repeats")
    if summary.get("missing_in_base") or summary.get("missing_in_repeat"):
        failures.append("case presence changed between repeats")
    if summary.get("outcome_transitions"):
        failures.append(f"outcome transitions: {summary['outcome_transitions']}")
    if summary.get("unresolved_group_transitions"):
        failures.append(f"unresolved-group transitions: {summary['unresolved_group_transitions']}")
    if summary.get("stage_result_changes"):
        failures.append(f"stage result changes: {summary['stage_result_changes']}")
    for label, report in (("base", base), ("repeat", repeat)):
        count = false_acceptances(report)
        if count:
            failures.append(f"{label} false acceptance count is {count}")
    return failures


def variant_counts(report: dict) -> dict:
    return {variant: report["summary"]["native"][variant]["outcomes"] for variant in ("buggy", "fixed")}


def write_summary(path: Path, diff: dict, failures: list[str]) -> None:
    summary = diff["summary"]
    lines = [
        "# Machine-TV repeat stability",
        "",
        "Focused repeat smoke only; not a proof grade, unified verdict, or full benchmark replacement.",
        "",
        f"- Cases compared: {summary['cases_compared']}",
        f"- Outcome transitions: {summary['outcome_transitions'] or '{}'}",
        f"- Unresolved-group transitions: {summary['unresolved_group_transitions'] or '{}'}",
        f"- Stage-result changes: {summary['stage_result_changes']}",
        f"- Timing-only stage differences: {summary['stage_changes']}",
        f"- Stability failures: {len(failures)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mumei-bin", required=True, help="mumei binary used for both repeat runs")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "reports/machine-tv-stability")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=120)
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.jobs < 1 or args.timeout < 1:
        print("--jobs and --timeout must be positive", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    base_path = args.output_dir / "machine_tv_base.json"
    repeat_path = args.output_dir / "machine_tv_repeat.json"
    diff_path = args.output_dir / "machine_tv_diff.json"
    summary_path = args.output_dir / "summary.md"
    try:
        run_benchmark(args.mumei_bin, base_path, args.jobs, args.timeout)
        run_benchmark(args.mumei_bin, repeat_path, args.jobs, args.timeout)
        base, repeat = compare.load_report(base_path), compare.load_report(repeat_path)
        diff = compare.compare_reports(base, repeat)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"machine-TV stability check failed: {exc}", file=sys.stderr)
        return 1
    diff_path.write_text(json.dumps(diff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    failures = stability_failures(diff, base, repeat)
    write_summary(summary_path, diff, failures)
    print(json.dumps({
        "matrix_cases": len(MATRIX),
        "cases_compared": diff["summary"]["cases_compared"],
        "base": variant_counts(base),
        "repeat": variant_counts(repeat),
        "outcome_transitions": diff["summary"]["outcome_transitions"],
        "unresolved_group_transitions": diff["summary"]["unresolved_group_transitions"],
        "stage_result_changes": diff["summary"]["stage_result_changes"],
        "timing_only_stage_differences": diff["summary"]["stage_changes"],
        "false_acceptances": {"base": false_acceptances(base), "repeat": false_acceptances(repeat)},
        "failures": failures,
    }, indent=2, ensure_ascii=False))
    print(f"Wrote {args.output_dir}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
