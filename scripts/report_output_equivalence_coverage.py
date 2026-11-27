#!/usr/bin/env python3
"""Report output-equivalence oracle coverage in the recorded benchmark artifact."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import port_fidelity as fidelity

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = REPO_ROOT / "proofs/results/mumei-llm-openai__gpt-6-luna.json"
REPORT_PATH = REPO_ROOT / "proofs/OUTPUT_EQUIVALENCE_COVERAGE.md"
BUCKETS = (
    "matched", "diverged", "boundary_only", "bounded_finite_agreement",
    "other_inconclusive", "helper_valid_domain_agreement", "unavailable_loop", "unavailable_other",
    "timeout", "operational", "not_applicable_not_proven",
)


def bucket(gate: dict | None, raw: dict) -> str:
    if not gate:
        return "unavailable_other" if raw.get("outcome") == "proven" else "not_applicable_not_proven"
    evidence = gate.get("output_equivalence", {}) or {}
    outcome = evidence.get("outcome")
    reason = evidence.get("reason")
    status = evidence.get("status")
    failure_kind = evidence.get("failure_kind")
    if status == "timeout" or failure_kind == "budget_exhausted":
        return "timeout"
    if status == "error" or failure_kind in {"environment_failure", "unsupported"}:
        return "operational"
    if outcome == "matched":
        return "matched"
    if outcome == "diverged":
        return "diverged"
    if outcome == "inconclusive" and reason == "abstraction_boundary_only":
        return "boundary_only"
    if outcome == "inconclusive" and reason == "bounded_interactions_matched":
        return "bounded_finite_agreement"
    if outcome == "inconclusive" and reason == "helper_body_valid_domain_matched":
        return "helper_valid_domain_agreement"
    if outcome == "inconclusive":
        return "other_inconclusive"
    if outcome == "unavailable" and reason == "loop_equivalence_unverified":
        return "unavailable_loop"
    if outcome == "unavailable":
        return "unavailable_other"
    return "operational"


def helper_definitions() -> dict[str, list[dict]]:
    """Static helper-atom inventory for benchmark cases, without native source extraction."""
    inventory = {}
    pattern = re.compile(r"\batom\s+(\w+)\s*\((.*?)\)\s*->\s*(\w+)\s+(.*?)(?=\n\s*atom\s+|\Z)", re.S)
    for cpath in sorted((REPO_ROOT / "proofs").glob("*/*/*/contract.json")):
        case_id = cpath.parent.name
        fixed_path = cpath.parent / "fixed.mm"
        if not fixed_path.is_file():
            continue
        meta = json.loads(cpath.read_text(encoding="utf-8"))
        parts = fidelity.split_port(fixed_path.read_text(encoding="utf-8"), meta["atom"])
        if parts is None:
            continue
        prelude = parts[0]
        inlineable = set(fidelity.simple_helper_atoms(prelude))
        entries = []
        for match in pattern.finditer(prelude):
            name, _params, _return_type, block = match.groups()
            body_match = re.search(r"\bbody\s*:\s*\{(.*)\}\s*$", block.strip(), re.S)
            body = body_match.group(1) if body_match else ""
            effectful = bool(re.search(r"\b(?:extern|effect|trusted)\b", block))
            self_recursive = bool(body and re.search(rf"\b{re.escape(name)}\s*\(", body))
            body_available = bool(body.strip())
            if effectful:
                shape = "effectful_or_trusted"
            elif not body_available:
                shape = "opaque_body_unavailable"
            elif self_recursive:
                shape = "self_recursive"
            elif name in inlineable:
                shape = "pure_nonrecursive_inlineable"
            else:
                shape = "pure_nonrecursive_not_inlineable"
            entries.append({"case": case_id, "helper": name, "shape": shape,
                            "body_available": body_available,
                            "inline_eligible": name in inlineable})
        if entries:
            inventory[case_id] = entries
    return inventory


def helper_summary(evidence: dict, key: str) -> str:
    reason = evidence.get("reason")
    if key in {"matched", "diverged"}:
        return key
    if reason == "helper_body_valid_domain_matched":
        return "valid_domain_agreement"
    if reason == "abstraction_boundary_only":
        return "boundary_only"
    if key in {"timeout", "operational"}:
        return key
    if key.startswith("unavailable"):
        return "unavailable"
    return "other_inconclusive"


def coverage(doc: dict) -> dict:
    rows = []
    for variant in ("fixed", "buggy"):
        for run_index, run in enumerate(doc["runs"], 1):
            counts = Counter()
            examples = defaultdict(list)
            opaque = []
            helper_counts = Counter()
            helper_examples = defaultdict(list)
            methods = Counter()
            for record in run:
                raw = record[variant]
                gate = raw.get("fidelity_gate")
                evidence = (gate or {}).get("output_equivalence", {}) or {}
                key = bucket(gate, raw)
                counts[key] += 1
                examples[key].append(record["id"])
                if evidence.get("opaque_atom_calls"):
                    opaque.append(record["id"])
                    helper_key = helper_summary(evidence, key)
                    helper_counts[helper_key] += 1
                    helper_examples[helper_key].append(record["id"])
                if evidence.get("method"):
                    methods[evidence["method"]] += 1
            rows.append({
                "variant": variant, "run": run_index, "rows": len(run),
                "counts": counts, "examples": examples, "opaque": opaque,
                "helper_counts": helper_counts, "helper_examples": helper_examples,
                "methods": methods,
            })
    return {"schema": "mumei-demo.output-equivalence-coverage/v1", "rows": rows,
            "helper_inventory": helper_definitions()}


def cell(counts: Counter, key: str) -> str:
    return str(counts.get(key, 0))


def render(result: dict) -> str:
    lines = [
        "# Output-equivalence oracle coverage",
        "",
        "<!-- Generated by scripts/report_output_equivalence_coverage.py; do not edit by hand. -->",
        "",
        "Coverage is counted over every recorded benchmark row. `not_applicable_not_proven` means the raw candidate was not verification-accepted, so the output-equivalence oracle was not needed for acceptance. `timeout` and `operational` are tool/evidence failures rather than semantic classifications. `bounded_finite_agreement` is concrete input/state interaction evidence only: it is not universal output equality. `helper_valid_domain_agreement` is likewise diagnostic agreement on the path-sensitive valid helper-call domain, not universal equality.",
        "",
        "| Variant | Run | Rows | Matched | Diverged | Boundary-only | Bounded finite agreement | Helper valid-domain agreement | Other inconclusive | Loop unavailable | Other unavailable | Timeout | Operational | Not applicable |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["rows"]:
        counts = row["counts"]
        lines.append(
            f"| {row['variant']} | {row['run']} | {row['rows']} | {cell(counts, 'matched')} | "
            f"{cell(counts, 'diverged')} | {cell(counts, 'boundary_only')} | "
            f"{cell(counts, 'bounded_finite_agreement')} | "
            f"{cell(counts, 'helper_valid_domain_agreement')} | {cell(counts, 'other_inconclusive')} | "
            f"{cell(counts, 'unavailable_loop')} | {cell(counts, 'unavailable_other')} | "
            f"{cell(counts, 'timeout')} | {cell(counts, 'operational')} | "
            f"{cell(counts, 'not_applicable_not_proven')} |"
        )
    lines.extend(["", "## Representative cases", ""])
    for row in result["rows"]:
        lines.append(f"### {row['variant']} run {row['run']}")
        for key in BUCKETS:
            ids = row["examples"].get(key, [])
            if ids:
                lines.append(f"- `{key}`: " + ", ".join(f"`{case_id}`" for case_id in ids))
        if row["opaque"]:
            lines.append("- opaque helper atoms present in comparison: "
                         + ", ".join(f"`{case_id}`" for case_id in row["opaque"]))
        if row["methods"]:
            methods = ", ".join(f"`{name}` × {count}" for name, count in sorted(row["methods"].items()))
            lines.append(f"- evidence methods: {methods}")
        lines.append("")
    inventory = result.get("helper_inventory", {})
    pairs = [(case_id, entry) for case_id, entries in sorted(inventory.items()) for entry in entries]
    lines.extend(["", "## Helper atom coverage", ""])
    if pairs:
        shapes = Counter(entry["shape"] for _, entry in pairs)
        shape_text = ", ".join(f"`{shape}` × {count}" for shape, count in sorted(shapes.items()))
        lines.append(f"Static inventory: {len(pairs)} case/helper pair(s) across {len(inventory)} case(s): {shape_text}.")
        lines.extend(["", "| Case | Helper | Shape | Body available | Inline eligible |", "|---|---|---|---|---|"])
        for case_id, entry in pairs:
            lines.append(f"| `{case_id}` | `{entry['helper']}` | `{entry['shape']}` | "
                         f"{'yes' if entry['body_available'] else 'no'} | {'yes' if entry['inline_eligible'] else 'no'} |")
        lines.extend(["", "Recorded rows using helper calls:"])
        for row in result["rows"]:
            if not row["helper_counts"]:
                continue
            counts_text = ", ".join(f"{name} {count}" for name, count in sorted(row["helper_counts"].items()))
            lines.append(f"- {row['variant']} run {row['run']}: {sum(row['helper_counts'].values())} row(s): {counts_text}.")
            for name, ids in sorted(row["helper_examples"].items()):
                lines.append(f"  - `{name}`: " + ", ".join(f"`{case_id}`" for case_id in ids))
    else:
        lines.append("No helper atom calls were present in recorded comparisons.")
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--check", action="store_true", help="fail when the committed report is out of date")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        doc = json.loads(args.results.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot load {args.results}: {exc}", file=sys.stderr)
        return 1
    text = render(coverage(doc))
    if args.check:
        if not args.report.is_file() or args.report.read_text(encoding="utf-8") != text:
            print(f"error: {args.report} is out of date; run scripts/report_output_equivalence_coverage.py", file=sys.stderr)
            return 1
        print("output-equivalence coverage report is up to date")
        return 0
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(text, encoding="utf-8")
    print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
