#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCENARIO_ORDER = [
    "ownership_transfer",
    "rtgs_settlement",
    "regtech_compliance",
    "nl_to_verified",
    "smart_contract_audit",
    "medical_device",
    "aviation_control",
    "merkle_tree_verification",
    "defi_invariant",
    "arklib_style_audit",
]
LAYER_LABELS = {
    "l1_z3": "L1 / Z3",
    "l2_agent": "L2 / Agent",
    "l3_lean": "L3 / Lean",
}

ERROR_LINE_RE = re.compile(
    r"InvalidPreState|not exhaustive|Counter[- ]?example|counterexample|Verification failed|error",
    re.IGNORECASE,
)
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


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


def layer_density_values(data: dict, layer: str) -> tuple[int, int, float]:
    counted_statuses = {"PASS", "REJECTED", "CERTIFIED", "FAIL"}
    verified_statuses = {"PASS", "REJECTED", "CERTIFIED"}
    steps = data.get("layers", {}).get(layer, {}).get("steps", [])
    counted = [step for step in steps if step.get("status") in counted_statuses]
    total = len(counted)
    verified = sum(1 for step in counted if step.get("status") in verified_statuses)
    percentage = round((verified / total) * 100, 1) if total else 0.0
    return verified, total, percentage


def density_label(verified: int, total: int, percentage: float) -> str:
    if total == 0:
        return "N/A"
    return f"{percentage:g}% ({verified}/{total})"


def duration_seconds(step: dict) -> float:
    return float(step.get("duration_ms", 0)) / 1000


def duration_text(step: dict) -> str:
    return f"{duration_seconds(step):.2f}s"


def proof_density_bar(percentage: float, width: int = 20) -> str:
    filled = round(width * max(0, min(percentage, 100)) / 100)
    return "█" * filled + "░" * (width - filled)


def generated_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def iter_steps(data: dict):
    for layer, payload in data.get("layers", {}).items():
        for step in payload.get("steps", []):
            yield layer, step


def total_duration_seconds(data: dict) -> float:
    return sum(duration_seconds(step) for _, step in iter_steps(data))


def rejected_failure_steps(data: dict) -> list[tuple[str, dict]]:
    return [
        (layer, step)
        for layer, step in iter_steps(data)
        if step.get("expect_failure") is True and step.get("status") == "REJECTED"
    ]


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def narrative_failure_lines(data: dict, step_id: str) -> list[str]:
    event = (
        data.get("narrative", {})
        .get("steps", {})
        .get(step_id, {})
        .get("rejected", {})
    )
    if not isinstance(event, dict):
        return []
    return [line for line in event.get("follow_up", []) if line.strip()]


def extract_error_message(data: dict, step: dict) -> str:
    combined = strip_ansi(f"{step.get('stdout', '')}\n{step.get('stderr', '')}")
    lines = [line.rstrip() for line in combined.splitlines() if line.strip()]
    selected: list[str] = []
    seen: set[int] = set()
    for index, line in enumerate(lines):
        if not ERROR_LINE_RE.search(line):
            continue
        for offset in range(max(0, index - 1), min(len(lines), index + 3)):
            if offset not in seen:
                selected.append(lines[offset])
                seen.add(offset)
    if selected:
        return "\n".join(selected[:24])

    fallback = narrative_failure_lines(data, str(step.get("id", "")))
    if fallback:
        return "\n".join(fallback[:12])
    if lines:
        return "\n".join(lines[:12])
    return "_No stdout/stderr was captured for this rejected step._"


def read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def changed_indices(
    before: list[str],
    after: list[str],
    context: int = 3,
) -> tuple[set[int], set[int]]:
    matcher = difflib.SequenceMatcher(None, before, after)
    before_indices: set[int] = set()
    after_indices: set[int] = set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        before_indices.update(range(max(0, i1 - context), min(len(before), i2 + context)))
        after_indices.update(range(max(0, j1 - context), min(len(after), j2 + context)))
    return before_indices, after_indices


