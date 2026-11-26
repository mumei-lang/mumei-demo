#!/usr/bin/env python3
"""Compare two machine-TV benchmark reports by case, variant, stage, and diagnostic."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_contract_bench as cb  # noqa: E402
import run_machine_tv_bench as bench  # noqa: E402

SCHEMA = "mumei-demo.machine-tv-run-diff/v1"
EXPECTED_REPORT_SCHEMA = "mumei-demo.machine-tv-bench/v1"
ASSURANCE_OUTCOMES = ("accepted",) + bench.REJECTION_OUTCOMES
OUTCOME_GROUPS = {
    outcome: label
    for label, outcomes in bench.UNRESOLVED_OUTCOME_GROUPS.items()
    for outcome in outcomes
}
for outcome in ASSURANCE_OUTCOMES:
    OUTCOME_GROUPS[outcome] = "assurance"


def load_report(path: Path) -> dict:
    doc = json.loads(path.read_text())
    if doc.get("schema_version") != EXPECTED_REPORT_SCHEMA or not isinstance(doc.get("cases"), list):
        raise ValueError(f"{path} is not a {EXPECTED_REPORT_SCHEMA} report")
    return doc


def diagnostic(native: dict) -> dict:
    return {
        "outcome": native.get("outcome"),
        "reason": native.get("reason"),
        "failure_kind": native.get("failure_kind"),
    }


def stage_status(slot: dict | None) -> str:
    if not isinstance(slot, dict):
        return "missing"
    if slot.get("error") == "timeout":
        return "timeout"
    if slot.get("error"):
        return "environment_error"
    if slot.get("exit") == 0:
        return "ok"
    if isinstance(slot.get("exit"), int):
        return "failed"
    return "missing"


def stage_differences(base: dict, repeat: dict) -> dict:
    differences = {}
    for name in sorted(set(base) | set(repeat)):
        before, after = base.get(name), repeat.get(name)
        seconds_delta = None
        if cb.numeric_measurement((before or {}).get("seconds")) and cb.numeric_measurement((after or {}).get("seconds")):
            seconds_delta = round(after["seconds"] - before["seconds"], 3)
        item = {
            "base_status": stage_status(before),
            "repeat_status": stage_status(after),
            "base_seconds": (before or {}).get("seconds"),
            "repeat_seconds": (after or {}).get("seconds"),
            "seconds_delta": seconds_delta,
            "base_budget_seconds": (before or {}).get("budget_seconds"),
            "repeat_budget_seconds": (after or {}).get("budget_seconds"),
        }
        if item["base_status"] != item["repeat_status"] or seconds_delta not in (None, 0.0):
            differences[name] = item
    return differences


def classification(before: dict, after: dict) -> str:
    base_outcome, repeat_outcome = before["outcome"], after["outcome"]
    if base_outcome == repeat_outcome:
        return "diagnostic_changed"
    if "accepted" in {base_outcome, repeat_outcome}:
        return "acceptance_changed"
    base_group, repeat_group = OUTCOME_GROUPS.get(base_outcome), OUTCOME_GROUPS.get(repeat_outcome)
    if base_group != repeat_group:
        return "unresolved_kind_changed"
    return "outcome_changed"


def compare_reports(base: dict, repeat: dict) -> dict:
    base_cases = {case.get("id"): case for case in base["cases"] if isinstance(case, dict)}
    repeat_cases = {case.get("id"): case for case in repeat["cases"] if isinstance(case, dict)}
    common = sorted(set(base_cases) & set(repeat_cases))
    changes = []
    outcome_transitions = Counter()
    group_transitions = Counter()
    by_variant = Counter()
    stage_result_changes = 0
    for case_id in common:
        for variant in cb.VARIANTS:
            base_native = base_cases[case_id].get(variant, {}).get("native", {})
            repeat_native = repeat_cases[case_id].get(variant, {}).get("native", {})
            before, after = diagnostic(base_native), diagnostic(repeat_native)
            if before == after:
                continue
            stages = stage_differences(base_native.get("stages", {}), repeat_native.get("stages", {}))
            stage_result_changes += sum(
                item["base_status"] != item["repeat_status"] for item in stages.values()
            )
            transition = f"{before['outcome']}->{after['outcome']}"
            group_transition = f"{OUTCOME_GROUPS.get(before['outcome'], 'unknown')}->{OUTCOME_GROUPS.get(after['outcome'], 'unknown')}"
            outcome_transitions[transition] += 1
            group_transitions[group_transition] += 1
            by_variant[variant] += 1
            changes.append({
                "id": case_id,
                "variant": variant,
                "classification": classification(before, after),
                "base": before,
                "repeat": after,
                "stage_differences": stages,
            })
    return {
        "schema_version": SCHEMA,
        "compared_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "base": report_identity(base),
        "repeat": report_identity(repeat),
        "summary": {
            "base_cases": len(base_cases),
            "repeat_cases": len(repeat_cases),
            "cases_compared": len(common),
            "missing_in_base": sorted(set(repeat_cases) - set(base_cases)),
            "missing_in_repeat": sorted(set(base_cases) - set(repeat_cases)),
            "verdict_changes": len(changes),
            "verdict_changes_by_variant": dict(sorted(by_variant.items())),
            "outcome_transitions": dict(sorted(outcome_transitions.items())),
            "unresolved_group_transitions": dict(sorted(group_transitions.items())),
            "stage_result_changes": stage_result_changes,
        },
        "changes": changes,
    }


def report_identity(doc: dict) -> dict:
    return {
        "recorded_at": doc.get("recorded_at"),
        "demo": doc.get("demo"),
        "verifier": doc.get("verifier"),
        "environment": doc.get("environment"),
        "settings": doc.get("settings"),
        "seconds": doc.get("seconds"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path, help="first machine-TV benchmark JSON report")
    parser.add_argument("repeat", type=Path, help="repeat machine-TV benchmark JSON report")
    parser.add_argument("--output", type=Path, help="write the complete machine-readable comparison here")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        diff = compare_reports(load_report(args.base), load_report(args.repeat))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"machine-TV comparison failed: {exc}", file=sys.stderr)
        return 1
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(diff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(diff["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
