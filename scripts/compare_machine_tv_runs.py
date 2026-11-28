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
TIMING_THRESHOLD_SECONDS = 0.1
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
        if item["base_status"] != item["repeat_status"] or (
            seconds_delta is not None and abs(seconds_delta) >= TIMING_THRESHOLD_SECONDS
        ):
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


def input_identity(case: dict, prefer_port_hashes: bool) -> dict:
    if prefer_port_hashes and isinstance(case.get("port_hashes"), dict):
        return {"port_hashes": case["port_hashes"]}
    return {"case_hash": case.get("case_hash"), "source_hash": case.get("source_hash")}


def toolchain_identity(report: dict) -> dict:
    metadata = report.get("toolchain")
    if not isinstance(metadata, dict):
        return {"status": "unavailable", "reason": "toolchain metadata missing"}
    if metadata.get("status") == "observed" and bench.valid_toolchain_observation(metadata.get("observation")):
        observation = metadata["observation"]
        identity = {
            key: observation[key]
            for key in ("host", "target_triple", "solvers", "llvm", "link")
            if key in observation
        }
        return {"status": "observed", "observation": identity}
    return {"status": "unavailable", "reason": metadata.get("reason") or "toolchain metadata unavailable"}


def flattened_metadata(value, prefix: str = "") -> dict:
    if isinstance(value, dict) and value:
        flattened = {}
        for key in sorted(value):
            flattened.update(flattened_metadata(value[key], f"{prefix}{key}."))
        return flattened
    return {prefix[:-1]: value}


def compare_toolchain_identity(base: dict, repeat: dict) -> dict:
    base_identity = toolchain_identity(base)
    repeat_identity = toolchain_identity(repeat)
    unavailable = [label for label, identity in (("base", base_identity), ("repeat", repeat_identity))
                   if identity.get("status") != "observed"]
    changed_fields = []
    if not unavailable:
        base_flat = flattened_metadata(base_identity["observation"])
        repeat_flat = flattened_metadata(repeat_identity["observation"])
        changed_fields = sorted(key for key in set(base_flat) | set(repeat_flat)
                                if base_flat.get(key) != repeat_flat.get(key))
    return {
        "matches": not unavailable and not changed_fields,
        "unavailable": unavailable,
        "changed_fields": changed_fields,
    }


def compare_reports(base: dict, repeat: dict) -> dict:
    base_cases = {case.get("id"): case for case in base["cases"] if isinstance(case, dict)}
    repeat_cases = {case.get("id"): case for case in repeat["cases"] if isinstance(case, dict)}
    common = sorted(set(base_cases) & set(repeat_cases))
    input_changes = []
    comparable = []
    for case_id in common:
        prefer_port_hashes = isinstance(base_cases[case_id].get("port_hashes"), dict) and isinstance(
            repeat_cases[case_id].get("port_hashes"), dict
        )
        before_input = input_identity(base_cases[case_id], prefer_port_hashes)
        after_input = input_identity(repeat_cases[case_id], prefer_port_hashes)
        if before_input == after_input:
            comparable.append(case_id)
        else:
            input_changes.append({"id": case_id, "base": before_input, "repeat": after_input})

    changes = []
    stage_changes = []
    outcome_transitions = Counter()
    group_transitions = Counter()
    outcome_transitions_by_variant = {variant: Counter() for variant in cb.VARIANTS}
    group_transitions_by_variant = {variant: Counter() for variant in cb.VARIANTS}
    by_variant = Counter()
    stage_result_changes = 0
    for case_id in comparable:
        for variant in cb.VARIANTS:
            base_native = base_cases[case_id].get(variant, {}).get("native", {})
            repeat_native = repeat_cases[case_id].get(variant, {}).get("native", {})
            before, after = diagnostic(base_native), diagnostic(repeat_native)
            stages = stage_differences(base_native.get("stages", {}), repeat_native.get("stages", {}))
            changed_stage_results = sum(
                item["base_status"] != item["repeat_status"] for item in stages.values()
            )
            stage_result_changes += changed_stage_results
            if before == after:
                if stages:
                    stage_changes.append({"id": case_id, "variant": variant, "stage_differences": stages})
                continue
            transition = f"{before['outcome']}->{after['outcome']}"
            group_transition = f"{OUTCOME_GROUPS.get(before['outcome'], 'unknown')}->{OUTCOME_GROUPS.get(after['outcome'], 'unknown')}"
            outcome_transitions[transition] += 1
            group_transitions[group_transition] += 1
            outcome_transitions_by_variant[variant][transition] += 1
            group_transitions_by_variant[variant][group_transition] += 1
            by_variant[variant] += 1
            changes.append({
                "id": case_id,
                "variant": variant,
                "classification": classification(before, after),
                "base": before,
                "repeat": after,
                "stage_differences": stages,
            })
    toolchain = compare_toolchain_identity(base, repeat)
    return {
        "schema_version": SCHEMA,
        "compared_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "base": report_identity(base),
        "repeat": report_identity(repeat),
        "summary": {
            "base_cases": len(base_cases),
            "repeat_cases": len(repeat_cases),
            "case_ids_in_both": len(common),
            "cases_compared": len(comparable),
            "input_changes": input_changes,
            "missing_in_base": sorted(set(repeat_cases) - set(base_cases)),
            "missing_in_repeat": sorted(set(base_cases) - set(repeat_cases)),
            "verdict_changes": len(changes),
            "verdict_changes_by_variant": dict(sorted(by_variant.items())),
            "diagnostic_changes": sum(change["classification"] == "diagnostic_changed" for change in changes),
            "outcome_transitions": dict(sorted(outcome_transitions.items())),
            "outcome_transitions_by_variant": {
                variant: dict(sorted(counts.items()))
                for variant, counts in outcome_transitions_by_variant.items() if counts
            },
            "unresolved_group_transitions": dict(sorted(group_transitions.items())),
            "unresolved_group_transitions_by_variant": {
                variant: dict(sorted(counts.items()))
                for variant, counts in group_transitions_by_variant.items() if counts
            },
            "stage_result_changes": stage_result_changes,
            "stage_changes": len(stage_changes),
            "toolchain_identity": toolchain,
        },
        "changes": changes,
        "stage_changes": stage_changes,
    }


def report_identity(doc: dict) -> dict:
    return {
        "recorded_at": doc.get("recorded_at"),
        "demo": doc.get("demo"),
        "verifier": doc.get("verifier"),
        "environment": doc.get("environment"),
        "toolchain": doc.get("toolchain"),
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
    if args.output and args.output.resolve() in {args.base.resolve(), args.repeat.resolve()}:
        print("machine-TV comparison failed: --output must not overwrite an input report", file=sys.stderr)
        return 1
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
