from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mumei-repo", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    target = Path(args.mumei_repo).resolve() / "scripts/generate_stdlib_metrics.py"
    payload = {
        "success": False,
        "mode": "fixture",
        "tool": "audit",
        "openai_api_key_used": False,
        "checkout_ref": "develop",
        "source_file": str(target),
        "language": "python",
        "spec_extracted": True,
        "spec_health_issues": [],
        "verification_violations": [
            {
                "file": "scripts/generate_stdlib_metrics.py",
                "function": "_scan_std",
                "message": "std directory traversal requires an explicit target inventory before report artifacts are trusted",
            }
        ],
        "counterexample_values": [
            {
                "std_dir": "std/",
                "missing_target_inventory": True,
                "artifact": "docs/STDLIB_METRICS.md",
            }
        ],
        "cross_validation_gaps": [
            {
                "file": "scripts/generate_stdlib_metrics.py",
                "gap": "The implementation can scan all std/*.mm files, while the scenario contract requires named develop-checkout targets and explicit generated artifact evidence.",
            }
        ],
        "migration_hints": [
            {
                "function": "_scan_std",
                "target": "mm/scan_std.mm",
                "command": "python -m agent migrate-suggest --code-file <mumei>/scripts/generate_stdlib_metrics.py --language python --issues-json <audit issues> --output <report>/mm",
            }
        ],
        "next_steps": [
            {
                "priority": "high",
                "action": "Run migrate-suggest after audit evidence is captured.",
            },
            {
                "priority": "medium",
                "action": "Use live audit only when OPENAI_API_KEY has been provided for this run.",
            },
        ],
        "generated_artifacts": [
            "target_files.json",
            "audit/mumei_develop_audit.json",
            "mm/scan_std.mm",
            "mm/render_markdown.mm",
        ],
        "fixture_live_branch": {
            "fixture": "CI_FIXTURE_MODE=1; no OPENAI_API_KEY is read.",
            "live": "CI_FIXTURE_MODE=0; OPENAI_API_KEY is required before running mumei-agent audit.",
        },
        "errors": [],
    }

    audit_dir = output_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "mumei_develop_audit.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
