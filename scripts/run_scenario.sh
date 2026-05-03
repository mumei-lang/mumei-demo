#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/run_scenario.sh <scenario_name> [--mumei-repo PATH] [--mumei-lean-repo PATH] [--mumei-agent-repo PATH] [--mumei-agent-python PATH] [--mumei-bin PATH]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <scenario_name> [--mumei-repo PATH] [--mumei-lean-repo PATH] [--mumei-agent-repo PATH] [--mumei-agent-python PATH] [--mumei-bin PATH]" >&2
  exit 2
fi

SCENARIO_NAME="$1"
shift

python3 - "$ROOT_DIR" "$SCENARIO_NAME" "$@" <<'PY'
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def parse_args(argv: list[str]) -> dict[str, str | None]:
    root = Path(argv[0]).resolve()
    scenario_name = argv[1]
    env = load_env(root / "repos.env")
    values: dict[str, str | None] = {
        "root_dir": str(root),
        "scenario_name": scenario_name,
        "mumei_repo": env.get("MUMEI_REPO") or str((root / "../mumei").resolve()),
        "mumei_lean_repo": env.get("MUMEI_LEAN_REPO") or str((root / "../mumei-lean").resolve()),
        "mumei_agent_repo": env.get("MUMEI_AGENT_REPO") or str((root / "../mumei-agent").resolve()),
        "mumei_agent_python": env.get("MUMEI_AGENT_PYTHON"),
        "mumei_bin": env.get("MUMEI_BIN"),
    }
    if not values["mumei_bin"]:
        values["mumei_bin"] = str(Path(str(values["mumei_repo"])) / "target" / "release" / "mumei")
    if not values["mumei_agent_python"]:
        agent_venv_python = Path(str(values["mumei_agent_repo"])) / ".venv" / "bin" / "python"
        values["mumei_agent_python"] = (
            str(agent_venv_python)
            if agent_venv_python.exists()
            else shutil.which("python") or sys.executable
        )

    args = argv[2:]
    i = 0
    while i < len(args):
        key = args[i]
        if key not in {
            "--mumei-repo",
            "--mumei-lean-repo",
            "--mumei-agent-repo",
            "--mumei-agent-python",
            "--mumei-bin",
        }:
            raise SystemExit(f"unknown argument: {key}")
        if i + 1 >= len(args):
            raise SystemExit(f"missing value for {key}")
        name = key[2:].replace("-", "_")
        if name == "mumei_agent_python":
            values[name] = str(Path(args[i + 1]).expanduser())
        else:
            values[name] = str(Path(args[i + 1]).expanduser().resolve())
        i += 2
    return values


def substitute(value: str, placeholders: dict[str, str]) -> str:
    result = value
    for key, replacement in placeholders.items():
        result = result.replace("{" + key + "}", replacement)
    return result


def shell_placeholders(placeholders: dict[str, str]) -> dict[str, str]:
    return {key: shlex.quote(value) for key, value in placeholders.items()}


def expected_status(step: dict, exit_code: int) -> str:
    if exit_code != int(step.get("expected_exit", 0)):
        return "FAIL"
    if step.get("expect_failure"):
        return "REJECTED"
    return "PASS"


def display_status(layer: str, step: dict, status: str) -> str:
    if status != "PASS":
        return status
    if layer == "l3_lean" and "build" in step.get("id", ""):
        return "CERTIFIED"
    return status


def check_patterns(output: str, patterns: list[str]) -> tuple[bool, list[str]]:
    missing = [pattern for pattern in patterns if pattern not in output]
    return not missing, missing


def proof_density(step_results: dict[str, dict]) -> dict[str, float | int]:
    counted = [
        step for step in step_results.values()
        if step["status"] in {"PASS", "REJECTED", "CERTIFIED", "FAIL"}
    ]
    total = len(counted)
    verified = sum(1 for step in counted if step["status"] in {"PASS", "REJECTED", "CERTIFIED"})
    percentage = round((verified / total) * 100, 1) if total else 0.0
    return {"verified": verified, "total": total, "percentage": percentage}


