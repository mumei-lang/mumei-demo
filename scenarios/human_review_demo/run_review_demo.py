#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> dict[str, object]:
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def load_tool_payload(raw: str) -> dict[str, object]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("MCP tool returned a non-object payload")
    if payload.get("status") != "ok":
        raise RuntimeError(json.dumps(payload, ensure_ascii=False))
    return payload


def main() -> int:
    here = Path(__file__).resolve().parent
    default_root = here.parents[1]
    parser = argparse.ArgumentParser(description="Run the human-review workflow demo.")
    parser.add_argument("--mumei-bin", default=os.environ.get("MUMEI_BIN", "mumei"))
    parser.add_argument(
        "--mumei-agent-repo",
        default=os.environ.get("MUMEI_AGENT_REPO", str(default_root.parent / "mumei-agent")),
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = here / "trusted_atom_review.mm"

    emit_result = run(
        [
            args.mumei_bin,
            "verify",
            str(spec),
            "--emit",
            "human-review-queue",
            "--report-dir",
            str(output_dir),
        ]
    )
    if emit_result["returncode"] != 0:
        print(json.dumps({"emit_result": emit_result}, indent=2, ensure_ascii=False))
        return int(emit_result["returncode"])

    queue_path = output_dir / "human_review_queue.json"
    if not queue_path.exists():
        print(f"human_review_queue.json was not generated at {queue_path}", file=sys.stderr)
        return 1

    agent_repo = Path(args.mumei_agent_repo).resolve()
    sys.path.insert(0, str(agent_repo))
    from agent import mcp_server

    queue_payload = load_tool_payload(mcp_server.get_review_queue(str(output_dir)))
    queue = queue_payload["queue"]
    if not isinstance(queue, dict):
        raise RuntimeError("review queue missing from MCP payload")
    atoms = queue.get("atoms")
    if not isinstance(atoms, list) or not atoms:
        raise RuntimeError("review queue contained no atoms")
    first_atom = atoms[0]
    if not isinstance(first_atom, dict) or not isinstance(first_atom.get("name"), str):
        raise RuntimeError("review queue atom is malformed")
    atom_name = first_atom["name"]

    approval_payload = load_tool_payload(
        mcp_server.approve_review(
            atom_name,
            "demo-reviewer",
            "Trusted external_risk_score contract reviewed for demo.",
        )
    )

    reverify_result = run([args.mumei_bin, "verify", str(spec)])
    result = {
        "queue_path": str(queue_path),
        "review_queue": queue_payload,
        "approval": approval_payload,
        "reverify": reverify_result,
        "passed": reverify_result["returncode"] == 0,
    }
    result_path = output_dir / "review_demo_result.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("human-review-queue generated")
    print(f"approved {atom_name}")
    print("reverification passed" if result["passed"] else "reverification failed")
    print(f"result: {result_path}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
