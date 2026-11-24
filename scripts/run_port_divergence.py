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


STRING = r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`[^`]*`"""
INDEX = r"(?:\b\w+|\]|\))\s*\["
DIVIDE = r"(?<=[\w\])])\s*(?:/|%)"
NARROW = r"\bas\s+[iu](?:8|16|32)\b|\bu?int(" + "|".join(map(str, range(8, 256, 8))) + r")\s*\("


def scrub(text: str, language: str = "mumei") -> str:
    if language == "python":
        pattern = r"""(?s:"{3}.*?"{3}|'{3}.*?'{3})|\#[^\n]*|""" + STRING
    else:
        pattern = STRING + r"|//[^\n]*|(?s:/\*.*?\*/)"
    return re.sub(pattern, " ", text)


def usable_body(body: object) -> bool:
    if not isinstance(body, str) or not body.strip():
        return False
    tokens = scrub(body)
    if re.search(r"\b(?:atom|import|trusted)\b", tokens):
        return False
    depth = 0
    for char in tokens:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def lint(case: dict, body: str) -> list[str]:
    source = scrub(case["functions"]["buggy"] or "", case["language"])
    _, _, reference_body = bench.split_port(case["ports"]["buggy"], case["atom"])
    reference = scrub(reference_body)
    port = scrub(body)
    # Only compare source operations represented by the hand-written model.
    rules = (
        ("index/slice", INDEX, INDEX + r"|\bslice_to\s*\("),
        ("division/modulo", DIVIDE, DIVIDE),
        ("dereference", r"(?:[\w\])])\s*\.|" + INDEX if case["category"] == "null-dereference"
         else r"\*\s*\w+", r"\bderef\s*\("),
        ("narrow cast", NARROW, NARROW),
    )
    warnings = [f"missing modeled {name}" for name, native, modeled in rules
                if re.search(native, source) and re.search(modeled, reference) and not re.search(modeled, port)]
    if len(re.findall(r"\bif\b", port)) > len(re.findall(r"\bif\b", reference)):
        warnings.append("possible added guard")
    ensures = bench.header_ensures(case["header"]) or ""
    if (re.match(r"^\(*\s*result\.ok\s*=>", ensures) and re.search(r"\bok\s*:\s*true\b", reference)
            and re.search(r"\bok\s*:\s*(?!true\b)[\w!(]", port)):
        warnings.append("success flag can mask a postcondition clause")
    if re.search(rf"\b{re.escape(case['atom'])}\s*\(", port):
        warnings.append("target atom calls itself")
    return warnings


def replay_verdict(mumei_bin: str, case: dict, port: str, values: dict, timeout: int) -> dict:
    try:
        return replay.port_verdict(mumei_bin, port, case["atom"], values, timeout)
    except ValueError as error:
        return {"verdict": "inconclusive", "status": "bad input", "diagnostics": [str(error)]}


def outcome(inputs: list[dict]) -> str:
    if any(i["reference"]["verdict"] == "breaks" and i["llm"]["verdict"] == "holds" for i in inputs):
        return "diverged"
    if not inputs or any(i["reference"]["verdict"] != "breaks" or i["llm"]["verdict"] != "breaks"
                         for i in inputs):
        return "inconclusive"
    return "still_refutes"


def collect(cases: list[dict], doc: dict, mumei_bin: str, timeout: int) -> dict:
    by_id = {c["id"]: c for c in cases}
    reference = {}
    rows = []
    for run, records in enumerate(doc["runs"], 1):
        for record in records:
            buggy = record["buggy"]
            if buggy["outcome"] != "proven":
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
                llm = None
                if witness["reference"]["verdict"] == "breaks":
                    if port is not None:
                        llm = replay_verdict(mumei_bin, case, port, witness["values"], timeout)
                    else:
                        llm = {"verdict": "inconclusive", "status": "missing or invalid body", "diagnostics": []}
                inputs.append({**witness, "llm": llm})
            rows.append({"case": case_id, "run": run, "outcome": outcome(inputs),
                         "lint": lint(case, body) if port is not None else [], "inputs": inputs})
    return {"model": doc["model"], "runs": len(doc["runs"]), "cases": len(reference),
            "outcomes": dict(sorted(Counter(row["outcome"] for row in rows).items())), "misaccepts": rows}


def render(report: dict) -> str:
    rows = sorted(report["misaccepts"], key=lambda r: (r["case"], r["run"]))
    lines = [f"{report['model']}: {len(rows)} buggy accepts across {report['cases']} cases "
             f"({report['runs']} runs)"]
    lines += [f"{name}: {total}" for name, total in report["outcomes"].items()]
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
