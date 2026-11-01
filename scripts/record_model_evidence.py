"""Collect independent Lean model evidence; never promote a Python operation."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from scenario_evidence import EvidenceError, _json

INPUTS = (
    "MumeiLean/AuthorizationModel.lean", "MumeiLean/AuthorizationExamples.lean",
    "lean-toolchain", "lakefile.lean", "lake-manifest.json",
    "scripts/check_authorization_model.py", "scripts/axiom_audit.py", "scripts/bridge.py",
)
ALLOWLIST = {"propext", "Classical.choice", "Quot.sound"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(repo: Path, output: Path) -> bool:
    output.mkdir(parents=True, exist_ok=True)
    path = output / "model.json"
    report = {"schema": "mumei-demo.independent-model/v1", "status": "error",
              "inputs": {}, "theorems": {}, "axiom_allowlist": sorted(ALLOWLIST)}
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    try:
        before = {name: digest(repo / name) for name in INPUTS}
        for name in INPUTS:
            destination = output / "source" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / name, destination)
            if digest(destination) != before[name]:
                raise ValueError("source changed while copying")
        report["inputs"] = {f"source/{name}": value for name, value in before.items()}
        audit_path = output / "audit" / "axiom_audit.json"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text("{}\n", encoding="utf-8")
        process = subprocess.run(
            [sys.executable, str(repo / "scripts/check_authorization_model.py"),
             "--out-dir", str(output / "audit")],
            cwd=repo, capture_output=True, text=True, timeout=900, check=False,
        )
        (output / "collector.log").write_text(process.stdout + process.stderr, encoding="utf-8")
        audit = _json(audit_path)
        expected = set()
        for name in INPUTS[:2]:
            module = name.removesuffix(".lean").replace("/", ".")
            source = (output / "source" / name).read_text(encoding="utf-8")
            expected.update(f"{module}.{theorem}" for theorem in re.findall(r"^theorem (\w+)", source, re.M))
        if process.returncode or not expected or set(audit) != expected:
            raise ValueError("build or complete theorem audit failed")
        for result in audit.values():
            if (not isinstance(result, dict) or result.get("status") != "passed"
                    or result.get("disallowed") != [] or not isinstance(result.get("axioms"), list)
                    or not all(type(a) is str and a in ALLOWLIST for a in result["axioms"])):
                raise ValueError("rejected theorem audit")
        if before != {name: digest(repo / name) for name in INPUTS}:
            raise ValueError("model inputs changed during audit")
        report.update(status="passed", theorems=audit)
    except (OSError, ValueError, EvidenceError, subprocess.TimeoutExpired):
        report["status"] = "error"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report["status"] == "passed"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    passed = collect(args.repo.resolve(), args.output.resolve())
    print(f"Independent model evidence: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
