"""Publish the reviewed Charter inputs and their Git diff, not an approval verdict."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

PROJECT = "scenarios/charter_gate_demo/project/"
PATHS = (PROJECT + "specs/dosage.charter.mm", PROJECT + "charter.lock", PROJECT + "mumei.toml", "scenarios/charter_gate_demo/scenario.json")


def review(root: Path, base: str | None, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "schema": "mumei-demo.charter-baseline-review/v1",
        "review_required": True,
        "comparison": "not_requested",
        "files": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in PATHS},
        "evidence_requirements": json.loads((root / PATHS[-1]).read_text(encoding="utf-8"))["evidence_requirements"],
    }
    if base:
        commit = subprocess.run(["git", "rev-parse", "--verify", "--end-of-options", base + "^{commit}"], cwd=root, text=True, check=True, capture_output=True).stdout.strip()
        diff = subprocess.run(["git", "diff", "--no-ext-diff", "--no-textconv", commit, "--", *PATHS], cwd=root, text=True, check=True, capture_output=True).stdout
        snapshot.update(base_commit=commit, comparison="changed" if diff else "unchanged")
    else:
        diff = "No base commit was supplied. This is a current snapshot, not a change comparison.\n"
    (out_dir / "baseline.diff").write_text(diff, encoding="utf-8")
    (out_dir / "baseline.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "review.md").write_text(
        "## Charter baseline review\n\n"
        f"Comparison: **{snapshot['comparison']}**.\n\n"
        "Review the Charter source, committed lock, project configuration, and required evidence together. "
        "Candidate repair steps must not update these reviewed inputs. "
        "The artifact contains baseline.diff and baseline.json.\n\n"
        "Hashes identify local bytes; they are not approval, authenticity, or proof of deployment safety. "
        "A green job only means this review material was produced.\n",
        encoding="utf-8",
    )
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    review(Path(__file__).resolve().parents[1], args.base, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
