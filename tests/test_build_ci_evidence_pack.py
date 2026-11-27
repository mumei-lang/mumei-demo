from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import build_ci_evidence_pack as pack

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = REPO_ROOT / "scenarios" / "ci_evidence_pack"


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["agent"], returncode, stdout, "")


def test_audit_environment_empties_credentials_and_sets_fixture_mode() -> None:
    env = pack._audit_environment(
        {
            "LLM_API_KEY": "sentinel-key",
            "OPENAI_API_KEY": "sentinel-key",
            "CI_FIXTURE_MODE": "0",
        },
        Path("/tmp/mumei"),
    )

    assert env["LLM_API_KEY"] == ""
    assert env["OPENAI_API_KEY"] == ""
    assert env["CI_FIXTURE_MODE"] == "1"
    assert env["MUMEI_BIN"] == "/tmp/mumei"


def test_load_audit_json_requires_fixed_contract_keys() -> None:
    with pytest.raises(pack.EvidencePackError, match="missing fixed contract keys"):
        pack._load_audit_json(_completed(json.dumps({"verification_status": "verified"})))


def test_migration_plan_marks_hints_as_human_review_required() -> None:
    audit = {
        "verification_status": "unverifiable",
        "migration_hints": [
            {
                "function_name": "divide",
                "priority": "high",
                "reason": "spec precondition assumed",
                "skeleton": "atom divide",
                "next_step": "review",
            }
        ],
    }

    plan = pack.migration_plan(audit)

    assert plan["schema"] == "mumei-demo.migration-plan/v1"
    assert plan["deterministic_mode"] is True
    assert plan["summary"] == {"candidate_count": 1, "high_priority_count": 1}
    assert plan["entries"][0]["readiness"] == "human_review_required"
    assert "not proof" in plan["entries"][0]["evidence_boundary"]


def test_build_evidence_pack_manifest_and_boundaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent_python = tmp_path / "agent-python"
    mumei_bin = tmp_path / "mumei"
    agent_python.write_text("", encoding="utf-8")
    mumei_bin.write_text("", encoding="utf-8")
    output_dir = tmp_path / "out"

    audit = {
        key: []
        for key in (
            "spec_health_issues",
            "verification_violations",
            "cross_validation_gaps",
            "migration_hints",
            "healed_files",
            "heal_errors",
            "trusted_atoms",
        )
    }
    audit.update(
        {
            "verification_status": "unverifiable",
            "next_steps": [],
            "source_file": str(SCENARIO_DIR / "src" / "ledger.py"),
            "migration_hints": [
                {
                    "function_name": "divide",
                    "priority": "high",
                    "reason": "spec precondition assumed",
                    "skeleton": "atom divide",
                    "next_step": "review",
                }
            ],
        }
    )

    def fake_audit(**kwargs):
        return audit, _completed(json.dumps(audit))

    def fake_verify(*, pack_dir: Path, **kwargs):
        certificate = pack_dir / "reference.proof.json"
        certificate.write_text(json.dumps({"all_verified": True}), encoding="utf-8")
        return (
            {
                "schema": "mumei-demo.reference-verification/v1",
                "reference_contract": "reference/safe_divide.mm",
                "proof_certificate": "reference.proof.json",
                "verify_exit_code": 0,
                "verify_cert_exit_code": 0,
                "all_verified": True,
                "atoms": [{"name": "divide", "status": "verified", "z3_check_result": "unsat"}],
                "boundary": "reference only",
            },
            "verify log",
            "recheck log",
        )

    monkeypatch.setattr(pack, "run_audit", fake_audit)
    monkeypatch.setattr(pack, "run_reference_verification", fake_verify)

    manifest = pack.build_evidence_pack(
        scenario_dir=SCENARIO_DIR,
        output_dir=output_dir,
        agent_repo=tmp_path,
        agent_python=agent_python,
        mumei_bin=mumei_bin,
        env={},
    )

    pack_dir = output_dir / "evidence-pack"
    assert manifest["schema"] == "mumei-demo.ci-evidence-pack/v1"
    assert manifest["sarif"]["status"] == "not_available_in_current_cli"
    assert manifest["sarif"]["required"] is False
    assert not (pack_dir / "audit.sarif").exists()
    assert len(manifest["artifacts"]) == 9
    audit_json = json.loads((pack_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit_json["source_file"] == "fixture/ledger.py"
    assert audit_json["deterministic_no_llm"] is True
    assert audit_json["capability_boundary"]["sarif"] == "not emitted by the current audit CLI"
    summary = (pack_dir / "summary.md").read_text(encoding="utf-8")
    assert "Neither artifact yet proves semantic equivalence" in summary
    workflow = (pack_dir / "github-actions-mumei-audit.yml").read_text(encoding="utf-8")
    assert workflow == (SCENARIO_DIR / "reference" / "workflows" / "mumei-audit.yml").read_text(encoding="utf-8")


def test_reference_workflow_uploads_sarif_only_conditionally() -> None:
    workflow = (SCENARIO_DIR / "reference" / "workflows" / "mumei-audit.yml").read_text(encoding="utf-8")

    assert "if: hashFiles('evidence-pack/audit.sarif') != ''" in workflow
    assert "upload-sarif" in workflow
    assert "--emit-sarif" not in workflow
    assert "--format sarif" not in workflow


def test_scenario_uses_current_cli_builder_and_declares_pack_artifacts() -> None:
    scenario = json.loads((SCENARIO_DIR / "scenario.json").read_text(encoding="utf-8"))
    step = scenario["l1_ci_reference"]["steps"][0]

    assert "scripts/build_ci_evidence_pack.py" in step["command"]
    assert "--format sarif" not in step["command"]
    assert "evidence-pack/audit.json" in step["artifacts"]
    assert "evidence-pack/manifest.json" in step["artifacts"]
    assert "must not fabricate SARIF" in json.dumps(scenario["harness_contract"])
    assert scenario["budget_policy_fingerprint"] == "deterministic-ci-evidence-pack-v1"
