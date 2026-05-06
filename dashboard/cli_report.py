#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


LAYER_LABELS = {
    "l1_z3": "L1: Z3",
    "l2_agent": "L2: AI",
    "l3_lean": "L3: Lean",
}


ROOT = Path(__file__).resolve().parent.parent


def step_status(layer: str, step: dict) -> str:
    status = step.get("status", "UNKNOWN")
    return step.get("display_status") or status


def duration(step: dict) -> str:
    return f"{step.get('duration_ms', 0) / 1000:.2f}s"


def rows(data: dict) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for layer, payload in data.get("layers", {}).items():
        label = LAYER_LABELS.get(layer, layer)
        for step in payload.get("steps", []):
            out.append((label, step.get("name", step.get("id", "")), step_status(layer, step), duration(step)))
    return out


def box(lines: list[str], width: int = 68) -> str:
    top = "╔" + "═" * (width - 2) + "╗"
    sep = "╠" + "═" * (width - 2) + "╣"
    bottom = "╚" + "═" * (width - 2) + "╝"
    body = ["║" + line[: width - 4].ljust(width - 2) + "║" for line in lines]
    return "\n".join([top, body[0], sep, *body[1:], bottom])


def proof_density_bar(percentage: float, width: int = 24) -> str:
    filled = round(width * max(0, min(percentage, 100)) / 100)
    return "█" * filled + "░" * (width - filled)


def render(data: dict) -> str:
    title = f"  Mumei Verification Report: {data.get('scenario_name', data.get('scenario'))}"
    narrative = data.get("narrative", {})
    before = narrative.get("before", "hostile_takeover skips accept and tries Idle → Transferred")
    after = narrative.get("after", "InvalidPreState catches the bug before deployment")
    table = [
        "",
        "  BEFORE: LLM alone",
        f"    {before}",
        "",
        "  AFTER: LLM + mumei",
        f"    {after}",
        "",
        "  Layer      Step                       Status      Duration",
        "  ─────────  ─────────────────────────  ──────────  ────────",
    ]
    for layer, name, status, elapsed in rows(data):
        table.append(f"  {layer:<10} {name[:25]:<25}  {status:<10}  {elapsed:<8}")
    density = data.get("proof_density", {})
    pct = density.get("percentage", 0)
    verified = density.get("verified", 0)
    total = density.get("total", 0)
    audit_status = "TRUSTLESS" if data.get("overall_status") == "PASS" else "ATTENTION"
    table.extend([
        "",
        f"  Proof Density: [{proof_density_bar(float(pct))}] {pct:g}%",
        f"                 {verified}/{total} atoms or layer steps verified",
        f"  Audit Status:  {audit_status}",
        "  Moment:        Proof failure → Bug found",
    ])
    return box([title, *table])


def latest_result(scenario_dir: Path) -> Path | None:
    report_dir = ROOT / "reports" / scenario_dir.name
    latest = report_dir / "latest" / "result.json"
    if latest.exists():
        return latest
    candidates = sorted(report_dir.glob("*/result.json"), reverse=True)
    return candidates[0] if candidates else None


def render_all() -> str:
    lines = [
        "Scenario                  Status      Verification  Proof Density",
        "────────────────────────  ──────────  ────────────  ─────────────",
    ]
    for scenario_dir in sorted((ROOT / "scenarios").iterdir()):
        if not scenario_dir.is_dir() or scenario_dir.name == "_template":
            continue
        path = latest_result(scenario_dir)
        if path is None:
            lines.append(f"{scenario_dir.name[:24]:<24}  MISSING     -             -")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        layers = data.get("layers", {})
        verification = "Z3 + Lean 4" if "l3_lean" in layers else "Z3 Only"
        density = data.get("proof_density", {})
        pct = density.get("percentage", 0)
        verified = density.get("verified", 0)
        total = density.get("total", 0)
        lines.append(
            f"{scenario_dir.name[:24]:<24}  "
            f"{data.get('overall_status', 'UNKNOWN'):<10}  "
            f"{verification:<12}  "
            f"{pct:g}% ({verified}/{total})"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Mumei verification report.")
    parser.add_argument("result_json", nargs="?", help="Path to result.json")
    parser.add_argument("--all", action="store_true", help="Render all scenarios")
    args = parser.parse_args()

    if args.all:
        print(render_all())
        return 0
    if not args.result_json:
        parser.error("result_json is required unless --all is used")
    data = json.loads(Path(args.result_json).read_text(encoding="utf-8"))
    print(render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
