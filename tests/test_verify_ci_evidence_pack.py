from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import build_ci_evidence_pack as pack
from scripts import verify_ci_evidence_pack as verifier


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_execution(generated: Path) -> dict:
    mm = generated / "divide.mm"
    proof = generated / "divide.proof.json"
    sarif_dir = generated / "divide"
    sarif_dir.mkdir(parents=True, exist_ok=True)
    sarif = sarif_dir / "report.sarif"
    mm.write_text("atom divide\n", encoding="utf-8")
    proof.write_text('{"all_verified": true}\n', encoding="utf-8")
    sarif.write_text('{"version": "2.1.0"}\n', encoding="utf-8")
    cache = generated / ".mumei" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "verification_cache.json").write_text("{}\n", encoding="utf-8")
    return {
        "schema": pack.MIGRATION_EXECUTION_SCHEMA,
        "generated_at": "now",
        "source": {"path": "fixture/ledger.py", "language": "python", "kind": "file", "sha256": "0" * 64},
        "audit": {},
        "selection": {"basis": "all audit migration_hints candidates", "requested_functions": [], "missing_requested_functions": []},
        "candidates": [{
            "function_name": "divide", "source_provenance": {}, "selection": {},
            "extracted_contract": {},
            "generated_mm": {"path": str(mm), "sha256": _sha256_path(mm), "origin": "generated_skeleton", "healed_source_path": None},
            "heal": {},
            "verification": {
                "proof_certificate": {"path": str(proof), "sha256": _sha256_path(proof), "written": True},
                "sarif": {"path": str(sarif), "sha256": _sha256_path(sarif), "written": True},
            },
            "unbound_audit_diagnostics": {}, "contract_provenance": {},
            "evidence_blockers": [], "operational_errors": [], "review_required": True,
            "execution_state": "ready_for_human_review",
        }],
        "operational_errors": [],
        "artifact_paths": {
            "migration_execution": "migration_execution.json",
            "generated_artifacts": str(generated),
        },
        "evidence_boundary": ["A verified generated .mm skeleton proves only the skeleton contract as written; it is not proof that host-language code implements the same behavior."],
        "summary": {
            "candidate_count": 1,
            "ready_for_human_review": 1,
            "blocked": 0,
            "operational_error": 0,
            "review_required": True,
        },
    }


