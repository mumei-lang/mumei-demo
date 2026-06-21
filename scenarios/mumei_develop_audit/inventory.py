from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


TARGET_FILES = [
    {
        "path": "scripts/generate_stdlib_metrics.py",
        "language": "python",
        "method": "audit",
        "live_command": "python -m agent audit --code-file <mumei>/scripts/generate_stdlib_metrics.py --language python --json --auto-migrate",
        "fixture_command": "scenarios/mumei_develop_audit/fixture_audit.py",
        "reason": "Audits the mumei develop checkout's stdlib metrics generator and preserves explicit verification/cross-validation evidence before accepting generated guidance.",
    }
]


def git_value(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=False,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mumei-repo", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    repo = Path(args.mumei_repo).resolve()
    output_dir = Path(args.output_dir).resolve()
    targets = []
    missing = []
    for target in TARGET_FILES:
        absolute_path = repo / target["path"]
        entry = {
            **target,
            "absolute_path": str(absolute_path),
            "exists": absolute_path.exists(),
        }
        targets.append(entry)
        if not absolute_path.exists():
            missing.append(target["path"])

    payload = {
        "checkout": {
            "repo": str(repo),
            "expected_ref": "develop",
            "actual_ref": git_value(repo, "rev-parse", "--abbrev-ref", "HEAD"),
            "commit": git_value(repo, "rev-parse", "HEAD"),
        },
        "target_files": targets,
        "fixture_mode": "CI_FIXTURE_MODE=1 emits deterministic audit evidence and does not read OPENAI_API_KEY.",
        "live_mode": "CI_FIXTURE_MODE=0 runs mumei-agent audit against the develop checkout target and requires OPENAI_API_KEY.",
        "generated_artifacts": [
            "target_files.json",
            "audit/mumei_develop_audit.json",
            "mm/*.mm",
            "harness_state.json",
            "result.json",
            "report.md",
        ],
        "missing_files": missing,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "target_files.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    raise SystemExit(1 if missing else 0)


if __name__ == "__main__":
    main()