def numbered_snippet(text: str, indices: set[int], max_lines: int = 90) -> str:
    lines = text.splitlines()
    if not lines:
        return "_No code file found._"
    if not indices:
        indices = set(range(min(len(lines), max_lines)))

    chosen = sorted(indices)
    chunks: list[list[int]] = []
    for index in chosen:
        if not chunks or index != chunks[-1][-1] + 1:
            chunks.append([index])
        else:
            chunks[-1].append(index)

    rendered: list[str] = []
    for chunk in chunks:
        if rendered:
            rendered.append("...")
        for index in chunk:
            if len(rendered) >= max_lines:
                rendered.append("...")
                return "\n".join(rendered)
            rendered.append(f"{index + 1:>4}| {lines[index]}")
    return "\n".join(rendered)


def code_fence(content: str, language: str = "text") -> str:
    fence = "```"
    if "```" in content:
        fence = "````"
    return f"{fence}{language}\n{content}\n{fence}"


def scenario_code_paths(root: Path, scenario: str) -> tuple[Path, Path]:
    scenario_dir = root / "scenarios" / scenario
    return scenario_dir / "buggy_code.mm", scenario_dir / "correct_code.mm"


def bug_detection_moment(data: dict, root: Path, heading: str, subheading: str) -> str:
    scenario = str(data.get("scenario", "unknown"))
    steps = rejected_failure_steps(data)
    before_path, after_path = scenario_code_paths(root, scenario)
    before_text = read_optional(before_path)
    after_text = read_optional(after_path)
    before_indices, after_indices = changed_indices(
        before_text.splitlines(),
        after_text.splitlines(),
    )
    diff = "\n".join(difflib.unified_diff(
        before_text.splitlines(),
        after_text.splitlines(),
        fromfile=relpath(before_path, root),
        tofile=relpath(after_path, root),
        lineterm="",
    ))

    lines = [heading, ""]
    if not steps:
        lines.append(
            "_No `expect_failure: true` step with `status: REJECTED` was found for this scenario._"
        )
        return "\n".join(lines)

    for index, (layer, step) in enumerate(steps):
        if len(steps) > 1:
            lines.extend([f"{subheading} Step {index + 1}: `{layer}/{step.get('id')}`", ""])
        lines.extend([
            f"{subheading} BEFORE: LLM alone (bug missed)",
            "",
            f"`{relpath(before_path, root)}`",
            "",
            code_fence(numbered_snippet(before_text, before_indices)),
            "",
            f"{subheading} mumei verify → BUG DETECTED",
            "",
            f"`{layer}/{step.get('id')}` rejected as expected.",
            "",
            code_fence(extract_error_message(data, step)),
            "",
            f"{subheading} AFTER: LLM + mumei (bug caught)",
            "",
            f"`{relpath(after_path, root)}`",
            "",
            code_fence(numbered_snippet(after_text, after_indices)),
        ])
        if diff:
            lines.extend([
                "",
                f"{subheading} BEFORE → AFTER diff",
                "",
                code_fence(diff, "diff"),
            ])
        lines.append("")
    return "\n".join(lines).rstrip()


def render_proof_density_markdown(data: dict) -> str:
    verified, total, percentage = density_values(data)
    lines = [
        "## Proof Density",
        "",
        f"- Verified atoms/steps: **{verified}**",
        f"- Total atoms/steps: **{total}**",
        f"- Percentage: **{percentage:g}%**",
        f"- Visual: `{proof_density_bar(percentage)}`",
    ]
    if "l3_lean" in data.get("layers", {}):
        lean_verified, lean_total, lean_percentage = layer_density_values(data, "l3_lean")
        lines.append(
            f"- Lean proof coverage: **{density_label(lean_verified, lean_total, lean_percentage)}**"
        )
    return "\n".join(lines)


