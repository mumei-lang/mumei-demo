#!/usr/bin/env python3
"""Build the deterministic CI audit evidence-pack reference artifact.

The pack uses the upstream audit CLI contract for SARIF, baselines, and
fail-on policy.  SARIF is emitted only by `mumei-agent audit`; the demo never
fabricates it, and baseline artifacts are CI policy rather than evidence.
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
    "audit.sarif",
    "audit-baseline.json",
    "migration_plan.json",
    "verification.json",
    "reference.proof.json",
    "reference-verify.log",
    "reference-verify-cert.log",
    "github-actions-mumei-audit.yml",
    "summary.md",
    "manifest.json",
)
HASHED_ARTIFACT_PATHS = tuple(path for path in ARTIFACT_PATHS if path != "manifest.json")
ARTIFACT_ROLES = {
    "audit_report": ["audit.json", "audit.sarif"],
    "migration_plan": ["migration_plan.json"],
    "proof_certificate": ["reference.proof.json"],
    "ci_policy": ["audit-baseline.json"],
    "native_bundle": [],
    "adapter_observation": [],
}
EVIDENCE_BOUNDARIES = {
    "audit_report": "Existing-code audit evidence and its SARIF rendering; not a proof certificate.",
    "migration_plan": "Human-review migration scaffold; not evidence of completed migration.",
    "proof_certificate": "Proof only for the reviewed reference .mm contract; not host-code equivalence.",
    "ci_policy": "CI suppression and fail-on policy only; not evidence and not part of proof acceptance.",
    "native_bundle": "No native bundle is present or implied by this audit/migration evidence pack.",
    "adapter_observation": "No adapter observation is present or implied by this audit/migration evidence pack.",
}
BASELINE_INPUT = "reference/audit-baseline.json"
BASELINE_SCHEMA = "mumei.audit-baseline/v1"
FAIL_ON_POLICY = "high-confidence"


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


def _validate_sarif(path: Path, *, require_baseline_state: bool = False) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidencePackError(f"audit SARIF output is not valid JSON: {path}") from exc
    runs = payload.get("runs") if isinstance(payload, dict) else None
    if payload.get("version") != "2.1.0" or not isinstance(runs, list) or not runs:
        raise EvidencePackError("audit SARIF output does not have the expected SARIF 2.1.0 shape")
    if require_baseline_state:
        results = [
            row
            for run in runs
            if isinstance(run, dict)
            for row in (run.get("results") or [])
            if isinstance(row, dict)
        ]
        if any(row.get("baselineState") not in {"new", "unchanged"} for row in results):
            raise EvidencePackError("audit SARIF results do not reflect the --baseline policy overlay")


def _validate_baseline_annotations(audit: dict[str, Any]) -> None:
    rows = audit.get("findings")
    if isinstance(rows, list) and any(isinstance(row, dict) and "baseline" not in row for row in rows):
        raise EvidencePackError("audit JSON findings do not reflect the --baseline policy overlay")


def _validate_baseline(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidencePackError(f"audit baseline output is not valid JSON: {path}") from exc
    fingerprints = payload.get("fingerprints") if isinstance(payload, dict) else None
    if payload.get("version") != BASELINE_SCHEMA or not isinstance(fingerprints, list):
        raise EvidencePackError("audit baseline output does not use mumei.audit-baseline/v1")
    if not all(type(item) is str and item for item in fingerprints):
        raise EvidencePackError("audit baseline fingerprints must be non-empty strings")


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
    baseline_input: Path,
    sarif_output: Path,
    write_baseline: Path,
    fail_on: str = FAIL_ON_POLICY,
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
        "--sarif-output",
        str(sarif_output),
        "--baseline",
        str(baseline_input),
        "--write-baseline",
        str(write_baseline),
        "--fail-on",
        fail_on,
    ]
    completed = _run(
        command,
        cwd=agent_repo,
        env=_audit_environment(os.environ if env is None else env, mumei_bin),
    )
    payload = _load_audit_json(completed)
    if completed.returncode == 2:
        raise EvidencePackError("audit failed operationally with exit 2")
    if completed.returncode not in (0, 1):
        raise EvidencePackError(f"audit exited with unsupported status {completed.returncode}")
    if not sarif_output.exists():
        raise EvidencePackError("audit CLI did not write SARIF output")
    if not write_baseline.exists():
        raise EvidencePackError("audit CLI did not write baseline output")
    _validate_sarif(sarif_output, require_baseline_state=True)
    _validate_baseline(write_baseline)
    _validate_baseline_annotations(payload)
    return payload, completed


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
    rows = audit.get("findings") if isinstance(audit.get("findings"), list) else []
    suppressed = sum(isinstance(row, dict) and row.get("baseline") == "suppressed" for row in rows)
    new = sum(isinstance(row, dict) and row.get("baseline") == "new" for row in rows)
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
        f"| Audit exit code | {audit.get('audit_cli_exit_code', 'not recorded')} |",
        f"| Fail-on policy | `{audit.get('audit_cli_contract', {}).get('fail_on', 'not recorded')}` |",
        f"| Code findings | {findings.get('code', 'not reported')} |",
        f"| Spec/model findings | {findings.get('spec', 'not reported')} |",
        f"| Baseline states | {suppressed} suppressed, {new} new |",
        f"| Migration candidates | {plan['summary']['candidate_count']} |",
        f"| Reference `.mm` certificate | `{verification['proof_certificate']}` |",
        "",
        "## Artifact map",
        "",
        "- `audit.json`: normalized current-CLI audit JSON with fixed keys.",
        "- `audit.sarif`: SARIF emitted by the upstream audit CLI; the demo does not fabricate SARIF.",
        "- `audit-baseline.json`: refreshed finding-fingerprint baseline; CI policy only, not evidence.",
        "- `migration_plan.json`: prioritized human-review migration plan derived from `migration_hints`.",
        "- `reference.proof.json`: proof certificate for the reviewed reference `.mm` contract only.",
        "- `github-actions-mumei-audit.yml`: copyable reference workflow.",
        "",
        "## Evidence boundary",
        "",
        "The audit report and SARIF rendering identify review and migration work. The reference certificate proves the standalone `.mm` contract. Neither artifact yet proves semantic equivalence between the Python implementation and the `.mm` contract.",
        "",
        "`audit-baseline.json` is a `ci_policy` artifact: it suppresses reviewed findings for CI policy decisions and must not be treated as audit evidence or proof acceptance. `native_bundle` and `adapter_observation` are empty roles in `artifact_roles`; neither audit findings nor migration scaffolds may be relabeled as those evidence classes.",
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
    baseline_input = scenario_dir / BASELINE_INPUT
    for required in (source, reference, workflow_template, baseline_input, agent_python, mumei_bin):
        if not required.exists():
            raise EvidencePackError(f"required input is missing: {required}")
    _validate_baseline(baseline_input)

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
        baseline_input=baseline_input,
        sarif_output=pack_dir / "audit.sarif",
        write_baseline=pack_dir / "audit-baseline.json",
        env=env,
    )
    audit = _redact_source_path(audit_raw, source)
    audit["deterministic_no_llm"] = True
    audit["audit_cli_exit_code"] = audit_completed.returncode
    audit["audit_cli_contract"] = {
        "sarif_output": "audit.sarif",
        "baseline_input": BASELINE_INPUT,
        "baseline_output": "audit-baseline.json",
        "fail_on": FAIL_ON_POLICY,
        "exit_policy": "0/1 are finding-policy outcomes; 2 is an operational audit failure",
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

    pack_artifact_paths = [pack_dir / path for path in HASHED_ARTIFACT_PATHS]
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
            "audit_baseline_input": {"path": BASELINE_INPUT, "sha256": _sha256(baseline_input)},
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
            "status": "emitted_by_audit_cli",
            "required": True,
            "boundary": "SARIF is emitted by the upstream audit CLI as a rendering of audit findings; the demo does not fabricate it.",
        },
        "baseline": {
            "input_path": BASELINE_INPUT,
            "output_path": "audit-baseline.json",
            "status": "emitted_by_audit_cli",
            "role": "ci_policy",
            "boundary": "Baseline suppression is CI policy only; it is not evidence and must not participate in proof acceptance.",
        },
        "fail_on": {
            "policy": FAIL_ON_POLICY,
            "audit_exit_code": audit_completed.returncode,
            "boundary": "Fail-on is a CI policy outcome over non-suppressed findings, not a verdict or proof boundary change.",
        },
        "evidence_boundary": [
            "audit.json is existing-code audit evidence, not a proof certificate.",
            "audit.sarif is the audit CLI's SARIF rendering of audit findings, not independent evidence.",
            "audit-baseline.json is CI suppression policy, not evidence or proof acceptance.",
            "migration_plan.json is a human-review plan, not evidence of completed migration.",
            "reference.proof.json proves only the reviewed reference .mm contract.",
            "No native bundle is present or implied by this pack.",
            "No adapter observation is present or implied by this pack.",
            "No artifact in this pack establishes Python/.mm semantic equivalence.",
        ],
    }
    _write_json(pack_dir / "manifest.json", manifest)
    if audit_completed.returncode == 1:
        raise EvidencePackError(
            "audit fail-on policy reported non-suppressed high-confidence evidence; see the completed evidence pack"
        )
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
    print("sarif status: emitted_by_audit_cli")
    print("baseline status: emitted_by_audit_cli")
    print(f"fail-on policy: {FAIL_ON_POLICY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
