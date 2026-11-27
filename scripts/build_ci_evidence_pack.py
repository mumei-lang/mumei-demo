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
import re
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

PACK_SCHEMA = "mumei-demo.ci-evidence-pack/v2"
MIGRATION_EXECUTION_SCHEMA = "mumei.migration-execution/v1"
MIGRATION_PLAN_SCHEMA = "mumei-demo.migration-plan/v1"

ARTIFACT_PATHS = (
    "audit.json",
    "audit.stderr.log",
    "audit.sarif",
    "audit-baseline.json",
    "migration_plan.json",
    "migration_execution.json",
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
    "migration_execution": ["migration_execution.json"],
    "proof_certificate": ["reference.proof.json"],
    "ci_policy": ["audit-baseline.json"],
    "native_bundle": [],
    "adapter_observation": [],
}
EVIDENCE_BOUNDARIES = {
    "audit_report": "Existing-code audit evidence and its SARIF rendering; not a proof certificate.",
    "migration_plan": "Human-review migration scaffold; not evidence of completed migration.",
    "migration_execution": "Upstream generated-.mm migration execution acceptance evidence; not host-code semantic equivalence proof.",
    "proof_certificate": "Proof only for the reviewed reference .mm contract; not host-code equivalence.",
    "ci_policy": "CI suppression and fail-on policy only; not evidence and not part of proof acceptance.",
    "native_bundle": "No native bundle is present or implied by this audit/migration evidence pack.",
    "adapter_observation": "No adapter observation is present or implied by this audit/migration evidence pack.",
}
BASELINE_INPUT = "reference/audit-baseline.json"
BASELINE_SCHEMA = "mumei.audit-baseline/v1"
FAIL_ON_POLICY = "high-confidence"


def pack_artifact_paths(include_migration_execution: bool) -> list[str]:
    paths = list(ARTIFACT_PATHS)
    if not include_migration_execution:
        paths.remove("migration_execution.json")
    return paths


def artifact_roles(include_migration_execution: bool = True) -> dict[str, list[str]]:
    roles = {role: list(paths) for role, paths in ARTIFACT_ROLES.items()}
    if not include_migration_execution:
        roles["migration_execution"] = []
    return roles


