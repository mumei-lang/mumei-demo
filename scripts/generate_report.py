#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Mumei demo result.")
    parser.add_argument("result_json", help="Path to result.json")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    args = parser.parse_args()

    result_path = Path(args.result_json)
    if args.format == "json":
        data = json.loads(result_path.read_text(encoding="utf-8"))
        print(json.dumps({
            "scenario": data.get("scenario"),
            "overall_status": data.get("overall_status"),
            "proof_density": data.get("proof_density"),
            "artifacts": data.get("artifacts", []),
        }, indent=2, ensure_ascii=False))
        return 0

    root = Path(__file__).resolve().parent.parent
    return subprocess.run(
        [sys.executable, str(root / "dashboard" / "cli_report.py"), str(result_path)],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