def render_harness_contract_markdown(data: dict) -> str:
    contract = data.get("harness_contract")
    if not isinstance(contract, dict):
        return ""

    lines = [
        "## Harness Contract",
        "",
        f"- Policy: `{contract.get('policy', 'unspecified')}`",
        f"- Acceptance path: `{', '.join(str(item) for item in contract.get('acceptance_path', []))}`",
        f"- State directory: `{contract.get('state_dir', 'unspecified')}`",
        f"- Intent: {contract.get('intent', '_Not specified_')}",
    ]
    artifact_contracts = contract.get("artifact_contracts", [])
    if isinstance(artifact_contracts, list) and artifact_contracts:
        lines.extend(["", "### Artifact contracts"])
        for item in artifact_contracts:
            lines.append(f"- {item}")

    stage_rows: list[str] = []
    for layer, step in iter_steps(data):
        if not any(key in step for key in ("harness_stage", "artifact_contract", "verifier_gate")):
            continue
        stage = str(step.get("harness_stage", ""))
        gate = str(step.get("verifier_gate", "")).replace("|", "\\|")
        artifacts = step.get("artifact_contract", step.get("artifacts", []))
        if isinstance(artifacts, list):
            artifact_text = ", ".join(str(item) for item in artifacts) or "-"
        else:
            artifact_text = str(artifacts)
        stage_rows.append(
            f"| {LAYER_LABELS.get(layer, layer)} | {stage} | {artifact_text} | {gate} |"
        )
    if stage_rows:
        lines.extend([
            "",
            "### Stage gates",
            "",
            "| Layer | Harness stage | Artifact contract | Verifier gate |",
            "| --- | --- | --- | --- |",
            *stage_rows,
        ])
    return "\n".join(lines)


def render_layer_breakdown_markdown(data: dict) -> str:
    lines = [
        "## Layer Breakdown",
        "",
        "| Layer | Step | Result | Duration |",
        "| --- | --- | --- | ---: |",
    ]
    step_count = 0
    for layer, step in iter_steps(data):
        step_count += 1
        label = LAYER_LABELS.get(layer, layer)
        status = step.get("display_status") or step.get("status", "UNKNOWN")
        name = str(step.get("name", step.get("id", ""))).replace("|", "\\|")
        lines.append(f"| {label} | {name} | {status} | {duration_text(step)} |")
    if step_count == 0:
        lines.append("| _No layer steps were recorded._ |  |  |  |")
    return "\n".join(lines)


def render_duration_markdown(data: dict) -> str:
    lines = [
        "## Duration",
        "",
        f"- Total recorded step time: **{total_duration_seconds(data):.2f}s**",
        "",
        "| Step | Duration |",
        "| --- | ---: |",
    ]
    for _, step in iter_steps(data):
        name = str(step.get("name", step.get("id", ""))).replace("|", "\\|")
        lines.append(f"| {name} | {duration_text(step)} |")
    return "\n".join(lines)


def render_bug_detection_markdown(data: dict, root: Path) -> str:
    narrative = data.get("narrative", {})
    before = narrative.get("before", "_No BEFORE narrative was provided._")
    after = narrative.get("after", "_No AFTER narrative was provided._")
    return "\n".join([
        "## Bug Detection",
        "",
        "### Narrative",
        "",
        f"- Before: {before}",
        f"- After: {after}",
        "",
        bug_detection_moment(data, root, "### Evidence", "####"),
    ]).rstrip()


def render_scenario_markdown(data: dict, root: Path) -> str:
    lines = [
        f"# Mumei Verification Report: {data.get('scenario_name', data.get('scenario'))}",
        "",
        f"Generated: {generated_at()}",
        "",
        f"Scenario: `{data.get('scenario')}`",
        f"Overall status: {data.get('overall_status', 'UNKNOWN')}",
        "",
        render_bug_detection_markdown(data, root),
        "",
        render_proof_density_markdown(data),
        "",
        render_harness_contract_markdown(data),
        "",
        render_layer_breakdown_markdown(data),
        "",
        render_duration_markdown(data),
        "",
    ]
    return "\n".join(lines)


def write_scenario_markdown(result_path: Path, root: Path, output_path: Path | None = None) -> Path:
    data = load_json(result_path)
    target = output_path or result_path.parent / "report.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_scenario_markdown(data, root), encoding="utf-8")
    return target