def evidence_metadata(include_migration_execution: bool = True) -> dict[str, Any]:
    return {
        "artifact_paths": pack_artifact_paths(include_migration_execution),
        "artifact_roles": artifact_roles(include_migration_execution),
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


def migration_execution_supported(*, agent_repo: Path, agent_python: Path, env: dict[str, str]) -> bool:
    completed = _run([str(agent_python), "-m", "agent", "audit", "--help"], cwd=agent_repo, env=env)
    return completed.returncode == 0 and "--migration-execution-output" in completed.stdout + completed.stderr


def _validate_migration_execution(path: Path, *, validate_output_path: bool = True) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidencePackError(f"migration execution output is not valid JSON: {path}") from exc
    required = {"schema", "generated_at", "source", "audit", "selection", "candidates", "operational_errors", "artifact_paths", "evidence_boundary", "summary"}
    if not isinstance(payload, dict) or payload.get("schema") != MIGRATION_EXECUTION_SCHEMA or required - set(payload):
        raise EvidencePackError("migration execution output does not use the required mumei.migration-execution/v1 shape")
    candidates, summary = payload.get("candidates"), payload.get("summary")
    if not isinstance(candidates, list) or not isinstance(summary, dict):
        raise EvidencePackError("migration execution candidates or summary are malformed")
    source, selection = payload.get("source"), payload.get("selection")
    if (
        not isinstance(source, dict)
        or {"path", "language", "kind", "sha256"} - set(source)
        or source.get("kind") not in {"file", "directory"}
        or not isinstance(source.get("path"), str)
        or not isinstance(source.get("language"), str)
        or not isinstance(source.get("sha256"), (str, type(None)))
    ):
        raise EvidencePackError("migration execution source provenance is malformed")
    if (
        not isinstance(selection, dict)
        or {"basis", "requested_functions", "missing_requested_functions"} - set(selection)
        or not isinstance(selection.get("requested_functions"), list)
        or not isinstance(selection.get("missing_requested_functions"), list)
        or not all(isinstance(item, str) for item in selection.get("requested_functions", []))
        or not all(isinstance(item, str) for item in selection.get("missing_requested_functions", []))
    ):
        raise EvidencePackError("migration execution selection metadata is malformed")
    states = {"not_attempted", "blocked", "operational_error", "ready_for_human_review"}
    candidate_required = {
        "function_name", "source_provenance", "selection", "extracted_contract", "generated_mm",
        "heal", "verification", "unbound_audit_diagnostics", "contract_provenance",
        "evidence_blockers", "operational_errors", "review_required", "execution_state",
    }
    if any(
        not isinstance(row, dict)
        or candidate_required - set(row)
        or row.get("execution_state") not in states
        or not isinstance(row.get("review_required"), bool)
        for row in candidates
    ):
        raise EvidencePackError("migration execution candidate contract is malformed")
    counts = {
        "candidate_count": len(candidates),
        "ready_for_human_review": sum(row.get("execution_state") == "ready_for_human_review" for row in candidates),
        "blocked": sum(row.get("execution_state") == "blocked" for row in candidates),
        "operational_error": sum(row.get("execution_state") == "operational_error" for row in candidates),
    }
    if any(summary.get(key) != value for key, value in counts.items()):
        raise EvidencePackError("migration execution summary does not match candidate execution states")
    if summary.get("review_required") is not bool(candidates or selection["missing_requested_functions"]):
        raise EvidencePackError("migration execution summary review_required is inconsistent")
    if not isinstance(payload.get("operational_errors"), list):
        raise EvidencePackError("migration execution operational errors are malformed")
    artifact_paths = payload.get("artifact_paths")
    if (not isinstance(artifact_paths, dict)
            or not isinstance(artifact_paths.get("migration_execution"), str)
            or not isinstance(artifact_paths.get("generated_artifacts"), str)):
        raise EvidencePackError("migration execution artifact paths are malformed")
    if validate_output_path:
        recorded_output = Path(artifact_paths["migration_execution"])
        recorded_output = recorded_output if recorded_output.is_absolute() else path.parent / recorded_output
        if recorded_output.resolve() != path.resolve():
            raise EvidencePackError("migration execution artifact path does not match the audit output file")
    evidence_boundary = payload.get("evidence_boundary")
    if not isinstance(evidence_boundary, list) or not all(isinstance(item, str) for item in evidence_boundary):
        raise EvidencePackError("migration execution evidence boundary is malformed")
    boundary = "\n".join(evidence_boundary)
    if "not proof that host-language code implements the same behavior" not in boundary:
        raise EvidencePackError("migration execution evidence boundary does not exclude host semantic equivalence")
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


def _migration_generated_dir(payload: dict[str, Any], output_path: Path) -> Path:
    generated_value = Path(payload["artifact_paths"]["generated_artifacts"])
    raw_dir = generated_value if generated_value.is_absolute() else output_path.parent / generated_value
    output_parent = output_path.parent.resolve()
    probe = raw_dir
    while probe != output_parent and output_parent in probe.parents:
        if probe.is_symlink():
            raise EvidencePackError("migration execution generated artifact directory contains a symlink component")
        probe = probe.parent
    generated_dir = raw_dir.resolve()
    if not generated_dir.is_relative_to(output_parent):
        raise EvidencePackError("migration execution generated artifact directory escapes the evidence pack")
    expected_base = output_parent / f"{output_path.stem}.migration-execution"
    if generated_dir.parent != output_parent or (
        generated_dir != expected_base
        and not re.fullmatch(re.escape(expected_base.name) + r"-\d+", generated_dir.name)
    ):
        raise EvidencePackError("migration execution generated artifact directory does not match the migration execution output")
    return generated_dir


def run_audit(
    *,
    source: Path,
    agent_repo: Path,
    agent_python: Path,
    mumei_bin: Path,
    baseline_input: Path,
    sarif_output: Path,
    write_baseline: Path,
    migration_execution_output: Path | None = None,
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
    if migration_execution_output is not None:
        command.extend(["--migration-execution-output", str(migration_execution_output)])
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
    if migration_execution_output is not None:
        if not migration_execution_output.exists():
            raise EvidencePackError("audit CLI did not write migration execution output")
        execution_payload = _validate_migration_execution(migration_execution_output)
        generated_dir = _migration_generated_dir(execution_payload, migration_execution_output)
        if not generated_dir.is_dir():
            raise EvidencePackError("audit CLI did not write the migration execution generated artifact directory")
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


def migration_plan(audit: dict[str, Any], include_migration_execution: bool = True) -> dict[str, Any]:
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
        **evidence_metadata(include_migration_execution),
        "entries": entries,
        "summary": {
            "candidate_count": len(entries),
            "high_priority_count": sum(entry["priority"] == "high" for entry in entries),
        },
    }


def _generated_artifact_files(root: Path) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        raise EvidencePackError("migration execution generated artifact directory is missing or is not a regular directory")
    root = root.resolve()
    files = []

    def raise_walk_error(error: OSError) -> None:
        raise EvidencePackError(f"migration execution generated artifact directory is not readable: {error.filename}") from error

    for current, dirnames, filenames in os.walk(root, onerror=raise_walk_error, followlinks=False):
        current_path = Path(current)
        for name in dirnames:
            path = current_path / name
            if path.is_symlink():
                raise EvidencePackError("migration execution generated artifact directory contains a symlink")
            if not path.resolve().is_relative_to(root):
                raise EvidencePackError("migration execution generated artifact directory contains an escaping directory")
        for name in filenames:
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                raise EvidencePackError("migration execution generated artifact directory contains a non-regular file")
            if not path.resolve().is_relative_to(root):
                raise EvidencePackError("migration execution generated artifact directory contains an escaping file")
            files.append(path)
    return sorted(files)


def _artifact_rows(paths: list[Path], pack_dir: Path, *, include_bytes: bool = False) -> list[dict[str, object]]:
    rows = []
    for path in paths:
        row: dict[str, object] = {
            "path": path.relative_to(pack_dir).as_posix(),
            "sha256": _sha256(path),
        }
        if include_bytes:
            row["bytes"] = path.stat().st_size
        rows.append(row)
    return rows


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _validate_migration_companion_rows(
    payload: dict[str, Any],
    generated_root: Path,
    pack_dir: Path,
    rows: list[dict[str, object]],
) -> None:
    rows_by_path = {str(row["path"]): row for row in rows}
    pack_root = pack_dir.resolve()
    generated_root = generated_root.resolve()
    claims: list[tuple[str, object, object]] = []
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        generated_mm = candidate.get("generated_mm") if isinstance(candidate.get("generated_mm"), dict) else {}
        mm_path = generated_mm.get("path")
        mm_sha = generated_mm.get("sha256")
        if mm_path is not None or mm_sha is not None:
            claims.append((f"candidates[{index}].generated_mm", mm_path, mm_sha))
        verification = candidate.get("verification") if isinstance(candidate.get("verification"), dict) else {}
        for key in ("proof_certificate", "sarif"):
            record = verification.get(key) if isinstance(verification.get(key), dict) else {}
            path = record.get("path")
            sha = record.get("sha256")
            written = record.get("written")
            if written is True or sha is not None:
                if written is not True:
                    raise EvidencePackError(f"migration execution {key} hash metadata is inconsistent")
                claims.append((f"candidates[{index}].verification.{key}", path, sha))

    for label, path_value, sha_value in claims:
        if not isinstance(path_value, str) or not path_value or not _valid_sha256(sha_value):
            raise EvidencePackError(f"migration execution {label} is missing a complete path and sha256")
        raw_path = Path(path_value)
        artifact_path = raw_path if raw_path.is_absolute() else pack_root / raw_path
        artifact_path = artifact_path.resolve(strict=False)
        if not artifact_path.is_relative_to(generated_root):
            raise EvidencePackError(f"migration execution {label} path is outside the generated artifact directory")
        if not artifact_path.is_relative_to(pack_root):
            raise EvidencePackError(f"migration execution {label} path is outside the evidence pack")
        pack_relative = artifact_path.relative_to(pack_root).as_posix()
        row = rows_by_path.get(pack_relative)
        if row is None:
            raise EvidencePackError(f"migration execution {label} path is missing from the companion hash manifest")
        if row["sha256"] != sha_value:
            raise EvidencePackError(f"migration execution {label} sha256 does not match the companion hash manifest")


def write_summary(path: Path, audit: dict[str, Any], plan: dict[str, Any], verification: dict[str, Any], migration_status: str = "not_available_in_current_cli") -> None:
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
        f"| Migration execution | `{migration_status}` |",
        f"| Reference `.mm` certificate | `{verification['proof_certificate']}` |",
        "",
        "## Artifact map",
        "",
        "- `audit.json`: normalized current-CLI audit JSON with fixed keys.",
        "- `audit.sarif`: SARIF emitted by the upstream audit CLI; the demo does not fabricate SARIF.",
        "- `audit-baseline.json`: refreshed finding-fingerprint baseline; CI policy only, not evidence.",
        "- `migration_plan.json`: prioritized human-review migration plan derived from `migration_hints`.",
        "- `migration_execution.json`: upstream-generated migration execution evidence when supported; never host semantic-equivalence proof.",
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
    output_dir = output_dir.resolve()
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

    audit_env = _audit_environment(os.environ if env is None else env, mumei_bin)
    migration_supported = migration_execution_supported(agent_repo=agent_repo, agent_python=agent_python, env=audit_env)
    migration_output = pack_dir / "migration_execution.json" if migration_supported else None
    audit_raw, audit_completed = run_audit(
        source=source,
        agent_repo=agent_repo,
        agent_python=agent_python,
        mumei_bin=mumei_bin,
        baseline_input=baseline_input,
        sarif_output=pack_dir / "audit.sarif",
        write_baseline=pack_dir / "audit-baseline.json",
        migration_execution_output=migration_output,
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
    audit.update(evidence_metadata(migration_supported))
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

    plan = migration_plan(audit, migration_supported)
    if not any(entry["function_name"] == "divide" and entry["priority"] == "high" for entry in plan["entries"]):
        raise EvidencePackError("division fixture did not produce the expected high-priority migration candidate")
    _write_json(pack_dir / "migration_plan.json", plan)
    shutil.copyfile(workflow_template, pack_dir / "github-actions-mumei-audit.yml")
    migration_status = "emitted_by_audit_cli" if migration_supported else "not_available_in_current_cli"
    write_summary(pack_dir / "summary.md", audit, plan, verification, migration_status)

    migration_generated_dir = None
    migration_generated_artifacts: list[dict[str, object]] = []
    if migration_output is not None:
        execution_payload = json.loads(migration_output.read_text(encoding="utf-8"))
        generated_root = _migration_generated_dir(execution_payload, migration_output)
        migration_generated_dir = generated_root.relative_to(pack_dir.resolve()).as_posix()
        migration_generated_artifacts = _artifact_rows(_generated_artifact_files(generated_root), pack_dir, include_bytes=True)
        _validate_migration_companion_rows(execution_payload, generated_root, pack_dir, migration_generated_artifacts)

    hashed_paths = [pack_dir / path for path in HASHED_ARTIFACT_PATHS if migration_supported or path != "migration_execution.json"]
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
        "artifacts": _artifact_rows(hashed_paths, pack_dir),
        "artifact_paths": pack_artifact_paths(migration_supported),
        "artifact_roles": artifact_roles(migration_supported),
        "evidence_boundary_by_role": dict(EVIDENCE_BOUNDARIES),
        "evidence_roles": {
            role: {
                "paths": list(paths),
                "status": "absent" if not paths else "present",
                "boundary": EVIDENCE_BOUNDARIES[role],
            }
            for role, paths in artifact_roles(migration_supported).items()
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
        "migration_execution": {
            "path": "migration_execution.json" if migration_supported else None,
            "schema": MIGRATION_EXECUTION_SCHEMA,
            "status": "emitted_by_audit_cli" if migration_supported else "not_available_in_current_cli",
            "generated_artifacts_dir": migration_generated_dir,
            "generated_artifacts": migration_generated_artifacts,
            "boundary": "Migration execution is upstream-generated acceptance evidence for generated .mm only; it is not host-code semantic equivalence proof, and partial artifacts are not completion evidence.",
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
            "migration_execution.json is upstream generated-.mm acceptance evidence only, not host-code semantic equivalence proof or completion evidence when partial.",
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
    print(f"migration execution status: {manifest['migration_execution']['status']}")
    print(f"fail-on policy: {FAIL_ON_POLICY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
