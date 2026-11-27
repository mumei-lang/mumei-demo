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


def success_flag_paths(body: str) -> set[tuple]:
    """Collect explicit ok expressions with the enclosing if/else predicates."""
    tokens = re.findall(r"\w+|[^\s]", body)
    braces = {}
    stack = []
    for i, token in enumerate(tokens):
        if token == "{":
            stack.append(i)
        elif token == "}" and stack:
            braces[stack.pop()] = i

    flags = set()

    def branch(i: int, end: int, path: tuple) -> int:
        if i >= end:
            return i
        if tokens[i] == "if":
            start = next((j for j in range(i + 1, end) if tokens[j] in ("{", ";")), end)
            if start not in braces:
                return i + 1
            predicate = tuple(tokens[i + 1:start])
            close = braces[start]
            scan(start + 1, close, (*path, (predicate, True)))
            after = close + 1
            if after < end and tokens[after] == "else":
                return branch(after + 1, end, (*path, (predicate, False)))
            return after
        if i in braces:
            scan(i + 1, braces[i], path)
            return braces[i] + 1
        return i + 1

    def scan(i: int, end: int, path: tuple) -> None:
        while i < end:
            if tokens[i:i + 2] == ["ok", ":"]:
                start = i + 2
                i = start
                depth = 0
                while i < end:
                    token = tokens[i]
                    if token == "," and depth == 0:
                        break
                    depth += (token in ("(", "[", "{")) - (token in (")", "]", "}"))
                    i += 1
                flags.add((path, tuple(tokens[start:i])))
            else:
                i = branch(i, end, path)

    scan(0, len(tokens), ())
    return flags


def body_inner(text: str) -> str:
    """Inner statements of a complete port body, or ``text`` when already inner."""
    start = text.find("body:")
    if start < 0:
        return text
    opening = text.find("{", start)
    closing = text.rfind("}")
    if opening < 0 or closing <= opening:
        return text
    return text[opening + 1:closing]


def token_pattern(text: str) -> tuple[str, ...]:
    """Whitespace/comment-insensitive token shape used for conservative comparisons."""
    return tuple(re.findall(r"\w+|[^\s]", scrub(text)))


def _reference_inner(case: dict, variant: str) -> str | None:
    text = case.get("ports", {}).get(variant)
    if not isinstance(text, str):
        return None
    parts = bench.split_port(text, case["atom"])
    return body_inner(parts[2]) if parts else None


def _silent_repair(case: dict, body: str) -> bool:
    """The candidate exactly follows the fixed reference body instead of the buggy one.

    This is deliberately exact after comment/string scrubbing and tokenization.  A
    looser similarity score would make ordinary correct translations noisy; the
    adversarial corpus pins the high-confidence case and future detectors can widen
    it behind the same finding kind.
    """
    buggy = _reference_inner(case, "buggy")
    fixed = _reference_inner(case, "fixed")
    if buggy is None or fixed is None:
        return False
    buggy_tokens = token_pattern(buggy)
    fixed_tokens = token_pattern(fixed)
    return fixed_tokens != buggy_tokens and token_pattern(body) == fixed_tokens


def _trivial_clause(text: str) -> bool:
    compact = re.sub(r"[\s()]+", "", text).removesuffix(";")
    return compact in {"", "true", "result==result"}


def _top_level_conjuncts(text: str) -> list[str]:
    parts, start, depth = [], 0, 0
    i = 0
    while i < len(text):
        char = text[i]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == "&" and i + 1 < len(text) and text[i + 1] == "&" and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 2
            i += 1
        i += 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def _numeric_bound_contradiction(requires: str) -> bool:
    bounds: dict[str, dict[str, float]] = {}
    integer = r"(?:\d+|\(0\s*-\s*\d+\))"
    for match in re.finditer(rf"\b([A-Za-z_]\w*)\s*(>=|>|<=|<)\s*({integer})", requires):
        name, op, raw = match.groups()
        negative = re.match(r"\(0\s*-\s*(\d+)\)", raw)
        value = -float(negative.group(1)) if negative else float(raw)
        entry = bounds.setdefault(name, {"lower": float("-inf"), "upper": float("inf"),
                                         "lower_strict": False, "upper_strict": False})
        if op in (">", ">="):
            if value > entry["lower"] or (value == entry["lower"] and op == ">"):
                entry["lower"] = value
                entry["lower_strict"] = op == ">"
        else:
            if value < entry["upper"] or (value == entry["upper"] and op == "<"):
                entry["upper"] = value
                entry["upper_strict"] = op == "<"
    return any(
        entry["lower"] > entry["upper"]
        or (entry["lower"] == entry["upper"] and (entry["lower_strict"] or entry["upper_strict"]))
        for entry in bounds.values()
    )


