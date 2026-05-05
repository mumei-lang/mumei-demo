#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCENARIO_ORDER = [
    "ownership_transfer",
    "rtgs_settlement",
    "regtech_compliance",
    "nl_to_verified",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_result_path(reports_dir: Path, scenario: str) -> Path | None:
    latest = reports_dir / scenario / "latest" / "result.json"
    if latest.exists():
        return latest
    candidates = sorted((reports_dir / scenario).glob("*/result.json"), reverse=True)
    return candidates[0] if candidates else None


def density_values(data: dict) -> tuple[int, int, float]:
    density = data.get("proof_density", {})
    verified = int(density.get("verified", 0))
    total = int(density.get("total", 0))
    percentage = float(density.get("percentage", 0))
    return verified, total, percentage


def write_summary(
    reports_dir: Path,
    output_path: Path,
    scenarios: list[str],
    require_all: bool,
) -> int:
    rows: list[tuple[str, str, int, int, float]] = []
    missing: list[str] = []
    for scenario in scenarios:
        result_path = latest_result_path(reports_dir, scenario)
        if result_path is None:
            missing.append(scenario)
            continue
        data = load_json(result_path)
        verified, total, percentage = density_values(data)
        rows.append((
            scenario,
            str(data.get("overall_status", "UNKNOWN")),
            verified,
            total,
            percentage,
        ))

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "# Mumei Demo Summary",
        "",
        f"Generated: {generated_at}",
        "",
        "| Scenario | Overall status | Verified | Total | Proof density |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for scenario, status, verified, total, percentage in rows:
        lines.append(f"| `{scenario}` | {status} | {verified} | {total} | {percentage:g}% |")
    if missing:
        lines.extend(["", "## Missing results", ""])
        lines.extend(f"- `{scenario}`" for scenario in missing)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Summary written to {output_path}")
    if missing and require_all:
        print(f"Missing result.json for: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Mumei demo result.")
    parser.add_argument("result_json", nargs="?", help="Path to result.json")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Aggregate latest scenario result.json files into dashboard/summary.md",
    )
    parser.add_argument("--reports-dir", default="reports", help="Directory containing scenario reports")
    parser.add_argument("--output", default="dashboard/summary.md", help="Summary markdown output path")
    parser.add_argument(
        "--scenarios",
        nargs="*",
        default=SCENARIO_ORDER,
        help="Scenario names to include in summary",
    )
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="Return a non-zero exit code when any requested scenario result is missing",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    if args.summary:
        reports_dir = Path(args.reports_dir)
        if not reports_dir.is_absolute():
            reports_dir = root / reports_dir
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = root / output_path
        return write_summary(reports_dir, output_path, list(args.scenarios), args.require_all)

    if not args.result_json:
        parser.error("result_json is required unless --summary is used")

    result_path = Path(args.result_json)
    if args.format == "json":
        data = load_json(result_path)
        print(json.dumps({
            "scenario": data.get("scenario"),
            "overall_status": data.get("overall_status"),
            "proof_density": data.get("proof_density"),
            "artifacts": data.get("artifacts", []),
        }, indent=2, ensure_ascii=False))
        return 0

    return subprocess.run(
        [sys.executable, str(root / "dashboard" / "cli_report.py"), str(result_path)],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