def write_valid_pack(root: Path, *, include_migration: bool = True, generated_dir_name: str = "migration_execution.migration-execution") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    metadata = pack.evidence_metadata(include_migration)
    audit = {key: [] for key in pack.FIXED_AUDIT_KEYS}
    audit.update({"verification_status": "unverifiable", "migration_hints": [{"function_name": "divide", "priority": "high"}], **metadata})
    _write_json(root / "audit.json", audit)
    (root / "audit.stderr.log").write_text("", encoding="utf-8")
    _write_json(root / "audit.sarif", {"version": "2.1.0", "runs": [{"results": []}]})
    _write_json(root / "audit-baseline.json", {"version": pack.BASELINE_SCHEMA, "fingerprints": []})
    plan = {
        "schema": pack.MIGRATION_PLAN_SCHEMA,
        "source": "fixture/ledger.py",
        "audit_verification_status": "unverifiable",
        "deterministic_mode": True,
        **metadata,
        "entries": [],
        "summary": {"candidate_count": 0, "high_priority_count": 0},
    }
    _write_json(root / "migration_plan.json", plan)
    verification = {
        "schema": "mumei-demo.reference-verification/v1",
        "reference_contract": "reference/safe_divide.mm",
        "proof_certificate": "reference.proof.json",
        "verify_exit_code": 0,
        "verify_cert_exit_code": 0,
        "all_verified": True,
        "atoms": [],
        "boundary": "reference only",
    }
    _write_json(root / "verification.json", verification)
    _write_json(root / "reference.proof.json", {"all_verified": True, "atoms": []})
    (root / "reference-verify.log").write_text("verify\n", encoding="utf-8")
    (root / "reference-verify-cert.log").write_text("verify-cert\n", encoding="utf-8")
    (root / "github-actions-mumei-audit.yml").write_text("name: audit\n", encoding="utf-8")
    (root / "summary.md").write_text("# summary\n", encoding="utf-8")

    generated_rows = []
    generated_dir = None
    if include_migration:
        generated_dir = generated_dir_name
        generated = root / generated_dir
        execution = _valid_execution(generated)
        _write_json(root / "migration_execution.json", execution)
        generated_rows = pack._artifact_rows(pack._generated_artifact_files(generated), root, include_bytes=True)

    hashed_paths = [path for path in pack.HASHED_ARTIFACT_PATHS if include_migration or path != "migration_execution.json"]
    artifacts = [{"path": path, "sha256": _sha256_path(root / path)} for path in hashed_paths]
    roles = pack.artifact_roles(include_migration)
    migration_boundary = "Migration execution is upstream-generated acceptance evidence for generated .mm only; it is not host-code semantic equivalence proof, and partial artifacts are not completion evidence."
    manifest = {
        "schema": pack.PACK_SCHEMA,
        "mode": {"audit": "deterministic_no_llm"},
        "inputs": {
            "source": {"path": "src/ledger.py", "sha256": "0" * 64},
            "reference_contract": {"path": "reference/safe_divide.mm", "sha256": "0" * 64},
            "workflow_template": {"path": "reference/workflows/mumei-audit.yml", "sha256": "0" * 64},
            "audit_baseline_input": {"path": pack.BASELINE_INPUT, "sha256": "0" * 64},
        },
        "artifacts": artifacts,
        "artifact_paths": pack.pack_artifact_paths(include_migration),
        "artifact_roles": roles,
        "evidence_boundary_by_role": dict(pack.EVIDENCE_BOUNDARIES),
        "evidence_roles": {
            role: {"paths": list(paths), "status": "absent" if not paths else "present", "boundary": pack.EVIDENCE_BOUNDARIES[role]}
            for role, paths in roles.items()
        },
        "sarif": {"path": "audit.sarif", "status": "emitted_by_audit_cli", "required": True, "boundary": "rendering"},
        "baseline": {
            "input_path": pack.BASELINE_INPUT,
            "output_path": "audit-baseline.json",
            "status": "emitted_by_audit_cli",
            "role": "ci_policy",
            "boundary": "Baseline suppression is CI policy only; it is not evidence and must not participate in proof acceptance.",
        },
        "migration_execution": {
            "path": "migration_execution.json" if include_migration else None,
            "schema": pack.MIGRATION_EXECUTION_SCHEMA,
            "status": "emitted_by_audit_cli" if include_migration else "not_available_in_current_cli",
            "generated_artifacts_dir": generated_dir,
            "generated_artifacts": generated_rows,
            "boundary": migration_boundary,
        },
        "fail_on": {"policy": pack.FAIL_ON_POLICY, "audit_exit_code": 0, "boundary": "policy"},
        "evidence_boundary": [
            "migration_execution.json is upstream generated-.mm acceptance evidence only, not host-code semantic equivalence proof or completion evidence when partial.",
            "No artifact in this pack establishes Python/.mm semantic equivalence.",
        ],
    }
    _write_json(root / "manifest.json", manifest)
    return root


def _manifest(root: Path) -> dict:
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(root: Path, manifest: dict) -> None:
    _write_json(root / "manifest.json", manifest)


def _refresh_migration_execution_hash(root: Path) -> None:
    manifest = _manifest(root)
    for row in manifest["artifacts"]:
        if row["path"] == "migration_execution.json":
            row["sha256"] = _sha256_path(root / "migration_execution.json")
    _write_manifest(root, manifest)


def _set_reference_input_hash(root: Path, reference: Path) -> None:
    manifest = _manifest(root)
    manifest["inputs"]["reference_contract"]["sha256"] = _sha256_path(reference)
    _write_manifest(root, manifest)