def write_summary(
    reports_dir: Path,
    output_path: Path,
    scenarios: list[str],
    require_all: bool,
) -> int:
    rows: list[tuple[str, str, int, int, float, str]] = []
    missing: list[str] = []
    for scenario in scenarios:
        result_path = latest_result_path(reports_dir, scenario)
        if result_path is None:
            missing.append(scenario)
            continue
        data = load_json(result_path)
        verified, total, percentage = density_values(data)
        lean_density = "N/A"
        if "l3_lean" in data.get("layers", {}):
            lean_density = density_label(*layer_density_values(data, "l3_lean"))
        rows.append((
            scenario,
            str(data.get("overall_status", "UNKNOWN")),
            verified,
            total,
            percentage,
            lean_density,
        ))

    lines = [
        "# Mumei Demo Summary",
        "",
        f"Generated: {generated_at()}",
        "",
        "| Scenario | Overall status | Verified | Total | Proof density | Lean proof coverage |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for scenario, status, verified, total, percentage, lean_density in rows:
        lines.append(
            f"| `{scenario}` | {status} | {verified} | {total} | {percentage:g}% | {lean_density} |"
        )
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


def write_highlights(
    root: Path,
    reports_dir: Path,
    output_path: Path,
    scenarios: list[str],
    require_all: bool,
) -> int:
    missing: list[str] = []
    lines = [
        "# Mumei Demo Bug Detection Highlights",
        "",
        f"Generated: {generated_at()}",
        "",
    ]
    for scenario in scenarios:
        result_path = latest_result_path(reports_dir, scenario)
        if result_path is None:
            missing.append(scenario)
            continue
        data = load_json(result_path)
        verified, total, percentage = density_values(data)
        lines.extend([
            f"## {data.get('scenario_name', scenario)}",
            "",
            f"- Scenario: `{scenario}`",
            f"- Overall status: {data.get('overall_status', 'UNKNOWN')}",
            f"- Proof density: {percentage:g}% ({verified}/{total} atoms)",
        ])
        if "l3_lean" in data.get("layers", {}):
            lines.append(f"- Lean proof coverage: {density_label(*layer_density_values(data, 'l3_lean'))}")
        lines.extend([
            "",
            bug_detection_moment(data, root, "### Bug Detection Moment", "####"),
            "",
        ])

    if missing:
        lines.extend(["## Missing results", ""])
        lines.extend(f"- `{scenario}`" for scenario in missing)
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Highlights written to {output_path}")
    if missing and require_all:
        print(f"Missing result.json for: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Mumei demo result.")
    parser.add_argument("result_json", nargs="?", help="Path to result.json")
    parser.add_argument("--format", choices=("table", "json", "markdown"), default="table")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Aggregate latest scenario result.json files into dashboard/summary.md",
    )
    parser.add_argument(
        "--highlights",
        action="store_true",
        help="Aggregate bug detection moments into dashboard/highlights.md",
    )
    parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Directory containing scenario reports",
    )
    parser.add_argument(
        "--output",
        default="dashboard/summary.md",
        help="Summary markdown output path",
    )
    parser.add_argument(
        "--highlights-output",
        default="dashboard/highlights.md",
        help="Highlights markdown output path",
    )
    parser.add_argument(
        "--report-output",
        help="Scenario markdown output path; defaults to report.md next to result_json",
    )
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
    if args.summary or args.highlights:
        reports_dir = Path(args.reports_dir)
        if not reports_dir.is_absolute():
            reports_dir = root / reports_dir
        status = 0
        if args.summary:
            output_path = Path(args.output)
            if not output_path.is_absolute():
                output_path = root / output_path
            status |= write_summary(
                reports_dir,
                output_path,
                list(args.scenarios),
                args.require_all,
            )
        if args.highlights:
            highlights_path = Path(args.highlights_output)
            if not highlights_path.is_absolute():
                highlights_path = root / highlights_path
            status |= write_highlights(
                root,
                reports_dir,
                highlights_path,
                list(args.scenarios),
                args.require_all,
            )
        return status

    if not args.result_json:
        parser.error("result_json is required unless --summary or --highlights is used")

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

    report_output = Path(args.report_output) if args.report_output else None
    if report_output and not report_output.is_absolute():
        report_output = root / report_output
    if args.format == "markdown":
        if report_output is None:
            report_path = write_scenario_markdown(result_path, root, None)
            print(f"Markdown report written to {report_path}")
        else:
            data = load_json(result_path)
            markdown = render_scenario_markdown(data, root)
            report_output.parent.mkdir(parents=True, exist_ok=True)
            report_output.write_text(markdown, encoding="utf-8")
            print(f"Markdown report written to {report_output}")
        return 0

    return subprocess.run(
        [sys.executable, str(root / "dashboard" / "cli_report.py"), str(result_path)],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