def main(argv: list[str]) -> int:
    values = parse_args(argv)
    root = Path(str(values["root_dir"]))
    scenario_name = str(values["scenario_name"])
    scenario_path = root / "scenarios" / scenario_name / "scenario.json"
    if not scenario_path.exists():
        raise SystemExit(f"scenario not found: {scenario_path}")

    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    iso_timestamp = now.isoformat().replace("+00:00", "Z")
    output_dir = root / "reports" / scenario_name / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    placeholders = {
        "mumei_repo": str(values["mumei_repo"]),
        "mumei_lean_repo": str(values["mumei_lean_repo"]),
        "mumei_agent_repo": str(values["mumei_agent_repo"]),
        "mumei_agent_python": str(values["mumei_agent_python"]),
        "mumei_bin": str(values["mumei_bin"]),
        "output_dir": str(output_dir),
    }
    command_placeholders = shell_placeholders(placeholders)

    print(f"Running scenario: {scenario['name']}")
    print(f"Report directory: {output_dir}")

    results: dict[str, dict] = {}
    step_index: dict[str, dict] = {}
    artifacts: list[str] = []
    overall_status = "PASS"

    for layer in scenario.get("layers", []):
        layer_steps: list[dict] = []
        for step in scenario.get(layer, {}).get("steps", []):
            step_id = step["id"]
            log_file = f"{step_id}.log"
            log_path = output_dir / log_file
            start = time.monotonic()

            missing_tool = step.get("optional_toolchain") and shutil.which(step["optional_toolchain"]) is None
            blocked_by = [
                dep for dep in step.get("depends_on", [])
                if step_index.get(dep, {}).get("status") not in {"PASS", "REJECTED", "CERTIFIED"}
            ]
            if missing_tool:
                duration_ms = int((time.monotonic() - start) * 1000)
                message = f"SKIPPED: optional toolchain not found: {step['optional_toolchain']}\n"
                log_path.write_text(message, encoding="utf-8")
                status = "SKIPPED"
                exit_code = None
                stdout = message
                stderr = ""
            elif blocked_by:
                duration_ms = int((time.monotonic() - start) * 1000)
                message = f"SKIPPED: dependency failed or skipped: {', '.join(blocked_by)}\n"
                log_path.write_text(message, encoding="utf-8")
                status = "SKIPPED"
                exit_code = None
                stdout = message
                stderr = ""
            else:
                command = substitute(step["command"], command_placeholders)
                cwd = substitute(step.get("cwd", str(root)), placeholders)
                proc = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env={
                        **os.environ.copy(),
                        "MUMEI_REPO": placeholders["mumei_repo"],
                        "MUMEI_LEAN_REPO": placeholders["mumei_lean_repo"],
                        "MUMEI_AGENT_REPO": placeholders["mumei_agent_repo"],
                        "MUMEI_AGENT_PYTHON": placeholders["mumei_agent_python"],
                        "MUMEI_BIN": placeholders["mumei_bin"],
                        "MUMEI_STD_PATH": os.environ.get(
                            "MUMEI_STD_PATH",
                            str(Path(placeholders["mumei_repo"]) / "std"),
                        ),
                    },
                    check=False,
                )
                duration_ms = int((time.monotonic() - start) * 1000)
                combined = proc.stdout + proc.stderr
                ok_patterns, missing = check_patterns(combined, list(step.get("expected_patterns", [])))
                status = expected_status(step, proc.returncode)
                if status == "PASS" and layer == "l3_lean" and "build" in step_id:
                    status = "CERTIFIED"
                if not ok_patterns:
                    status = "FAIL"
                exit_code = proc.returncode
                stdout = proc.stdout
                stderr = proc.stderr
                log_path.write_text(
                    f"$ {command}\n\n[stdout]\n{stdout}\n[stderr]\n{stderr}\n",
                    encoding="utf-8",
                )
                if missing:
                    with log_path.open("a", encoding="utf-8") as handle:
                        handle.write("\n[missing expected patterns]\n")
                        handle.write("\n".join(missing) + "\n")
                    print(f"[missing expected patterns] {step_id}: {', '.join(missing)}", file=sys.stderr)
                if status == "FAIL":
                    overall_status = "FAIL"
                    if stderr:
                        print(f"[stderr] {step_id}:\n{stderr}", file=sys.stderr)
                    if stdout:
                        print(f"[stdout] {step_id}:\n{stdout}", file=sys.stderr)

            step_result = {
                "id": step_id,
                "name": step.get("name", step_id),
                "repo": step.get("repo"),
                "status": status,
                "display_status": display_status(layer, step, status),
                "exit_code": exit_code,
                "expected_exit": step.get("expected_exit"),
                "expect_failure": bool(step.get("expect_failure", False)),
                "duration_ms": duration_ms,
                "output_file": log_file,
                "stdout": stdout,
                "stderr": stderr,
                "artifacts": step.get("artifacts", []),
            }
            for artifact in step.get("artifacts", []):
                if (output_dir / artifact).exists():
                    artifacts.append(artifact)
            layer_steps.append(step_result)
            step_index[step_id] = step_result
            print(f"{layer}/{step_id}: {status}")

        layer_status = "PASS"
        if any(step["status"] == "FAIL" for step in layer_steps):
            layer_status = "FAIL"
        elif layer_steps and all(step["status"] == "SKIPPED" for step in layer_steps):
            layer_status = "SKIPPED"
        results[layer] = {"status": layer_status, "steps": layer_steps}

    result = {
        "scenario": scenario_name,
        "scenario_name": scenario.get("name", scenario_name),
        "version": scenario.get("version"),
        "description": scenario.get("description"),
        "timestamp": iso_timestamp,
        "layers": results,
        "overall_status": overall_status,
        "proof_density": proof_density(step_index),
        "artifacts": artifacts,
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    latest = root / "reports" / scenario_name / "latest"
    if latest.exists() or latest.is_symlink():
        if latest.is_symlink() or latest.is_file():
            latest.unlink()
        else:
            shutil.rmtree(latest)
    try:
        latest.symlink_to(output_dir, target_is_directory=True)
    except OSError:
        shutil.copytree(output_dir, latest)

    subprocess.run(
        [sys.executable, str(root / "scripts" / "generate_report.py"), str(output_dir / "result.json")],
        cwd=root,
        check=False,
    )
    return 0 if overall_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
PY
