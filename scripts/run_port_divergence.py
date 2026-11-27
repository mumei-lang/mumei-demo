#!/usr/bin/env python3
"""Replay reference counterexamples on the bench's accepted buggy LLM ports."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import run_contract_bench as bench
import run_native_replay as replay
from port_fidelity import (  # noqa: E402
    body_inner,
    fixed_variant_outcome,
    lint,
    lint_contract,
    lint_findings,
    outcome,
    scrub,
    success_flag_paths,
    token_pattern,
    usable_body,
)


def replay_verdict(mumei_bin: str, case: dict, port: str, values: dict, timeout: int) -> dict:
    try:
        return replay.port_verdict(mumei_bin, port, case["atom"], values, timeout)
    except ValueError as error:
        return {"verdict": "inconclusive", "status": "bad input", "diagnostics": [str(error)],
                "verification_attempted": False}


def replay_verdict(mumei_bin: str, case: dict, port: str, values: dict, timeout: int) -> dict:
    try:
        return replay.port_verdict(mumei_bin, port, case["atom"], values, timeout)
    except ValueError as error:
        return {"verdict": "inconclusive", "status": "bad input", "diagnostics": [str(error)],
                "verification_attempted": False}


def outcome(inputs: list[dict]) -> str:
    if any(i["reference"]["verdict"] == "breaks" and i["llm"]["verdict"] == "holds" for i in inputs):
        return "diverged"
    if not inputs or any(i["reference"]["verdict"] != "breaks" or i["llm"]["verdict"] != "breaks"
                         for i in inputs):
        return "inconclusive"
    return "still_refutes"


def fixed_variant_outcome(inputs: list[dict]) -> str:
    """Replay outcome for a fixed candidate against the fixed reference port.

    ``diverged`` means the candidate breaks an input that the fixed reference
    satisfies. ``still_holds`` requires both sides to hold every supplied input;
    missing or unresolved verification is explicit non-evidence.
    """
    if any(i["reference"]["verdict"] == "holds" and i["llm"]["verdict"] == "breaks" for i in inputs):
        return "diverged"
    if not inputs or any(i["reference"]["verdict"] != "holds" or i["llm"]["verdict"] != "holds"
                         for i in inputs):
        return "inconclusive"
    return "still_holds"


def raw_verifier_outcome(result: dict) -> str | None:
    """The verifier outcome before the benchmark's fidelity acceptance gate."""
    return result.get("verifier_outcome", result.get("outcome"))


def collect(cases: list[dict], doc: dict, mumei_bin: str, timeout: int) -> dict:
    by_id = {c["id"]: c for c in cases}
    reference = {}
    rows = []
    for run, records in enumerate(doc["runs"], 1):
        for record in records:
            buggy = record["buggy"]
            if raw_verifier_outcome(buggy) != "proven":
                continue
            case_id = record["id"]
            case = by_id[case_id]
            if case_id not in reference:
                reference[case_id] = [
                    {**w, "reference": replay_verdict(mumei_bin, case, case["ports"]["buggy"], w["values"], timeout)}
                    for w in replay.replay_inputs(case)[0]
                ]
            body = buggy.get("body")
            port = bench.assemble(case, body) if usable_body(body) else None
            inputs = []
            for witness in reference[case_id]:
                if port is not None:
                    llm = replay_verdict(mumei_bin, case, port, witness["values"], timeout)
                else:
                    llm = {"verdict": "inconclusive", "status": "missing or invalid body", "diagnostics": [],
                           "verification_attempted": False}
                inputs.append({**witness, "llm": llm})
            linted = lint_findings(case, body, "buggy") if port is not None else []
            rows.append({"case": case_id, "run": run, "outcome": outcome(inputs),
                         "bench_outcome": buggy["outcome"], "verifier_outcome": raw_verifier_outcome(buggy),
                         "fidelity_gate": buggy.get("fidelity_gate"),
                         "lint": [finding["message"] for finding in linted],
                         "lint_findings": linted, "inputs": inputs})
    reference_verdicts = [witness["reference"] for inputs in reference.values() for witness in inputs]
    llm_verdicts = [witness["llm"] for row in rows for witness in row["inputs"]]
    lint_counts = Counter(
        f"{finding['kind']}:{finding['operation']}" if finding.get("operation") else finding["kind"]
        for row in rows for finding in row["lint_findings"]
    )
    return {"model": doc["model"], "runs": len(doc["runs"]), "cases": len(reference),
            "outcomes": dict(sorted(Counter(row["outcome"] for row in rows).items())),
            "lint_counts": dict(sorted(lint_counts.items())),
            "unresolved": {"reference": replay.unresolved_counts(reference_verdicts),
                           "llm_ports": replay.unresolved_counts(llm_verdicts)},
            "measurement": {"reference": replay.measurement_stats(reference_verdicts),
                            "llm_ports": replay.measurement_stats(llm_verdicts)},
            "misaccepts": rows}


def render(report: dict) -> str:
    rows = sorted(report["misaccepts"], key=lambda r: (r["case"], r["run"]))
    lines = [f"{report['model']}: {len(rows)} raw verifier buggy accepts across {report['cases']} cases "
             f"({report['runs']} runs)"]
    lines += [f"{name}: {total}" for name, total in report["outcomes"].items()]
    if report.get("lint_counts"):
        lines.append("lint findings: " + ", ".join(
            f"{kind} {count}" for kind, count in report["lint_counts"].items()))
    for key, label in (("reference", "reference"), ("llm_ports", "LLM port")):
        unresolved = report["unresolved"][key]
        measured = report["measurement"][key]
        lines.append(f"{label} unresolved: unsupported {unresolved['unsupported']}, "
                     f"inconclusive {unresolved['inconclusive']}, "
                     f"environment failure {unresolved['environment_failure']}, "
                     f"budget exhausted {unresolved['budget_exhausted']}")
        lines.append(f"{label} verifier measurement: {measured['seconds']:.1f}s across "
                     f"{measured['timed_calls']} of {measured['expected_calls']} calls; budget "
                     f"{measured['budget_seconds']:.1f}s across {measured['budgeted_calls']} of "
                     f"{measured['expected_calls']} calls")
    lines += [f"{r['case']} run {r['run']}: {r['outcome']}" + (f" ({'; '.join(r['lint'])})" if r["lint"] else "")
              for r in rows]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="limit to one recorded model")
    parser.add_argument("--mumei-bin", default=os.environ.get("MUMEI_BIN") or shutil.which("mumei"),
                        help="Mumei binary (default: $MUMEI_BIN, then mumei on PATH)")
    parser.add_argument("--timeout", type=int, default=120, help="per-verification timeout in seconds")
    parser.add_argument("--json", action="store_true", help="include witness inputs and both verifier verdicts")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    binary = shutil.which(args.mumei_bin) if args.mumei_bin else None
    if not binary or args.timeout <= 0:
        parser.error("provide an executable Mumei binary and a positive timeout")
    docs = [d for d in bench.load_results()
            if d["arm"] == "mumei-llm" and (args.model is None or args.model == d["model"])]
    if not docs:
        parser.error("no matching recorded mumei-llm results")
    cases, errors = bench.load_cases()
    for doc in docs:
        errors.extend(bench.stale_records(cases, [doc]))
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    try:
        reports = [collect(cases, doc, str(Path(binary).resolve()), args.timeout) for doc in docs]
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(reports, indent=2) if args.json else "\n\n".join(map(render, reports)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
