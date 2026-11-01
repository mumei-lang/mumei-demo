"""Exercise an evidence reader on isolated, explicitly synthetic snapshots."""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import tempfile
from pathlib import Path

from scenario_evidence import GRADES, capture_identities, load_result


CASES = (
    "unchanged", "missing_source", "missing_certificate", "missing_claim_book",
    "replaced_certificate", "stale_claim", "direct_dependency", "transitive_dependency",
    "missing_required_artifact", "missing_step", "existing_failure",
)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def relocate(value: object, old: Path, new: Path) -> object:
    if isinstance(value, dict):
        return {k: relocate(v, old, new) for k, v in value.items()}
    if isinstance(value, list):
        return [relocate(v, old, new) for v in value]
    if isinstance(value, str) and value.startswith(str(old) + "/"):
        return str(new) + value[len(str(old)):]
    return value


def mutate(case: str, data: dict, root: Path) -> None:
    requirement = data["evidence_requirements"]["claims"][0]
    entry = next(e for e in data["claim_book"]["entries"] if e["step"] == requirement["step"])
    book_path = root / entry["file"]
    if case in {"missing_source", "missing_certificate", "missing_claim_book"}:
        name = {"missing_source": requirement["source"], "missing_certificate": entry["cert"], "missing_claim_book": entry["file"]}[case]
        (root / name).unlink()
    elif case == "replaced_certificate":
        write_json(root / entry["cert"], {"version": "1.1", "atoms": []})
        # A replacement must differ even if a tiny input fixture already has no atoms.
        with (root / entry["cert"]).open("a", encoding="utf-8") as stream:
            stream.write("\n")
    elif case in {"stale_claim", "direct_dependency", "transitive_dependency"}:
        book = json.loads(book_path.read_text(encoding="utf-8"))
        claim = next(c for c in book["claims"] if c["atom"] == requirement["atom"])
        if case == "stale_claim":
            claim["freshness"] = "drifted"
        else:
            missing = "__regression_missing_dependency__"
            while any(c["atom"] == missing for c in book["claims"]):
                missing += "_"
            claim["effective_grade_complete"] = False
            if case == "direct_dependency":
                claim["dependencies"].append(missing)
                claim["unresolved_dependencies"].append(missing)
            else:
                helper = copy.deepcopy(claim)
                helper.update(atom=missing + "helper", dependencies=[missing], unresolved_dependencies=[missing])
                claim["dependencies"].append(helper["atom"])
                book["claims"].append(helper)
        book["summary"] = {
            "total": len(book["claims"]),
            "by_effective_grade": {g: sum(c["effective_grade"] == g for c in book["claims"]) for g in GRADES},
            "by_freshness": {s: sum(c["freshness"] == s for c in book["claims"]) for s in ("fresh", "drifted", "uncertified")},
        }
        write_json(book_path, book)
        data["evidence_identities"] = capture_identities(data, root)
    elif case == "missing_required_artifact":
        data["evidence_requirements"]["artifacts"] = [*data["evidence_requirements"].get("artifacts", []), "__regression_required_artifact.json"]
    elif case == "missing_step":
        for layer in data["layers"].values():
            layer["steps"] = [s for s in layer["steps"] if s["id"] != requirement["step"]]
    elif case == "existing_failure":
        data["overall_status"] = "FAIL"
    elif case != "unchanged":
        raise ValueError(f"unknown regression case: {case}")


def run_suite(result_path: Path, out_dir: Path) -> dict:
    root = result_path.resolve().parent
    out_dir = out_dir.resolve()
    if out_dir.is_relative_to(root) or root.is_relative_to(out_dir):
        raise ValueError("regression output must be separate from the input report tree")
    out_dir.mkdir(parents=True, exist_ok=True)
    if any(out_dir.iterdir()):
        raise ValueError("regression output directory must be empty")
    summary = {"schema": "mumei-demo.evidence-regressions/v1", "kind": "synthetic_artifact_mutations", "status": "FAIL", "cases": []}
    try:
        original = load_result(result_path)
        if original.get("overall_status") != "PASS" or original.get("evidence_summary", {}).get("status") != "satisfied":
            raise ValueError("a freshly validated, satisfied evidence report is required")
        for case in CASES:
            target = out_dir / case
            shutil.copytree(root, target)
            data = relocate(original, root, target)
            for entry in data["claim_book"]["entries"]:
                book = target / entry["file"]
                write_json(book, relocate(json.loads(book.read_text(encoding="utf-8")), root, target))
            data["evidence_identities"] = capture_identities(data, target)
            path = target / "result.json"
            write_json(path, data)
            if load_result(path)["evidence_summary"]["status"] != "satisfied":
                raise ValueError("relocated baseline did not validate")
            mutate(case, data, target)
            write_json(path, data)
            actual = load_result(path)
            expected = "PASS" if case == "unchanged" else "FAIL"
            expected_evidence = "satisfied" if case in {"unchanged", "existing_failure"} else "incomplete"
            matched = actual["overall_status"] == expected and actual["evidence_summary"]["status"] == expected_evidence
            if case in {"direct_dependency", "transitive_dependency"}:
                key = "direct_unresolved_dependencies" if case == "direct_dependency" else "transitive_unresolved_dependencies"
                matched = matched and bool(actual["evidence_summary"]["claims"][0]["dependency_coverage"][key])
            row = {"case": case, "expected_status": expected, "actual_status": actual["overall_status"], "evidence_status": actual["evidence_summary"]["status"], "matched": matched, "issues": actual["evidence_summary"]["issues"]}
            summary["cases"].append(row)
            write_json(target / "reader_result.json", actual)
        summary["status"] = "PASS" if all(row["matched"] for row in summary["cases"]) else "FAIL"
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        summary["error"] = str(error)
    write_json(out_dir / "summary.json", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="run-", dir=args.out_dir))
    try:
        summary = run_suite(args.result, output)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    print(f"Synthetic artifact regressions: {summary['status']} ({len(summary['cases'])} cases); {output / 'summary.json'}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