def test_verifier_accepts_supported_pack_with_hidden_companions_and_absolute_upstream_claims(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "downloaded-pack")

    report = verifier.verify_evidence_pack(root)

    assert report["migration_execution_status"] == "emitted_by_audit_cli"
    assert report["canonical_file_count"] == 13
    assert report["companion_file_count"] == 4
    assert report["reference_proof_revalidation"] == "not_requested"


def test_verifier_accepts_copy_after_original_upstream_paths_are_removed(tmp_path: Path) -> None:
    original = write_valid_pack(tmp_path / "original-pack")
    copied = tmp_path / "downloaded-pack"
    shutil.copytree(original, copied)
    shutil.rmtree(original)

    report = verifier.verify_evidence_pack(copied)

    assert report["migration_execution_status"] == "emitted_by_audit_cli"
    assert report["companion_file_count"] == 4


def test_verifier_accepts_numbered_generated_directory_binding(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack", generated_dir_name="migration_execution.migration-execution-1")

    report = verifier.verify_evidence_pack(root)

    assert report["companion_file_count"] == 4


def test_verifier_accepts_unsupported_pack_without_fabricated_migration_artifacts(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack", include_migration=False)

    report = verifier.verify_evidence_pack(root)

    assert report["migration_execution_status"] == "not_available_in_current_cli"
    assert report["canonical_file_count"] == 12
    assert report["companion_file_count"] == 0


def test_cli_output_does_not_claim_proof_revalidation_without_mumei_bin(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_valid_pack(tmp_path / "pack")

    assert verifier.main([str(root)]) == 0

    output = capsys.readouterr().out
    assert "structural/hash verification: passed" in output
    assert "reference proof certificate revalidation: not requested; structural/hash verification only" in output
    assert "not host semantic equivalence" in output
    assert "partial artifacts are not completion evidence" in output
    assert "baseline boundary: ci_policy only; not evidence" in output


def test_cli_rejects_reference_contract_without_mumei_bin(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_valid_pack(tmp_path / "pack")
    reference = tmp_path / "safe_divide.mm"
    reference.write_text("atom divide\n", encoding="utf-8")

    assert verifier.main([str(root), "--reference-contract", str(reference)]) == 1
    assert "requires --mumei-bin" in capsys.readouterr().err


def test_optional_reference_proof_revalidation_invokes_strict_verify_cert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = write_valid_pack(tmp_path / "pack")
    mumei = tmp_path / "mumei"
    mumei.write_text("", encoding="utf-8")
    reference = tmp_path / "safe_divide.mm"
    reference.write_text("atom divide\n", encoding="utf-8")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, "", "")

    _set_reference_input_hash(root, reference)
    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    report = verifier.verify_evidence_pack(root, mumei_bin=mumei, reference_contract=reference)

    assert report["reference_proof_revalidation"] == "performed"
    assert captured["command"][:3] == [str(mumei), "verify-cert", "--strict"]
    assert captured["command"][3] == str(root / "reference.proof.json")
    assert captured["command"][4] == str(reference)


def test_optional_reference_proof_revalidation_failure_is_operational(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = write_valid_pack(tmp_path / "pack")
    mumei = tmp_path / "mumei"
    mumei.write_text("", encoding="utf-8")
    reference = tmp_path / "safe_divide.mm"
    reference.write_text("atom divide\n", encoding="utf-8")
    _set_reference_input_hash(root, reference)
    monkeypatch.setattr(verifier.subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "certificate drift"))

    with pytest.raises(verifier.EvidencePackVerificationError, match="revalidation failed"):
        verifier.verify_evidence_pack(root, mumei_bin=mumei, reference_contract=reference)


def test_canonical_hash_mismatch_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    (root / "audit.json").write_text('{"tampered": true}\n', encoding="utf-8")

    with pytest.raises(verifier.EvidencePackVerificationError, match="canonical artifact sha256 mismatch: audit.json"):
        verifier.verify_evidence_pack(root)


def test_missing_canonical_artifact_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    (root / "audit.sarif").unlink()

    with pytest.raises(verifier.EvidencePackVerificationError, match="canonical artifact is missing"):
        verifier.verify_evidence_pack(root)


def test_extra_undeclared_file_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    (root / "unexpected.txt").write_text("extra\n", encoding="utf-8")

    with pytest.raises(verifier.EvidencePackVerificationError, match="undeclared files: unexpected.txt"):
        verifier.verify_evidence_pack(root)


def test_symlinked_file_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    target = tmp_path / "target.txt"
    target.write_text("target\n", encoding="utf-8")
    (root / "linked.txt").symlink_to(target)

    with pytest.raises(verifier.EvidencePackVerificationError, match="symlink or non-regular file"):
        verifier.verify_evidence_pack(root)


def test_symlinked_directory_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    target = tmp_path / "target-dir"
    target.mkdir()
    (root / "linked-dir").symlink_to(target, target_is_directory=True)

    with pytest.raises(verifier.EvidencePackVerificationError, match="symlinked directory"):
        verifier.verify_evidence_pack(root)


def test_missing_companion_file_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    (root / "migration_execution.migration-execution" / ".mumei" / "cache" / "verification_cache.json").unlink()

    with pytest.raises(verifier.EvidencePackVerificationError, match="migration companion artifact is missing"):
        verifier.verify_evidence_pack(root)


def test_companion_hidden_file_hash_mismatch_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    hidden = root / "migration_execution.migration-execution" / ".mumei" / "cache" / "verification_cache.json"
    hidden.write_text('{"tampered": true}\n', encoding="utf-8")

    with pytest.raises(verifier.EvidencePackVerificationError, match="migration companion artifact sha256 mismatch"):
        verifier.verify_evidence_pack(root)


def test_unbound_generated_directory_name_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    manifest = _manifest(root)
    manifest["migration_execution"]["generated_artifacts_dir"] = "unrelated-generated"
    _write_manifest(root, manifest)

    with pytest.raises(verifier.EvidencePackVerificationError, match="not bound to migration_execution"):
        verifier.verify_evidence_pack(root)


def test_companion_bytes_mismatch_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    manifest = _manifest(root)
    manifest["migration_execution"]["generated_artifacts"][0]["bytes"] += 1
    _write_manifest(root, manifest)

    with pytest.raises(verifier.EvidencePackVerificationError, match="bytes mismatch"):
        verifier.verify_evidence_pack(root)


def test_duplicate_companion_path_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    manifest = _manifest(root)
    rows = manifest["migration_execution"]["generated_artifacts"]
    rows[1]["path"] = rows[0]["path"]
    _write_manifest(root, manifest)

    with pytest.raises(verifier.EvidencePackVerificationError, match="duplicate migration companion path"):
        verifier.verify_evidence_pack(root)


def test_companion_path_traversal_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    manifest = _manifest(root)
    manifest["migration_execution"]["generated_artifacts"][0]["path"] = "../audit.json"
    _write_manifest(root, manifest)

    with pytest.raises(verifier.EvidencePackVerificationError, match="path traversal|not a safe pack-relative path"):
        verifier.verify_evidence_pack(root)


def test_companion_row_outside_generated_directory_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    manifest = _manifest(root)
    manifest["migration_execution"]["generated_artifacts"][0]["path"] = "audit.json"
    _write_manifest(root, manifest)

    with pytest.raises(verifier.EvidencePackVerificationError, match="outside the generated artifact directory"):
        verifier.verify_evidence_pack(root)


def test_migration_claim_hash_mismatch_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    execution_path = root / "migration_execution.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    execution["candidates"][0]["generated_mm"]["sha256"] = "0" * 64
    _write_json(execution_path, execution)
    _refresh_migration_execution_hash(root)

    with pytest.raises(verifier.EvidencePackVerificationError, match="sha256 does not match"):
        verifier.verify_evidence_pack(root)


def test_migration_claim_outside_generated_directory_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    execution_path = root / "migration_execution.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    outside = root / "audit.json"
    execution["candidates"][0]["generated_mm"].update({"path": str(outside), "sha256": _sha256_path(outside)})
    _write_json(execution_path, execution)
    _refresh_migration_execution_hash(root)

    with pytest.raises(verifier.EvidencePackVerificationError, match="outside the generated artifact directory"):
        verifier.verify_evidence_pack(root)


def test_schema_or_closed_role_mismatch_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    manifest = _manifest(root)
    manifest["artifact_roles"]["proof_certificate"].append("migration_execution.migration-execution/divide.proof.json")
    _write_manifest(root, manifest)

    with pytest.raises(verifier.EvidencePackVerificationError, match="artifact_roles"):
        verifier.verify_evidence_pack(root)


def test_migration_boundary_tampering_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    manifest = _manifest(root)
    manifest["migration_execution"]["boundary"] = "generated evidence"
    _write_manifest(root, manifest)

    with pytest.raises(verifier.EvidencePackVerificationError, match="host semantic equivalence"):
        verifier.verify_evidence_pack(root)


def test_baseline_evidence_boundary_tampering_is_operational_failure(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    manifest = _manifest(root)
    manifest["baseline"]["role"] = "audit_report"
    _write_manifest(root, manifest)

    with pytest.raises(verifier.EvidencePackVerificationError, match="baseline role"):
        verifier.verify_evidence_pack(root)


def test_verifier_tests_are_registered_in_explicit_pytest_workflow_list() -> None:
    integration = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "integration.yml").read_text(encoding="utf-8")
    audit_pack = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "audit-evidence-pack.yml").read_text(encoding="utf-8")

    assert "tests/test_verify_ci_evidence_pack.py" in integration
    assert "scripts/verify_ci_evidence_pack.py" in audit_pack
    assert "tests/test_verify_ci_evidence_pack.py" in audit_pack


def test_verifier_accepts_relative_migration_claim_paths_after_copy(tmp_path: Path) -> None:
    original = write_valid_pack(tmp_path / "original-pack")
    execution_path = original / "migration_execution.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    generated_dir = execution["artifact_paths"]["generated_artifacts"]
    original_generated = Path(generated_dir)
    execution["artifact_paths"]["generated_artifacts"] = "migration_execution.migration-execution"
    execution["artifact_paths"]["migration_execution"] = "migration_execution.json"
    candidate = execution["candidates"][0]
    candidate["generated_mm"]["path"] = str(Path(candidate["generated_mm"]["path"]).relative_to(original_generated.parent))
    for key in ("proof_certificate", "sarif"):
        candidate["verification"][key]["path"] = str(Path(candidate["verification"][key]["path"]).relative_to(original_generated.parent))
    _write_json(execution_path, execution)
    _refresh_migration_execution_hash(original)
    copied = tmp_path / "downloaded-pack"
    shutil.copytree(original, copied)
    shutil.rmtree(original)

    report = verifier.verify_evidence_pack(copied)

    assert report["companion_file_count"] == 4


def test_unwritten_proof_and_sarif_preplanned_paths_are_non_claims(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    execution_path = root / "migration_execution.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    verification = execution["candidates"][0]["verification"]
    for key in ("proof_certificate", "sarif"):
        verification[key]["written"] = False
        verification[key]["sha256"] = None
    _write_json(execution_path, execution)
    _refresh_migration_execution_hash(root)

    report = verifier.verify_evidence_pack(root)

    assert report["migration_execution_status"] == "emitted_by_audit_cli"


def test_reference_contract_must_match_pack_input_provenance(tmp_path: Path) -> None:
    root = write_valid_pack(tmp_path / "pack")
    mumei = tmp_path / "mumei"
    mumei.write_text("", encoding="utf-8")
    reference = tmp_path / "safe_divide.mm"
    reference.write_text("atom divide\n", encoding="utf-8")

    with pytest.raises(verifier.EvidencePackVerificationError, match="input provenance"):
        verifier.verify_evidence_pack(root, mumei_bin=mumei, reference_contract=reference)