def _strip_wrapping_parens(text: str) -> str:
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        wraps = True
        for index, char in enumerate(text):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(text) - 1:
                    wraps = False
                    break
        if not wraps:
            break
        text = text[1:-1].strip()
    return text


def _compact_clause(text: str) -> str:
    return "".join(_strip_wrapping_parens(text).split())


def _has_direct_complement(parts: list[str]) -> bool:
    compact = {_compact_clause(part) for part in parts if _compact_clause(part)}
    for part in compact:
        positive = part[1:] if part.startswith("!") else part
        positive = _compact_clause(positive)
        complements = {f"!{positive}", f"!({positive})"}
        if positive in compact and compact.intersection(complements):
            return True
    return False


def lint_contract(requires: str, ensures: str) -> list[dict]:
    """Static adversarial contract warnings for generated `requires`/`ensures` clauses.

    The checker is intentionally conservative and syntactic: it catches empty-domain
    contracts and contracts whose postcondition carries no result constraint without
    trying to prove general satisfiability.  Mumei/Z3 remains the semantic checker.
    """
    findings = []
    requires_parts = _top_level_conjuncts(scrub(requires, "mumei"))
    if (any(re.sub(r"[\s()]+", "", part) == "false" for part in requires_parts)
            or _has_direct_complement(requires_parts) or _numeric_bound_contradiction(requires)):
        findings.append({"kind": "vacuous_spec",
                         "message": "requires clause is trivially unsatisfiable"})
    ensures_parts = _top_level_conjuncts(scrub(ensures, "mumei"))
    if not ensures_parts or all(_trivial_clause(part) or "result" not in part for part in ensures_parts):
        findings.append({"kind": "weak_spec",
                         "message": "ensures clause carries no result constraint"})
    return findings


def lint_findings(case: dict, body: str) -> list[dict]:
    """Structured fidelity warnings for an accepted LLM port.

    `lint()` keeps the human-readable strings for compatibility; these records
    make the mechanism machine-countable instead of requiring prose parsing.
    """
    source = scrub(case["functions"]["buggy"] or "", case["language"])
    _, _, reference_body = bench.split_port(case["ports"]["buggy"], case["atom"])
    reference = scrub(body_inner(reference_body))
    port = scrub(body)
    findings = []
    silent_repair = _silent_repair(case, body)
    if silent_repair:
        findings.append({"kind": "silent_repair",
                         "message": "candidate body matches the fixed reference instead of the buggy source"})
    # Only compare source operations represented by the hand-written model.
    rules = (
        ("index/slice", INDEX, INDEX + r"|\bslice_to\s*\("),
        ("division/modulo", DIVIDE, DIVIDE),
        ("dereference", r"(?:[\w\])])\s*\.|" + INDEX if case["category"] == "null-dereference"
         else r"\*\s*\w+", r"\bderef\s*\("),
        ("narrow cast", NARROW, NARROW),
    )
    findings.extend(
        {"kind": "missing_modeled_operation", "operation": name,
         "message": f"missing modeled {name}"}
        for name, native, modeled in rules
        if re.search(native, source) and re.search(modeled, reference) and not re.search(modeled, port)
    )
    if not silent_repair and len(re.findall(r"\bif\b", port)) > len(re.findall(r"\bif\b", reference)):
        findings.append({"kind": "added_guard", "message": "possible added guard"})
    ensures = bench.header_ensures(case["header"]) or ""
    if re.match(r"^\(*\s*result\.ok\s*=>", ensures):
        reference_flags = success_flag_paths(reference)
        port_flags = success_flag_paths(port)
        new_flags = port_flags - reference_flags
        reference_exprs = {expr for _, expr in reference_flags}
        port_exprs = {expr for _, expr in port_flags}
        if (any(expr != ("true",) for expr in reference_exprs) and port_flags
                and port_exprs == {("true",)}):
            findings.append({"kind": "guard_folding",
                             "message": "failure branch is folded into unconditional success"})
        if reference_flags and any(expr != ("true",) for _, expr in new_flags):
            findings.append({"kind": "success_flag_rewrite",
                             "message": "success flag can mask a postcondition clause"})
    if re.search(rf"\b{re.escape(case['atom'])}\s*\(", port):
        findings.append({"kind": "self_call", "message": "target atom calls itself"})
    return findings


def lint(case: dict, body: str) -> list[str]:
    return [finding["message"] for finding in lint_findings(case, body)]


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
                if port is not None:
                    llm = replay_verdict(mumei_bin, case, port, witness["values"], timeout)
                else:
                    llm = {"verdict": "inconclusive", "status": "missing or invalid body", "diagnostics": [],
                           "verification_attempted": False}
                inputs.append({**witness, "llm": llm})
            linted = lint_findings(case, body) if port is not None else []
            rows.append({"case": case_id, "run": run, "outcome": outcome(inputs),
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
    lines = [f"{report['model']}: {len(rows)} buggy accepts across {report['cases']} cases "
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
