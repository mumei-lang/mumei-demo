#!/usr/bin/env python3
"""Verify a copied or downloaded CI audit evidence pack.

The default mode is structural and hash verification only.  It does not claim
that proof certificates were independently rechecked unless `--mumei-bin` and
`--reference-contract` are supplied and `mumei verify-cert --strict` exits
successfully.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import build_ci_evidence_pack as pack  # noqa: E402


class EvidencePackVerificationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidencePackVerificationError(f"{label} is missing or is not valid JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise EvidencePackVerificationError(f"{label} must be a JSON object")
    return payload


def _pack_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidencePackVerificationError(f"{label} must be a non-empty pack-relative path")
    if value.startswith("/") or value.endswith("/") or "//" in value or "\\" in value:
        raise EvidencePackVerificationError(f"{label} is not a safe pack-relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise EvidencePackVerificationError(f"{label} contains path traversal or non-canonical segments")
    return value


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _valid_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _scan_regular_files(root: Path) -> list[str]:
    if root.is_symlink() or not root.is_dir():
        raise EvidencePackVerificationError("evidence pack directory is missing or is not a regular directory")
    root = root.resolve()
    files: list[str] = []

    def raise_walk_error(error: OSError) -> None:
        raise EvidencePackVerificationError(f"evidence pack is not readable: {error.filename}") from error

    for current, dirnames, filenames in os.walk(root, onerror=raise_walk_error, followlinks=False):
        current_path = Path(current)
        for name in dirnames:
            path = current_path / name
            if path.is_symlink():
                raise EvidencePackVerificationError(f"evidence pack contains a symlinked directory: {path.relative_to(root).as_posix()}")
            if not path.resolve().is_relative_to(root):
                raise EvidencePackVerificationError("evidence pack contains an escaping directory")
        for name in filenames:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.is_file():
                raise EvidencePackVerificationError(f"evidence pack contains a symlink or non-regular file: {relative}")
            if not path.resolve().is_relative_to(root):
                raise EvidencePackVerificationError("evidence pack contains an escaping file")
            files.append(relative)
    return sorted(files)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise EvidencePackVerificationError(message)


def _exact_keys(row: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) != keys:
        raise EvidencePackVerificationError(f"{label} has a malformed row shape")
    return row


def _validate_canonical_manifest(manifest: dict[str, Any], include_migration: bool) -> None:
    expected_paths = pack.pack_artifact_paths(include_migration)
    _expect(manifest.get("artifact_paths") == expected_paths, "canonical artifact_paths do not match schema v2")
    inputs = manifest.get("inputs")
    _expect(isinstance(inputs, dict), "manifest inputs are malformed")
    expected_inputs = {
        "source": "src/ledger.py",
        "reference_contract": "reference/safe_divide.mm",
        "workflow_template": "reference/workflows/mumei-audit.yml",
        "audit_baseline_input": pack.BASELINE_INPUT,
    }
    _expect(set(inputs) == set(expected_inputs), "manifest inputs do not match schema v2")
    for key, expected_path in expected_inputs.items():
        row = inputs.get(key)
        _expect(isinstance(row, dict) and set(row) == {"path", "sha256"}, f"manifest input {key} is malformed")
        _expect(row.get("path") == expected_path, f"manifest input {key} path is inconsistent")
        _expect(_valid_sha256(row.get("sha256")), f"manifest input {key} sha256 is malformed")
    _expect(manifest.get("artifact_roles") == pack.artifact_roles(include_migration), "artifact_roles do not match the closed schema v2 role map")
    _expect(manifest.get("evidence_boundary_by_role") == pack.EVIDENCE_BOUNDARIES, "evidence boundaries do not match schema v2")
    roles = manifest.get("evidence_roles")
    expected_roles = pack.artifact_roles(include_migration)
    _expect(isinstance(roles, dict), "evidence_roles is malformed")
    _expect(set(roles) == set(expected_roles), "evidence_roles do not match the closed schema v2 role map")
    for role, paths in expected_roles.items():
        row = roles.get(role) if isinstance(roles, dict) else None
        _expect(isinstance(row, dict), f"evidence role {role} is missing")
        _expect(row.get("paths") == paths, f"evidence role {role} paths are inconsistent")
        _expect(row.get("status") == ("present" if paths else "absent"), f"evidence role {role} status is inconsistent")
        _expect(row.get("boundary") == pack.EVIDENCE_BOUNDARIES[role], f"evidence role {role} boundary is inconsistent")


def _validate_top_level_artifacts(root: Path, manifest: dict[str, Any], include_migration: bool) -> list[str]:
    rows = manifest.get("artifacts")
    _expect(isinstance(rows, list), "manifest artifacts must be a list")
    expected = [path for path in pack.HASHED_ARTIFACT_PATHS if include_migration or path != "migration_execution.json"]
    _expect(len(rows) == len(expected), "manifest has missing or extra canonical artifact hash rows")
    seen: set[str] = set()
    for index, (row_value, expected_path) in enumerate(zip(rows, expected, strict=True)):
        row = _exact_keys(row_value, {"path", "sha256"}, f"manifest.artifacts[{index}]")
        path = _pack_relative_path(row["path"], f"manifest.artifacts[{index}].path")
        _expect(path == expected_path, "canonical artifact hash rows are not in the schema v2 order")
        _expect(path not in seen, f"duplicate canonical artifact path: {path}")
        seen.add(path)
        _expect(_valid_sha256(row["sha256"]), f"canonical artifact {path} has a malformed sha256")
        artifact = root / path
        if not artifact.is_file() or artifact.is_symlink():
            raise EvidencePackVerificationError(f"canonical artifact is missing or is not a regular file: {path}")
        if _sha256(artifact) != row["sha256"]:
            raise EvidencePackVerificationError(f"canonical artifact sha256 mismatch: {path}")
    return list(manifest["artifact_paths"])


def _generated_dir_name(value: str) -> None:
    base = "migration_execution.migration-execution"
    _expect(
        value == base or re.fullmatch(re.escape(base) + r"-\d+", value) is not None,
        "migration generated artifact directory is not bound to migration_execution.json",
    )


def _companion_rows(manifest: dict[str, Any], include_migration: bool) -> list[dict[str, Any]]:
    section = manifest.get("migration_execution")
    _expect(isinstance(section, dict), "manifest migration_execution section is malformed")
    _expect(section.get("schema") == pack.MIGRATION_EXECUTION_SCHEMA, "migration execution schema is inconsistent")
    expected_status = "emitted_by_audit_cli" if include_migration else "not_available_in_current_cli"
    _expect(section.get("status") == expected_status, "migration execution status is inconsistent")
    boundary = section.get("boundary")
    _expect(isinstance(boundary, str), "migration execution boundary is malformed")
    _expect("not host-code semantic equivalence proof" in boundary, "migration execution boundary does not exclude host semantic equivalence")
    _expect("partial artifacts are not completion evidence" in boundary, "migration execution boundary does not exclude partial completion evidence")
    if not include_migration:
        _expect(section.get("path") is None, "unsupported migration execution must not claim an artifact path")
        _expect(section.get("generated_artifacts_dir") is None, "unsupported migration execution must not claim a generated directory")
        _expect(section.get("generated_artifacts") == [], "unsupported migration execution must not fabricate companion rows")
        return []

    _expect(section.get("path") == "migration_execution.json", "migration execution path is inconsistent")
    generated_dir = _pack_relative_path(section.get("generated_artifacts_dir"), "migration_execution.generated_artifacts_dir")
    _generated_dir_name(generated_dir)
    rows = section.get("generated_artifacts")
    _expect(isinstance(rows, list), "migration companion rows must be a list")
    validated = []
    seen: set[str] = set()
    prefix = generated_dir + "/"
    for index, row_value in enumerate(rows):
        row = _exact_keys(row_value, {"path", "sha256", "bytes"}, f"migration_execution.generated_artifacts[{index}]")
        path = _pack_relative_path(row["path"], f"migration_execution.generated_artifacts[{index}].path")
        _expect(path.startswith(prefix), f"migration companion row is outside the generated artifact directory: {path}")
        _expect(path not in seen, f"duplicate migration companion path: {path}")
        seen.add(path)
        _expect(_valid_sha256(row["sha256"]), f"migration companion row has a malformed sha256: {path}")
        _expect(_valid_nonnegative_int(row["bytes"]), f"migration companion row has malformed byte metadata: {path}")
        validated.append(row)
    return validated


def _validate_companion_files(root: Path, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        path = row["path"]
        artifact = root / path
        if not artifact.is_file() or artifact.is_symlink():
            raise EvidencePackVerificationError(f"migration companion artifact is missing or is not a regular file: {path}")
        if _sha256(artifact) != row["sha256"]:
            raise EvidencePackVerificationError(f"migration companion artifact sha256 mismatch: {path}")
        if artifact.stat().st_size != row["bytes"]:
            raise EvidencePackVerificationError(f"migration companion artifact bytes mismatch: {path}")


def _normalized_absolute(path_text: str) -> Path:
    return Path(os.path.normpath(path_text))


def _map_claimed_path(path_text: str, *, pack_root: Path, generated_root: Path, original_generated_root_text: str) -> Path:
    raw = Path(path_text)
    if raw.is_absolute():
        original_generated_root = Path(original_generated_root_text)
        if not original_generated_root.is_absolute():
            raise EvidencePackVerificationError("migration execution mixes absolute artifact claims with a relative generated directory")
        normalized_root = _normalized_absolute(str(original_generated_root))
        normalized_claim = _normalized_absolute(path_text)
        try:
            suffix = normalized_claim.relative_to(normalized_root)
        except ValueError as exc:
            raise EvidencePackVerificationError("migration execution artifact claim is outside the generated artifact directory") from exc
        return generated_root / suffix
    return (pack_root / raw).resolve(strict=False)


def _validate_upstream_generated_root_binding(original_generated_root_text: str, generated_dir: str) -> None:
    normalized = os.path.normpath(original_generated_root_text)
    basename = Path(normalized).name
    _generated_dir_name(basename)
    if Path(original_generated_root_text).is_absolute():
        if basename != generated_dir:
            raise EvidencePackVerificationError("upstream generated artifact directory basename is inconsistent with the manifest")
    elif normalized != generated_dir:
        raise EvidencePackVerificationError("relative upstream generated artifact directory is inconsistent with the manifest")


def _validate_migration_claims(root: Path, rows: list[dict[str, Any]], generated_dir: str) -> None:
    execution_path = root / "migration_execution.json"
    payload = pack._validate_migration_execution(execution_path, validate_output_path=False)
    rows_by_path = {row["path"]: row for row in rows}
    pack_root = root.resolve()
    generated_root = (pack_root / generated_dir).resolve(strict=False)
    original_generated_root_text = payload["artifact_paths"]["generated_artifacts"]
    _validate_upstream_generated_root_binding(original_generated_root_text, generated_dir)
    claims: list[tuple[str, object, object]] = []
    for index, candidate in enumerate(payload.get("candidates", [])):
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
                    raise EvidencePackVerificationError(f"migration execution {key} hash metadata is inconsistent")
                claims.append((f"candidates[{index}].verification.{key}", path, sha))

    for label, path_value, sha_value in claims:
        if not isinstance(path_value, str) or not path_value or not _valid_sha256(sha_value):
            raise EvidencePackVerificationError(f"migration execution {label} is missing a complete path and sha256")
        artifact_path = _map_claimed_path(
            path_value,
            pack_root=pack_root,
            generated_root=generated_root,
            original_generated_root_text=original_generated_root_text,
        ).resolve(strict=False)
        if not artifact_path.is_relative_to(generated_root):
            raise EvidencePackVerificationError(f"migration execution {label} path is outside the generated artifact directory")
        if not artifact_path.is_relative_to(pack_root):
            raise EvidencePackVerificationError(f"migration execution {label} path is outside the evidence pack")
        pack_relative = artifact_path.relative_to(pack_root).as_posix()
        row = rows_by_path.get(pack_relative)
        if row is None:
            raise EvidencePackVerificationError(f"migration execution {label} path is missing from the companion hash manifest")
        if row["sha256"] != sha_value:
            raise EvidencePackVerificationError(f"migration execution {label} sha256 does not match the companion hash manifest")


def _validate_closed_world(actual_files: list[str], canonical_paths: list[str], companion_rows: list[dict[str, Any]]) -> None:
    expected = sorted(set(canonical_paths) | {row["path"] for row in companion_rows})
    actual = sorted(actual_files)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        details = []
        if missing:
            details.append("missing files: " + ", ".join(missing[:5]))
        if extra:
            details.append("undeclared files: " + ", ".join(extra[:5]))
        raise EvidencePackVerificationError("evidence pack file set does not match the manifest (" + "; ".join(details) + ")")


def _validate_structural_artifacts(root: Path, manifest: dict[str, Any]) -> None:
    audit = _load_json(root / "audit.json", "audit report")
    missing = [key for key in pack.FIXED_AUDIT_KEYS if key not in audit]
    _expect(not missing, "audit report is missing fixed contract keys: " + ", ".join(missing))
    _expect(audit.get("artifact_paths") == manifest["artifact_paths"], "audit report artifact_paths diverge from the manifest")
    _expect(audit.get("artifact_roles") == manifest["artifact_roles"], "audit report artifact_roles diverge from the manifest")
    _expect(audit.get("evidence_boundary_by_role") == manifest["evidence_boundary_by_role"], "audit report evidence boundaries diverge from the manifest")

    pack._validate_sarif(root / "audit.sarif", require_baseline_state=True)
    pack._validate_baseline(root / "audit-baseline.json")

    sarif = manifest.get("sarif")
    _expect(isinstance(sarif, dict) and sarif.get("path") == "audit.sarif" and sarif.get("status") == "emitted_by_audit_cli", "SARIF provenance is inconsistent")
    _expect(sarif.get("required") is True, "SARIF provenance does not record the upstream artifact as required")
    baseline = manifest.get("baseline")
    _expect(isinstance(baseline, dict) and baseline.get("role") == "ci_policy", "baseline role is not ci_policy")
    _expect(baseline.get("status") == "emitted_by_audit_cli" and baseline.get("output_path") == "audit-baseline.json", "baseline provenance is inconsistent")
    _expect("not evidence" in str(baseline.get("boundary")), "baseline boundary does not exclude evidence use")
    fail_on = manifest.get("fail_on")
    _expect(isinstance(fail_on, dict) and fail_on.get("policy") == pack.FAIL_ON_POLICY, "fail-on policy is inconsistent")
    _expect(type(fail_on.get("audit_exit_code")) is int, "fail-on audit exit code is malformed")

    plan = _load_json(root / "migration_plan.json", "migration plan")
    _expect(plan.get("schema") == pack.MIGRATION_PLAN_SCHEMA, "migration plan schema is inconsistent")
    _expect(plan.get("artifact_paths") == manifest["artifact_paths"], "migration plan artifact_paths diverge from the manifest")
    _expect(plan.get("artifact_roles") == manifest["artifact_roles"], "migration plan artifact_roles diverge from the manifest")
    _expect(plan.get("evidence_boundary_by_role") == manifest["evidence_boundary_by_role"], "migration plan evidence boundaries diverge from the manifest")

    verification = _load_json(root / "verification.json", "reference verification metadata")
    _expect(verification.get("schema") == "mumei-demo.reference-verification/v1", "reference verification schema is inconsistent")
    _expect(verification.get("proof_certificate") == "reference.proof.json", "reference verification proof certificate path is inconsistent")
    _expect(verification.get("all_verified") is True, "reference verification does not record all_verified=true")
    certificate = _load_json(root / "reference.proof.json", "reference proof certificate")
    _expect(certificate.get("all_verified") is True, "reference proof certificate does not record all_verified=true")

    boundary_lines = manifest.get("evidence_boundary")
    _expect(isinstance(boundary_lines, list) and all(isinstance(item, str) for item in boundary_lines), "manifest evidence boundary is malformed")
    boundary = "\n".join(boundary_lines)
    _expect("not host-code semantic equivalence proof" in boundary, "pack boundary does not exclude host semantic equivalence")
    _expect("No artifact in this pack establishes Python/.mm semantic equivalence." in boundary, "pack boundary does not exclude Python/.mm semantic equivalence")


def _revalidate_reference_proof(root: Path, mumei_bin: Path | None, reference_contract: Path | None, expected_reference_sha256: str) -> str:
    if mumei_bin is None:
        return "not_requested"
    if reference_contract is None:
        raise EvidencePackVerificationError("--reference-contract is required when --mumei-bin is supplied")
    if mumei_bin.is_symlink() or not mumei_bin.is_file():
        raise EvidencePackVerificationError("--mumei-bin is not a regular file")
    if reference_contract.is_symlink() or not reference_contract.is_file():
        raise EvidencePackVerificationError("--reference-contract is not a regular file")
    if _sha256(reference_contract) != expected_reference_sha256:
        raise EvidencePackVerificationError("--reference-contract sha256 does not match the evidence pack input provenance")
    completed = subprocess.run(
        [str(mumei_bin), "verify-cert", "--strict", str(root / "reference.proof.json"), str(reference_contract)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = f": {detail[-1][:200]}" if detail else ""
        raise EvidencePackVerificationError("reference proof certificate revalidation failed" + suffix)
    return "performed"


def verify_evidence_pack(
    pack_dir: Path,
    *,
    mumei_bin: Path | None = None,
    reference_contract: Path | None = None,
) -> dict[str, Any]:
    root = pack_dir.resolve()
    try:
        actual_files = _scan_regular_files(root)
        manifest = _load_json(root / "manifest.json", "evidence pack manifest")
        _expect(manifest.get("schema") == pack.PACK_SCHEMA, "evidence pack schema is not mumei-demo.ci-evidence-pack/v2")
        migration_section = manifest.get("migration_execution") if isinstance(manifest.get("migration_execution"), dict) else {}
        status = migration_section.get("status")
        _expect(status in {"emitted_by_audit_cli", "not_available_in_current_cli"}, "migration execution status is malformed")
        include_migration = status == "emitted_by_audit_cli"
        if not include_migration and (root / "migration_execution.json").exists():
            raise EvidencePackVerificationError("unsupported migration execution must not fabricate migration_execution.json")

        _validate_canonical_manifest(manifest, include_migration)
        canonical_paths = _validate_top_level_artifacts(root, manifest, include_migration)
        companions = _companion_rows(manifest, include_migration)
        _validate_companion_files(root, companions)
        if include_migration:
            generated_dir = manifest["migration_execution"]["generated_artifacts_dir"]
            _validate_migration_claims(root, companions, generated_dir)
        _validate_closed_world(actual_files, canonical_paths, companions)
        _validate_structural_artifacts(root, manifest)
        proof_revalidation = _revalidate_reference_proof(
            root,
            mumei_bin,
            reference_contract,
            manifest["inputs"]["reference_contract"]["sha256"],
        )
    except pack.EvidencePackError as exc:
        raise EvidencePackVerificationError(str(exc)) from exc
    return {
        "schema": pack.PACK_SCHEMA,
        "migration_execution_status": status,
        "canonical_file_count": len(canonical_paths),
        "canonical_hash_row_count": len(manifest["artifacts"]),
        "companion_file_count": len(companions),
        "reference_proof_revalidation": proof_revalidation,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_dir", type=Path)
    parser.add_argument("--mumei-bin", type=Path)
    parser.add_argument("--reference-contract", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv or sys.argv[1:])
    if args.reference_contract is not None and args.mumei_bin is None:
        print("ci evidence pack verification failed: --reference-contract requires --mumei-bin", file=sys.stderr)
        return 1
    try:
        report = verify_evidence_pack(
            args.pack_dir,
            mumei_bin=args.mumei_bin.expanduser().resolve() if args.mumei_bin is not None else None,
            reference_contract=args.reference_contract.expanduser().resolve() if args.reference_contract is not None else None,
        )
    except (EvidencePackVerificationError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"ci evidence pack verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"evidence pack schema: {report['schema']}")
    print("structural/hash verification: passed")
    print(f"migration execution status: {report['migration_execution_status']}")
    print(f"canonical files verified: {report['canonical_file_count']}")
    print(f"canonical artifact hash rows verified: {report['canonical_hash_row_count']}")
    print(f"migration companion files verified: {report['companion_file_count']}")
    if report["reference_proof_revalidation"] == "performed":
        print("reference proof certificate revalidation: performed")
    else:
        print("reference proof certificate revalidation: not requested; structural/hash verification only")
    print("migration execution boundary: generated-.mm acceptance evidence only; not host semantic equivalence; partial artifacts are not completion evidence")
    print("baseline boundary: ci_policy only; not evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
