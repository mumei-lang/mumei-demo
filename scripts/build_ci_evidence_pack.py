#!/usr/bin/env python3
"""Build the deterministic CI audit evidence-pack reference artifact.

The pack intentionally uses the current audit CLI contract.  It records the
absence of SARIF/baseline support as an explicit capability boundary instead
of synthesizing those artifacts in the demo repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

FIXED_AUDIT_KEYS = [
    "spec_health_issues",
    "verification_violations",
    "verification_status",
    "cross_validation_gaps",
    "next_steps",
    "migration_hints",
    "healed_files",
    "heal_errors",
    "trusted_atoms",
]

PACK_SCHEMA = "mumei-demo.ci-evidence-pack/v1"
MIGRATION_PLAN_SCHEMA = "mumei-demo.migration-plan/v1"

ARTIFACT_PATHS = (
    "audit.json",
    "audit.stderr.log",
    "migration_plan.json",
    "verification.json",
    "reference.proof.json",
    "reference-verify.log",
    "reference-verify-cert.log",
    "github-actions-mumei-audit.yml",
    "summary.md",
)
ARTIFACT_ROLES = {
    "audit_report": ["audit.json"],
    "migration_plan": ["migration_plan.json"],
    "proof_certificate": ["reference.proof.json"],
    "native_bundle": [],
    "adapter_observation": [],
}
EVIDENCE_BOUNDARIES = {
    "audit_report": "Existing-code audit evidence; not a proof certificate.",
    "migration_plan": "Human-review migration scaffold; not evidence of completed migration.",
    "proof_certificate": "Proof only for the reviewed reference .mm contract; not host-code equivalence.",
    "native_bundle": "No native bundle is present or implied by this audit/migration evidence pack.",
    "adapter_observation": "No adapter observation is present or implied by this audit/migration evidence pack.",
}


def artifact_roles() -> dict[str, list[str]]:
    return {role: list(paths) for role, paths in ARTIFACT_ROLES.items()}


def evidence_metadata() -> dict[str, Any]:
    return {
        "artifact_paths": list(ARTIFACT_PATHS),
        "artifact_roles": artifact_roles(),
        "evidence_boundary_by_role": dict(EVIDENCE_BOUNDARIES),
    }


class EvidencePackError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=180,
    )


def _redact_source_path(value: Any, source: Path) -> Any:
    source_text = str(source)
    if isinstance(value, str):
        return value.replace(source_text, "fixture/ledger.py")
    if isinstance(value, list):
        return [_redact_source_path(item, source) for item in value]
    if isinstance(value, dict):
        return {key: _redact_source_path(item, source) for key, item in value.items()}
    return value


def _load_audit_json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise EvidencePackError(
            "audit did not emit JSON stdout; "
            f"exit={result.returncode}, stderr={result.stderr[:300]!r}"
        ) from exc
    if not isinstance(payload, dict):
        raise EvidencePackError("audit JSON stdout must be an object")
    missing = [key for key in FIXED_AUDIT_KEYS if key not in payload]
    if missing:
        raise EvidencePackError(f"audit JSON is missing fixed contract keys: {', '.join(missing)}")
    return payload


def _audit_environment(base_env: dict[str, str], mumei_bin: Path) -> dict[str, str]:
    env = dict(base_env)
    # Deterministic reference mode: the current CLI falls back to its parser
    # path when both credential variables are present but empty.  Setting empty
    # values also prevents dotenv from filling them from a developer checkout.
    env["LLM_API_KEY"] = ""
    env["OPENAI_API_KEY"] = ""
    env["CI_FIXTURE_MODE"] = "1"
    env["MUMEI_BIN"] = str(mumei_bin)
    return env


def run_audit(
    *,
    source: Path,
    agent_repo: Path,
    agent_python: Path,
    mumei_bin: Path,
    env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], subprocess.CompletedProcess[str]]:
    command = [
        str(agent_python),
        "-m",
        "agent",
        "audit",
        "--code-file",
        str(source),
        "--language",
        "python",
        "--format",
        "json",
        "--auto-migrate",
    ]
    completed = _run(
        command,
        cwd=agent_repo,
        env=_audit_environment(os.environ if env is None else env, mumei_bin),
    )
    return _load_audit_json(completed), completed


def run_reference_verification(
    *,
    reference: Path,
    pack_dir: Path,
    workspace: Path,
    mumei_bin: Path,
    env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], str, str]:
    base_env = dict(os.environ if env is None else env)
    base_env["LLVM_SYS_170_PREFIX"] = base_env.get("LLVM_SYS_170_PREFIX", "/usr/lib/llvm-17")
    verify = _run(
        [
            str(mumei_bin),
            "verify",
            str(reference),
            "--proof-cert",
            "--output",
            str(pack_dir / "reference.proof.json"),
        ],
        cwd=workspace,
        env=base_env,
    )
    verify_log = verify.stdout + verify.stderr
    if verify.returncode != 0:
        raise EvidencePackError(f"reference mumei verify failed with exit {verify.returncode}")
    certificate_path = pack_dir / "reference.proof.json"
    if not certificate_path.exists():
        raise EvidencePackError("reference proof certificate was not written")
    recheck = _run(
        [str(mumei_bin), "verify-cert", "--strict", str(certificate_path), str(reference)],
        cwd=workspace,
        env=base_env,
    )
    recheck_log = recheck.stdout + recheck.stderr
    if recheck.returncode != 0:
        raise EvidencePackError(f"reference verify-cert failed with exit {recheck.returncode}")
    try:
        certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidencePackError("reference proof certificate is not valid JSON") from exc
    verification = {
        "schema": "mumei-demo.reference-verification/v1",
        "reference_contract": "reference/safe_divide.mm",
        "proof_certificate": "reference.proof.json",
        "verify_exit_code": verify.returncode,
        "verify_cert_exit_code": recheck.returncode,
        "all_verified": certificate.get("all_verified") is True,
        "atoms": [
            {
                "name": atom.get("name"),
                "status": atom.get("status"),
                "z3_check_result": atom.get("z3_check_result"),
            }
            for atom in certificate.get("atoms", [])
            if isinstance(atom, dict)
        ],
        "boundary": (
            "This certificate proves only the reviewed reference .mm contract. "
            "It does not prove semantic equivalence between that contract and fixture/ledger.py."
        ),
    }
    if verification["all_verified"] is not True:
        raise EvidencePackError("reference proof certificate does not have all_verified=true")
    return verification, verify_log, recheck_log


def migration_plan(audit: dict[str, Any]) -> dict[str, Any]:
    hints = audit.get("migration_hints")
    if not isinstance(hints, list):
        raise EvidencePackError("audit migration_hints must be a list")
    entries = []
    for index, hint in enumerate(hints):
        if not isinstance(hint, dict):
            raise EvidencePackError(f"migration hint {index} is not an object")
        entries.append(
            {
                "function_name": hint.get("function_name"),
                "priority": hint.get("priority", "review"),
                "reason": hint.get("reason", ""),
                "readiness": "human_review_required",
                "skeleton": hint.get("skeleton", ""),
                "next_step": hint.get("next_step", ""),
                "evidence_boundary": (
                    "The skeleton is a migration scaffold, not proof that the Python body implements the contract."
                ),
            }
        )
    return {
        "schema": MIGRATION_PLAN_SCHEMA,
        "source": "fixture/ledger.py",
        "audit_verification_status": audit.get("verification_status"),
        "deterministic_mode": True,
        **evidence_metadata(),
        "entries": entries,
        "summary": {
            "candidate_count": len(entries),
            "high_priority_count": sum(entry["priority"] == "high" for entry in entries),
        },
    }


def _artifact_rows(paths: list[Path], pack_dir: Path) -> list[dict[str, str]]:
    rows = []
    for path in paths:
        rows.append(
            {
                "path": path.relative_to(pack_dir).as_posix(),
                "sha256": _sha256(path),
            }
        )
    return rows


def write_summary(path: Path, audit: dict[str, Any], plan: dict[str, Any], verification: dict[str, Any]) -> None:
    findings = audit.get("finding_counts") if isinstance(audit.get("finding_counts"), dict) else {}
    lines = [
        "# Mumei CI evidence pack",
        "",
        "Deterministic audit reference run; no LLM credentials are used.",
        "",
        "## Result",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Audit status | `{audit.get('verification_status')}` |",
        f"| Code findings | {findings.get('code', 'not reported')} |",
        f"| Spec/model findings | {findings.get('spec', 'not reported')} |",
        f"| Migration candidates | {plan['summary']['candidate_count']} |",
        f"| Reference `.mm` certificate | `{verification['proof_certificate']}` |",
        "",
        "## Artifact map",
        "",
        "- `audit.json`: normalized current-CLI audit JSON with fixed keys.",
        "- `migration_plan.json`: prioritized human-review migration plan derived from `migration_hints`.",
        "- `reference.proof.json`: proof certificate for the reviewed reference `.mm` contract only.",
        "- `github-actions-mumei-audit.yml`: copyable reference workflow.",
        "- `audit.sarif`: intentionally absent until the audit CLI emits SARIF; no demo-side SARIF is fabricated.",
        "",
        "## Evidence boundary",
        "",
        "The audit report identifies review and migration work. The reference certificate proves the standalone `.mm` contract. Neither artifact yet proves semantic equivalence between the Python implementation and the `.mm` contract.",
        "",
        "`native_bundle` and `adapter_observation` are empty roles in `artifact_roles`; neither audit findings nor migration scaffolds may be relabeled as those evidence classes.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_evidence_pack(
    *,
    scenario_dir: Path,
    output_dir: Path,
    agent_repo: Path,
    agent_python: Path,
    mumei_bin: Path,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    source = scenario_dir / "src" / "ledger.py"
    reference = scenario_dir / "reference" / "safe_divide.mm"
    workflow_template = scenario_dir / "reference" / "workflows" / "mumei-audit.yml"
    for required in (source, reference, workflow_template, agent_python, mumei_bin):
        if not required.exists():
            raise EvidencePackError(f"required input is missing: {required}")

    workspace = output_dir / "workspace"
    pack_dir = output_dir / "evidence-pack"
    if workspace.exists():
        shutil.rmtree(workspace)
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    workspace.mkdir(parents=True)
    pack_dir.mkdir(parents=True)

    audit_raw, audit_completed = run_audit(
        source=source,
        agent_repo=agent_repo,
        agent_python=agent_python,
        mumei_bin=mumei_bin,
        env=env,
    )
    audit = _redact_source_path(audit_raw, source)
    audit["deterministic_no_llm"] = True
    audit["audit_cli_exit_code"] = audit_completed.returncode
    audit["capability_boundary"] = {
        "sarif": "not emitted by the current audit CLI",
        "baseline": "not implemented by the current audit CLI",
        "exit_policy": "current CLI exit code is recorded, not interpreted as a fail-on policy",
    }
    audit.update(evidence_metadata())
    _write_json(pack_dir / "audit.json", audit)
    (pack_dir / "audit.stderr.log").write_text(audit_completed.stderr, encoding="utf-8")

    verification, verify_log, recheck_log = run_reference_verification(
        reference=reference,
        pack_dir=pack_dir,
        workspace=workspace,
        mumei_bin=mumei_bin,
        env=env,
    )
    _write_json(pack_dir / "verification.json", verification)
    (pack_dir / "reference-verify.log").write_text(verify_log, encoding="utf-8")
    (pack_dir / "reference-verify-cert.log").write_text(recheck_log, encoding="utf-8")

    plan = migration_plan(audit)
    if not any(entry["function_name"] == "divide" and entry["priority"] == "high" for entry in plan["entries"]):
        raise EvidencePackError("division fixture did not produce the expected high-priority migration candidate")
    _write_json(pack_dir / "migration_plan.json", plan)
    shutil.copyfile(workflow_template, pack_dir / "github-actions-mumei-audit.yml")
    write_summary(pack_dir / "summary.md", audit, plan, verification)

    pack_artifact_paths = [pack_dir / path for path in ARTIFACT_PATHS]
    manifest = {
        "schema": PACK_SCHEMA,
        "mode": {
            "audit": "deterministic_no_llm",
            "fixture": "reference_source",
            "llm_credentials": "explicitly_empty_for_audit_child",
        },
        "inputs": {
            "source": {"path": "src/ledger.py", "sha256": _sha256(source)},
            "reference_contract": {"path": "reference/safe_divide.mm", "sha256": _sha256(reference)},
            "workflow_template": {"path": "reference/workflows/mumei-audit.yml", "sha256": _sha256(workflow_template)},
        },
        "artifacts": _artifact_rows(pack_artifact_paths, pack_dir),
        "artifact_paths": list(ARTIFACT_PATHS),
        "artifact_roles": artifact_roles(),
        "evidence_boundary_by_role": dict(EVIDENCE_BOUNDARIES),
        "evidence_roles": {
            role: {
                "paths": list(paths),
                "status": "absent" if not paths else "present",
                "boundary": EVIDENCE_BOUNDARIES[role],
            }
            for role, paths in ARTIFACT_ROLES.items()
        },
        "sarif": {
            "path": "audit.sarif",
            "status": "not_available_in_current_cli",
            "required": False,
            "boundary": "The demo does not fabricate SARIF; upload is conditional in the workflow for the future audit CLI contract.",
        },
        "evidence_boundary": [
            "audit.json is existing-code audit evidence, not a proof certificate.",
            "migration_plan.json is a human-review plan, not evidence of completed migration.",
            "reference.proof.json proves only the reviewed reference .mm contract.",
            "No native bundle is present or implied by this pack.",
            "No adapter observation is present or implied by this pack.",
            "No artifact in this pack establishes Python/.mm semantic equivalence.",
        ],
    }
    _write_json(pack_dir / "manifest.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mumei-agent-repo", type=Path, required=True)
    parser.add_argument("--mumei-agent-python", type=Path, required=True)
    parser.add_argument("--mumei-bin", type=Path, required=True)
    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        manifest = build_evidence_pack(
            scenario_dir=args.scenario_dir.resolve(),
            output_dir=args.output_dir.resolve(),
            agent_repo=args.mumei_agent_repo.resolve(),
            # Make the interpreter path absolute without resolving symlinks:
            # resolving a venv Python yields the base interpreter and loses
            # the venv's site-packages, while a relative path would otherwise
            # be re-interpreted from the agent repository working directory.
            agent_python=args.mumei_agent_python.expanduser().absolute(),
            mumei_bin=args.mumei_bin.expanduser().resolve(),
        )
    except (EvidencePackError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"ci evidence pack failed: {exc}", file=sys.stderr)
        return 1
    print(f"evidence pack schema: {manifest['schema']}")
    print(f"evidence pack artifacts: {len(manifest['artifacts'])}")
    print("deterministic audit mode: no LLM credentials")
    print("sarif status: not_available_in_current_cli")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
