#!/usr/bin/env python3
"""Check the pinned adversarial intent-fidelity corpus offline.

The corpus in proofs/adversarial/ is deliberately static: it does not call an
LLM or Mumei.  It pins hostile generated-contract and body-port shapes to the
structured warnings produced by run_port_divergence.py, so detector regressions
are visible in CI before another false-acceptance measurement is interpreted.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_port_divergence as port_divergence  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = REPO_ROOT / "proofs" / "adversarial" / "intent-fidelity-corpus.json"
REPORT_PATH = REPO_ROOT / "proofs" / "ADVERSARIAL.md"
SCHEMA = "mumei-demo.intent-fidelity-adversarial/v1"
FAILURE_MODES = (
    "guard_folding",
    "silent_repair",
    "vacuous_spec",
    "weak_spec",
    "body_port_meaning_loss",
)
TOP_KEYS = {"schema", "purpose", "failure_modes", "cases"}
CASE_KEYS = {
    "id", "kind", "failure_mode", "language", "category", "atom", "header",
    "native_source", "reference_body", "fixed_reference_body", "candidate_body",
    "requires", "ensures", "expected_findings", "rationale",
}
PORT_REQUIRED = {
    "id", "kind", "failure_mode", "language", "category", "atom", "header",
    "native_source", "reference_body", "candidate_body", "expected_findings", "rationale",
}
CONTRACT_REQUIRED = {
    "id", "kind", "failure_mode", "requires", "ensures", "expected_findings", "rationale",
}


def finding_label(finding: dict) -> str:
    operation = finding.get("operation")
    return f"{finding['kind']}:{operation}" if operation else finding["kind"]


def _error(errors: list[str], case_id: str, message: str) -> None:
    errors.append(f"{case_id}: {message}")


def validate_case(case: object, index: int, errors: list[str]) -> None:
    if not isinstance(case, dict):
        _error(errors, f"cases[{index}]", "case must be an object")
        return
    case_id = str(case.get("id") or f"cases[{index}]")
    unknown = set(case) - CASE_KEYS
    if unknown:
        _error(errors, case_id, f"unexpected keys: {', '.join(sorted(unknown))}")
    kind = case.get("kind")
    required = PORT_REQUIRED if kind == "port" else CONTRACT_REQUIRED if kind == "contract" else set()
    if kind not in {"port", "contract"}:
        _error(errors, case_id, "kind must be 'port' or 'contract'")
    missing = sorted(key for key in required if key not in case)
    if missing:
        _error(errors, case_id, f"missing required keys: {', '.join(missing)}")
    if case.get("failure_mode") not in FAILURE_MODES:
        _error(errors, case_id, "unknown failure_mode")
    expected = case.get("expected_findings")
    if not isinstance(expected, list):
        _error(errors, case_id, "expected_findings must be a list")
    else:
        for finding_index, finding in enumerate(expected):
            if (not isinstance(finding, dict) or set(finding) - {"kind", "operation"}
                    or not isinstance(finding.get("kind"), str) or not finding["kind"]):
                _error(errors, case_id, f"expected_findings[{finding_index}] must contain a non-empty kind")
    string_keys = (PORT_REQUIRED | CONTRACT_REQUIRED | {"fixed_reference_body"}) - {"expected_findings"}
    for key in string_keys:
        if key in case and not isinstance(case[key], str):
            _error(errors, case_id, f"{key} must be a string")


def validate_corpus(doc: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["corpus root must be an object"]
    unknown = set(doc) - TOP_KEYS
    if unknown:
        errors.append(f"corpus: unexpected keys: {', '.join(sorted(unknown))}")
    if doc.get("schema") != SCHEMA:
        errors.append(f"corpus: schema must be {SCHEMA}")
    if sorted(doc.get("failure_modes") or []) != sorted(FAILURE_MODES):
        errors.append("corpus: failure_modes must exactly cover the pinned mode vocabulary")
    cases = doc.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("corpus: cases must be a non-empty list")
        return errors
    seen: set[str] = set()
    for index, case in enumerate(cases):
        validate_case(case, index, errors)
        if isinstance(case, dict) and isinstance(case.get("id"), str):
            if case["id"] in seen:
                errors.append(f"{case['id']}: duplicate case id")
            seen.add(case["id"])
    covered = {case.get("failure_mode") for case in cases if isinstance(case, dict)}
    missing_modes = sorted(set(FAILURE_MODES) - covered)
    if missing_modes:
        errors.append(f"corpus: no case covers failure modes: {', '.join(missing_modes)}")
    return errors


def load_corpus(path: Path = CORPUS_PATH) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load {path}: {exc}") from exc
    errors = validate_corpus(doc)
    if errors:
        raise ValueError("invalid adversarial corpus:\n" + "\n".join(f"- {error}" for error in errors))
    return doc


def _port_case(case: dict) -> dict:
    shell = {
        "id": case["id"],
        "atom": case["atom"],
        "header": case["header"],
        "prelude": "",
        "language": case["language"],
        "category": case["category"],
        "functions": {"buggy": case["native_source"]},
    }
    shell["ports"] = {
        "buggy": port_divergence.bench.assemble(shell, case["reference_body"]),
        "fixed": port_divergence.bench.assemble(shell, case.get("fixed_reference_body", case["reference_body"])),
    }
    return shell


def evaluate_case(case: dict) -> dict:
    if case["kind"] == "port":
        actual = port_divergence.lint_findings(_port_case(case), case["candidate_body"])
    else:
        actual = port_divergence.lint_contract(case["requires"], case["ensures"])
    expected_labels = sorted(finding_label(finding) for finding in case["expected_findings"])
    actual_labels = sorted(finding_label(finding) for finding in actual)
    return {
        "id": case["id"],
        "kind": case["kind"],
        "failure_mode": case["failure_mode"],
        "expected": expected_labels,
        "actual": actual_labels,
        "status": "pass" if actual_labels == expected_labels else "fail",
        "rationale": case["rationale"],
    }


def evaluate_corpus(doc: dict) -> dict:
    rows = [evaluate_case(case) for case in doc["cases"]]
    by_mode = {}
    for mode in FAILURE_MODES:
        mode_rows = [row for row in rows if row["failure_mode"] == mode]
        by_mode[mode] = {
            "cases": len(mode_rows),
            "passed": sum(row["status"] == "pass" for row in mode_rows),
        }
    return {
        "schema": "mumei-demo.intent-fidelity-adversarial-result/v1",
        "cases": rows,
        "summary": {
            "total": len(rows),
            "passed": sum(row["status"] == "pass" for row in rows),
            "failed": sum(row["status"] == "fail" for row in rows),
            "by_failure_mode": by_mode,
        },
    }


def _labels(labels: list[str]) -> str:
    return ", ".join(f"`{label}`" for label in labels) if labels else "—"


def render(result: dict) -> str:
    summary = result["summary"]
    lines = [
        "# Adversarial intent-fidelity corpus",
        "",
        "<!-- Generated by scripts/check_adversarial_port_corpus.py; do not edit by hand. -->",
        "",
        "Static adversarial fixtures for generated contracts and LLM body ports. The cases do not replace Mumei/Z3 verification: they pin whether the deterministic fidelity lint recognizes shapes that previously made false acceptance hard to explain.",
        "",
        f"Result: **{summary['passed']}/{summary['total']} cases pass**; {summary['failed']} failing.",
        "",
        "| Failure mode | Cases | Passing |",
        "|---|---:|---:|",
    ]
    for mode in FAILURE_MODES:
        row = summary["by_failure_mode"][mode]
        lines.append(f"| `{mode}` | {row['cases']} | {row['passed']} |")
    lines.extend([
        "",
        "| Case | Mode | Expected findings | Actual findings | Status |",
        "|---|---|---|---|---|",
    ])
    for row in result["cases"]:
        status = "PASS" if row["status"] == "pass" else "FAIL"
        lines.append(
            f"| `{row['id']}` | `{row['failure_mode']}` | {_labels(row['expected'])} | "
            f"{_labels(row['actual'])} | {status} |"
        )
    lines.extend([
        "",
        "The negative controls are part of the gate: a faithful port and a meaningful contract must produce no adversarial warning.",
        "",
    ])
    return "\n".join(lines)


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--check", action="store_true", help="fail when the committed report is out of date")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = evaluate_corpus(load_corpus(args.corpus))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    text = render(result)
    if args.check:
        if not args.report.is_file() or args.report.read_text(encoding="utf-8") != text:
            print(f"error: {display_path(args.report)} is out of date; run scripts/check_adversarial_port_corpus.py", file=sys.stderr)
            return 1
    else:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
        print(f"wrote {display_path(args.report)}")
    failed = result["summary"]["failed"]
    if failed:
        print(f"error: {failed} adversarial corpus cases do not produce the pinned findings", file=sys.stderr)
        return 1
    print(f"adversarial corpus: {result['summary']['passed']}/{result['summary']['total']} cases pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
