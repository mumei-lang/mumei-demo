from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts import build_ci_evidence_pack as pack

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = REPO_ROOT / "scenarios" / "ci_evidence_pack"
ORIGINAL_MIGRATION_EXECUTION_SUPPORTED = pack.migration_execution_supported


@pytest.fixture(autouse=True)
def migration_execution_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pack, "migration_execution_supported", lambda **_kwargs: False)


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


def test_run_audit_uses_upstream_ci_contract_and_explicit_empty_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNRELATED_PARENT_VARIABLE", "must-not-be-inherited")
    captured = {}
    baseline_input = tmp_path / "baseline-input.json"
    baseline_input.write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}), encoding="utf-8")
    sarif_output = tmp_path / "audit.sarif"
    baseline_output = tmp_path / "audit-baseline.json"

    def fake_run(command, *, cwd: Path, env: dict[str, str]):
        captured["command"] = command
        captured["env"] = env
        sarif_output.write_text(json.dumps({"version": "2.1.0", "runs": [{"results": []}]}), encoding="utf-8")
        baseline_output.write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}), encoding="utf-8")
        return _completed(json.dumps({key: [] for key in pack.FIXED_AUDIT_KEYS}))

    monkeypatch.setattr(pack, "_run", fake_run)
    payload, completed = pack.run_audit(
        source=tmp_path / "ledger.py",
        agent_repo=tmp_path,
        agent_python=tmp_path / "python",
        mumei_bin=tmp_path / "mumei",
        baseline_input=baseline_input,
        sarif_output=sarif_output,
        write_baseline=baseline_output,
        env={},
    )

    assert payload["verification_status"] == []
    assert completed.returncode == 0
    assert "UNRELATED_PARENT_VARIABLE" not in captured["env"]
    assert captured["env"]["LLM_API_KEY"] == ""
    command = captured["command"]
    assert "--sarif-output" in command
    assert str(sarif_output) in command
    assert "--baseline" in command
    assert str(baseline_input) in command
    assert "--write-baseline" in command
    assert str(baseline_output) in command
    assert command[command.index("--fail-on") + 1] == pack.FAIL_ON_POLICY


def test_run_audit_rejects_operational_exit_and_missing_ci_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline_input = tmp_path / "baseline-input.json"
    baseline_input.write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}), encoding="utf-8")

    def fake_run(command, *, cwd: Path, env: dict[str, str]):
        return _completed(json.dumps({key: [] for key in pack.FIXED_AUDIT_KEYS}), returncode=2)

    monkeypatch.setattr(pack, "_run", fake_run)
    with pytest.raises(pack.EvidencePackError, match="operational"):
        pack.run_audit(
            source=tmp_path / "ledger.py",
            agent_repo=tmp_path,
            agent_python=tmp_path / "python",
            mumei_bin=tmp_path / "mumei",
            baseline_input=baseline_input,
            sarif_output=tmp_path / "audit.sarif",
            write_baseline=tmp_path / "audit-baseline.json",
            env={},
        )


def test_ci_artifact_validators_reject_malformed_documents(tmp_path: Path) -> None:
    sarif = tmp_path / "audit.sarif"
    sarif.write_text(json.dumps({"version": "2.0.0", "runs": []}), encoding="utf-8")
    baseline = tmp_path / "audit-baseline.json"
    baseline.write_text(json.dumps({"version": "wrong", "fingerprints": []}), encoding="utf-8")

    with pytest.raises(pack.EvidencePackError, match="SARIF 2.1.0"):
        pack._validate_sarif(sarif)
    with pytest.raises(pack.EvidencePackError, match="mumei.audit-baseline/v1"):
        pack._validate_baseline(baseline)

    sarif.write_text(json.dumps({"version": "2.1.0", "runs": [{"results": []}]}), encoding="utf-8")
    baseline.write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}), encoding="utf-8")
    pack._validate_sarif(sarif)
    pack._validate_baseline(baseline)


def test_baseline_overlay_validation_requires_annotations_when_results_exist(tmp_path: Path) -> None:
    sarif = tmp_path / "audit.sarif"
    sarif.write_text(
        json.dumps({"version": "2.1.0", "runs": [{"results": [{"ruleId": "x"}]}]}),
        encoding="utf-8",
    )

    with pytest.raises(pack.EvidencePackError, match="baseline policy overlay"):
        pack._validate_sarif(sarif, require_baseline_state=True)
    with pytest.raises(pack.EvidencePackError, match="baseline policy overlay"):
        pack._validate_baseline_annotations({"findings": [{"category": "spec"}]})

    sarif.write_text(
        json.dumps({"version": "2.1.0", "runs": [{"results": [{"ruleId": "x", "baselineState": "unchanged"}]}]}),
        encoding="utf-8",
    )
    pack._validate_sarif(sarif, require_baseline_state=True)
    pack._validate_baseline_annotations({"findings": [{"category": "spec", "baseline": "suppressed"}]})


def test_reference_baseline_input_is_valid_policy_data() -> None:
    baseline = SCENARIO_DIR / "reference" / "audit-baseline.json"

    pack._validate_baseline(baseline)
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    assert payload["fingerprints"] == sorted(payload["fingerprints"])


def test_run_audit_accepts_fail_on_finding_exit_with_valid_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline_input = tmp_path / "baseline-input.json"
    baseline_input.write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}), encoding="utf-8")
    sarif_output = tmp_path / "audit.sarif"
    baseline_output = tmp_path / "audit-baseline.json"

    def fake_run(command, *, cwd: Path, env: dict[str, str]):
        sarif_output.write_text(json.dumps({"version": "2.1.0", "runs": [{"results": []}]}), encoding="utf-8")
        baseline_output.write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}), encoding="utf-8")
        return _completed(json.dumps({key: [] for key in pack.FIXED_AUDIT_KEYS}), returncode=1)

    monkeypatch.setattr(pack, "_run", fake_run)
    _, completed = pack.run_audit(
        source=tmp_path / "ledger.py",
        agent_repo=tmp_path,
        agent_python=tmp_path / "python",
        mumei_bin=tmp_path / "mumei",
        baseline_input=baseline_input,
        sarif_output=sarif_output,
        write_baseline=baseline_output,
        env={},
    )

    assert completed.returncode == 1


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
    assert plan["artifact_paths"] == list(pack.ARTIFACT_PATHS)
    assert plan["artifact_roles"] == pack.artifact_roles()
    assert plan["evidence_boundary_by_role"]["native_bundle"].startswith("No native bundle")
    assert plan["evidence_boundary_by_role"]["adapter_observation"].startswith("No adapter observation")


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
        kwargs["sarif_output"].write_text(
            json.dumps({"version": "2.1.0", "runs": [{"results": []}]}),
            encoding="utf-8",
        )
        kwargs["write_baseline"].write_text(
            json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": ["fingerprint-a"]}),
            encoding="utf-8",
        )
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
    assert manifest["schema"] == "mumei-demo.ci-evidence-pack/v2"
    assert manifest["sarif"]["status"] == "emitted_by_audit_cli"
    assert manifest["sarif"]["required"] is True
    assert manifest["baseline"]["status"] == "emitted_by_audit_cli"
    assert manifest["baseline"]["role"] == "ci_policy"
    assert manifest["fail_on"] == {
        "policy": pack.FAIL_ON_POLICY,
        "audit_exit_code": 0,
        "boundary": "Fail-on is a CI policy outcome over non-suppressed findings, not a verdict or proof boundary change.",
    }
    assert (pack_dir / "audit.sarif").is_file()
    assert (pack_dir / "audit-baseline.json").is_file()
    assert len(manifest["artifacts"]) == 11
    assert [row["path"] for row in manifest["artifacts"]] == [p for p in pack.HASHED_ARTIFACT_PATHS if p != "migration_execution.json"]
    assert manifest["artifact_paths"] == pack.pack_artifact_paths(False)
    assert manifest["artifact_roles"] == pack.artifact_roles(False)
    assert manifest["migration_execution"]["generated_artifacts"] == []
    assert manifest["migration_execution"]["generated_artifacts_dir"] is None
    assert manifest["evidence_roles"]["native_bundle"]["status"] == "absent"
    assert manifest["evidence_roles"]["adapter_observation"]["status"] == "absent"
    assert any("audit-baseline.json is CI suppression policy" in line for line in manifest["evidence_boundary"])
    assert any("No native bundle is present or implied" in line for line in manifest["evidence_boundary"])
    assert any("No adapter observation is present or implied" in line for line in manifest["evidence_boundary"])
    assert manifest["inputs"]["audit_baseline_input"]["path"] == pack.BASELINE_INPUT
    audit_json = json.loads((pack_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit_json["source_file"] == "fixture/ledger.py"
    assert audit_json["deterministic_no_llm"] is True
    assert audit_json["audit_cli_contract"] == {
        "sarif_output": "audit.sarif",
        "baseline_input": pack.BASELINE_INPUT,
        "baseline_output": "audit-baseline.json",
        "fail_on": pack.FAIL_ON_POLICY,
        "exit_policy": "0/1 are finding-policy outcomes; 2 is an operational audit failure",
    }
    assert audit_json["artifact_paths"] == pack.pack_artifact_paths(False)
    assert audit_json["artifact_roles"] == pack.artifact_roles(False)
    assert audit_json["evidence_boundary_by_role"] == pack.EVIDENCE_BOUNDARIES
    assert audit_json["evidence_boundary_by_role"]["audit_report"].endswith("not a proof certificate.")
    migration_json = json.loads((pack_dir / "migration_plan.json").read_text(encoding="utf-8"))
    assert migration_json["artifact_paths"] == pack.pack_artifact_paths(False)
    assert migration_json["artifact_roles"] == pack.artifact_roles(False)
    assert migration_json["evidence_boundary_by_role"] == pack.EVIDENCE_BOUNDARIES
    assert migration_json["evidence_boundary_by_role"]["migration_plan"].startswith("Human-review migration scaffold")
    summary = (pack_dir / "summary.md").read_text(encoding="utf-8")
    assert "Neither artifact yet proves semantic equivalence" in summary
    assert "`audit-baseline.json` is a `ci_policy` artifact" in summary
    assert "must not be treated as audit evidence or proof acceptance" in summary
    assert "empty roles in `artifact_roles`" in summary
    workflow = (pack_dir / "github-actions-mumei-audit.yml").read_text(encoding="utf-8")
    assert workflow == (SCENARIO_DIR / "reference" / "workflows" / "mumei-audit.yml").read_text(encoding="utf-8")


def test_build_evidence_pack_writes_pack_then_rejects_fail_on_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent_python = tmp_path / "agent-python"
    mumei_bin = tmp_path / "mumei"
    agent_python.write_text("", encoding="utf-8")
    mumei_bin.write_text("", encoding="utf-8")
    audit = {key: [] for key in pack.FIXED_AUDIT_KEYS}
    audit.update({
        "verification_status": "refuted",
        "migration_hints": [{"function_name": "divide", "priority": "high"}],
    })

    def fake_audit(**kwargs):
        kwargs["sarif_output"].write_text(
            json.dumps({"version": "2.1.0", "runs": [{"results": []}]}),
            encoding="utf-8",
        )
        kwargs["write_baseline"].write_text(
            json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}),
            encoding="utf-8",
        )
        return audit, _completed(json.dumps(audit), returncode=1)

    def fake_verify(*, pack_dir: Path, **kwargs):
        (pack_dir / "reference.proof.json").write_text(json.dumps({"all_verified": True}), encoding="utf-8")
        return ({
            "schema": "mumei-demo.reference-verification/v1",
            "reference_contract": "reference/safe_divide.mm",
            "proof_certificate": "reference.proof.json",
            "verify_exit_code": 0,
            "verify_cert_exit_code": 0,
            "all_verified": True,
            "atoms": [],
            "boundary": "reference only",
        }, "", "")

    monkeypatch.setattr(pack, "run_audit", fake_audit)
    monkeypatch.setattr(pack, "run_reference_verification", fake_verify)

    with pytest.raises(pack.EvidencePackError, match="fail-on policy"):
        pack.build_evidence_pack(
            scenario_dir=SCENARIO_DIR,
            output_dir=tmp_path / "out",
            agent_repo=tmp_path,
            agent_python=agent_python,
            mumei_bin=mumei_bin,
            env={},
        )

    manifest = json.loads((tmp_path / "out" / "evidence-pack" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["fail_on"]["audit_exit_code"] == 1
    assert (tmp_path / "out" / "evidence-pack" / "audit.sarif").is_file()


def test_artifact_paths_match_present_manifest_artifacts_and_absent_roles() -> None:
    assert len(pack.ARTIFACT_PATHS) == 13
    assert len(pack.HASHED_ARTIFACT_PATHS) == 12
    assert "manifest.json" in pack.ARTIFACT_PATHS
    assert "manifest.json" not in pack.HASHED_ARTIFACT_PATHS
    assert len(set(pack.ARTIFACT_PATHS)) == len(pack.ARTIFACT_PATHS)
    for role in ("audit_report", "migration_plan", "migration_execution", "proof_certificate", "ci_policy"):
        assert pack.ARTIFACT_ROLES[role]
        assert all(path in pack.ARTIFACT_PATHS for path in pack.ARTIFACT_ROLES[role])
        assert pack.EVIDENCE_BOUNDARIES[role]
    for role in ("native_bundle", "adapter_observation"):
        assert pack.ARTIFACT_ROLES[role] == []
        assert "not proof" not in pack.EVIDENCE_BOUNDARIES[role].lower()
    assert "not evidence" in pack.EVIDENCE_BOUNDARIES["ci_policy"]

    # Keep this as an explicit golden map rather than comparing the constant to
    # itself: a wrong audit/proof/policy/native/adapter assignment must fail here.
    assert pack.ARTIFACT_ROLES == {
        "audit_report": ["audit.json", "audit.sarif"],
        "migration_plan": ["migration_plan.json"],
        "migration_execution": ["migration_execution.json"],
        "proof_certificate": ["reference.proof.json"],
        "ci_policy": ["audit-baseline.json"],
        "native_bundle": [],
        "adapter_observation": [],
    }
    assert set(pack.ARTIFACT_ROLES) == set(pack.EVIDENCE_BOUNDARIES)


def test_main_makes_relative_agent_python_absolute_without_resolving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return {"schema": pack.PACK_SCHEMA, "artifacts": [], "migration_execution": {"status": "not_available_in_current_cli"}}

    real_python = tmp_path / "real-python"
    real_python.write_text("", encoding="utf-8")
    link_dir = tmp_path / "venv" / "bin"
    link_dir.mkdir(parents=True)
    link_python = link_dir / "python"
    link_python.symlink_to(real_python)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pack, "build_evidence_pack", fake_build)

    assert pack.main(
        [
            "--scenario-dir", "scenario",
            "--output-dir", "out",
            "--mumei-agent-repo", "agent",
            "--mumei-agent-python", "venv/bin/python",
            "--mumei-bin", "mumei",
        ]
    ) == 0

    agent_python = captured["agent_python"]
    assert agent_python.is_absolute()
    assert agent_python == link_python
    assert agent_python != real_python


def test_summary_distinguishes_missing_finding_counts_from_zero(tmp_path: Path) -> None:
    output = tmp_path / "summary.md"
    pack.write_summary(
        output,
        {"verification_status": "verified"},
        {"summary": {"candidate_count": 0}},
        {"proof_certificate": "reference.proof.json"},
    )

    text = output.read_text(encoding="utf-8")
    assert "| Code findings | not reported |" in text
    assert "| Spec/model findings | not reported |" in text
    assert "| Code findings | 0 |" not in text


def test_reference_workflow_uses_upstream_sarif_baseline_and_fail_on_contract() -> None:
    workflow = (SCENARIO_DIR / "reference" / "workflows" / "mumei-audit.yml").read_text(encoding="utf-8")

    assert "--sarif-output" in workflow
    assert "--baseline" in workflow
    assert "--write-baseline" in workflow
    assert "--fail-on high-confidence" in workflow
    assert "mumei.audit-baseline/v1" in workflow
    assert "if: always() && hashFiles('evidence-pack/audit.sarif') != ''" in workflow
    assert "continue-on-error: true" in workflow
    assert ".mumei/.venv/bin/mumei-agent\" audit" in workflow
    assert "PYTHONPATH:" not in workflow
    assert "working-directory: .mumei/mumei-agent\n        env:\n          # Empty values" not in workflow
    assert "upload-sarif" in workflow
    assert "steps.upload-sarif.outcome" in workflow
    assert "CI policy, not evidence" in workflow
    assert "--emit-sarif" not in workflow
    assert "--format sarif" not in workflow
    assert "--migration-execution-output" in workflow
    assert "not_available_in_current_cli" in workflow


def test_audit_evidence_workflow_asserts_closed_artifact_roles() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "audit-evidence-pack.yml").read_text(encoding="utf-8")

    assert 'manifest["artifact_paths"] == expected_paths' in workflow
    assert '"audit_report": ["audit.json", "audit.sarif"]' in workflow
    assert '"migration_execution": migration_role' in workflow
    assert '"proof_certificate": ["reference.proof.json"]' in workflow
    assert '"ci_policy": ["audit-baseline.json"]' in workflow
    assert '"native_bundle": []' in workflow
    assert '"adapter_observation": []' in workflow
    assert 'audit["artifact_paths"] == manifest["artifact_paths"]' in workflow
    assert 'audit["artifact_roles"] == manifest["artifact_roles"]' in workflow
    assert 'audit["evidence_boundary_by_role"] == manifest["evidence_boundary_by_role"]' in workflow
    assert 'migration["artifact_paths"] == manifest["artifact_paths"]' in workflow
    assert 'migration["artifact_roles"] == manifest["artifact_roles"]' in workflow
    assert 'migration["evidence_boundary_by_role"] == manifest["evidence_boundary_by_role"]' in workflow
    assert 'manifest["sarif"]["status"] == "emitted_by_audit_cli"' in workflow
    assert 'manifest["baseline"]["status"] == "emitted_by_audit_cli"' in workflow
    assert 'manifest["fail_on"]["policy"] == "high-confidence"' in workflow
    assert 'not_available_in_current_cli' in workflow
    assert 'assert "not evidence" in manifest["evidence_roles"]["ci_policy"]["boundary"]' in workflow


def test_scenario_uses_current_cli_builder_and_declares_pack_artifacts() -> None:
    scenario = json.loads((SCENARIO_DIR / "scenario.json").read_text(encoding="utf-8"))
    step = scenario["l1_ci_reference"]["steps"][0]

    assert "scripts/build_ci_evidence_pack.py" in step["command"]
    assert "--format sarif" not in step["command"]
    assert "evidence-pack/audit.json" in step["artifacts"]
    assert "evidence-pack/audit.sarif" in step["artifacts"]
    assert "evidence-pack/audit-baseline.json" in step["artifacts"]
    assert "evidence-pack/manifest.json" in step["artifacts"]
    assert "sarif status: emitted_by_audit_cli" in step["expected_patterns"]
    assert "baseline status: emitted_by_audit_cli" in step["expected_patterns"]
    assert "fail-on policy: high-confidence" in step["expected_patterns"]
    assert "migration execution status:" in step["expected_patterns"]
    contract_text = json.dumps(scenario["harness_contract"])
    assert "must not fabricate SARIF" in contract_text
    assert "ci_policy" in contract_text
    assert "not evidence" in contract_text
    assert "migration_execution" in contract_text
    assert "not_available_in_current_cli" in contract_text
    assert scenario["budget_policy_fingerprint"] == "deterministic-ci-evidence-pack-v2"


def valid_execution() -> dict:
    return {
        "schema": pack.MIGRATION_EXECUTION_SCHEMA,
        "generated_at": "now",
        "source": {"path": "fixture/ledger.py", "language": "python", "kind": "file", "sha256": "0" * 64},
        "audit": {},
        "selection": {"basis": "all audit migration_hints candidates", "requested_functions": [], "missing_requested_functions": []},
        "candidates": [{
            "function_name": "divide", "source_provenance": {}, "selection": {},
            "extracted_contract": {}, "generated_mm": {}, "heal": {}, "verification": {},
            "unbound_audit_diagnostics": {}, "contract_provenance": {},
            "evidence_blockers": [], "operational_errors": [], "review_required": True,
            "execution_state": "ready_for_human_review",
        }],
        "operational_errors": [],
        "artifact_paths": {
            "migration_execution": "migration_execution.json",
            "generated_artifacts": "migration_execution.migration-execution",
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


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_execution_with_claimed_companions(generated: Path) -> dict:
    generated.mkdir(parents=True, exist_ok=True)
    mm = generated / "divide.mm"
    proof = generated / "divide.proof.json"
    sarif_dir = generated / "divide"
    sarif_dir.mkdir(exist_ok=True)
    sarif = sarif_dir / "report.sarif"
    mm.write_text("atom divide\n", encoding="utf-8")
    proof.write_text("{\"all_verified\": true}\n", encoding="utf-8")
    sarif.write_text("{\"version\": \"2.1.0\"}\n", encoding="utf-8")
    cache = generated / ".mumei" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "verification_cache.json").write_text("{}\n", encoding="utf-8")
    payload = valid_execution()
    candidate = payload["candidates"][0]
    candidate["generated_mm"] = {
        "path": str(mm),
        "sha256": _sha256_path(mm),
        "origin": "generated_skeleton",
        "healed_source_path": None,
    }
    candidate["verification"] = {
        "proof_certificate": {"path": str(proof), "sha256": _sha256_path(proof), "written": True},
        "sarif": {"path": str(sarif), "sha256": _sha256_path(sarif), "written": True},
    }
    return payload


def companion_rows_fixture(tmp_path: Path) -> tuple[dict, Path, Path, list[dict[str, object]]]:
    pack_dir = tmp_path / "evidence-pack"
    generated = pack_dir / "migration_execution.migration-execution"
    payload = valid_execution_with_claimed_companions(generated)
    rows = pack._artifact_rows(pack._generated_artifact_files(generated), pack_dir, include_bytes=True)
    return payload, generated, pack_dir, rows


def test_migration_execution_validator_accepts_complete_upstream_shape(tmp_path: Path) -> None:
    path = tmp_path / "migration_execution.json"
    path.write_text(json.dumps(valid_execution()), encoding="utf-8")
    assert pack._validate_migration_execution(path)["schema"] == pack.MIGRATION_EXECUTION_SCHEMA


def test_migration_execution_validator_rejects_partial_or_inconsistent_shape(tmp_path: Path) -> None:
    path = tmp_path / "migration_execution.json"
    payload = valid_execution(); payload["summary"]["blocked"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(pack.EvidencePackError, match="summary"):
        pack._validate_migration_execution(path)
    path.write_text(json.dumps({"schema": pack.MIGRATION_EXECUTION_SCHEMA}), encoding="utf-8")
    with pytest.raises(pack.EvidencePackError, match="required"):
        pack._validate_migration_execution(path)


def test_migration_execution_capability_help_detection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pack, "migration_execution_supported", ORIGINAL_MIGRATION_EXECUTION_SUPPORTED)
    monkeypatch.setattr(pack, "_run", lambda *a, **k: _completed("--migration-execution-output"))
    assert pack.migration_execution_supported(agent_repo=tmp_path, agent_python=tmp_path / "python", env={})
    monkeypatch.setattr(pack, "_run", lambda *a, **k: _completed("other"))
    assert not pack.migration_execution_supported(agent_repo=tmp_path, agent_python=tmp_path / "python", env={})
    monkeypatch.setattr(pack, "_run", lambda *a, **k: _completed("--migration-execution-output", returncode=2))
    assert not pack.migration_execution_supported(agent_repo=tmp_path, agent_python=tmp_path / "python", env={})


def test_run_audit_passes_and_validates_migration_execution_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline_input = tmp_path / "baseline.json"; baseline_input.write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}))
    sarif = tmp_path / "audit.sarif"; baseline = tmp_path / "audit-baseline.json"; execution = tmp_path / "migration_execution.json"
    captured = {}
    def fake_run(command, *, cwd, env):
        captured["command"] = command
        sarif.write_text(json.dumps({"version": "2.1.0", "runs": [{"results": []}]}))
        baseline.write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}))
        execution.write_text(json.dumps(valid_execution()))
        (tmp_path / "migration_execution.migration-execution").mkdir()
        return _completed(json.dumps({key: [] for key in pack.FIXED_AUDIT_KEYS}))
    monkeypatch.setattr(pack, "_run", fake_run)
    pack.run_audit(source=tmp_path / "x.py", agent_repo=tmp_path, agent_python=tmp_path / "python", mumei_bin=tmp_path / "mumei", baseline_input=baseline_input, sarif_output=sarif, write_baseline=baseline, migration_execution_output=execution, env={})
    assert "--migration-execution-output" in captured["command"]


def test_migration_execution_validator_rejects_missing_candidate_keys_and_bad_boundary(tmp_path: Path) -> None:
    path = tmp_path / "migration_execution.json"
    payload = valid_execution()
    del payload["candidates"][0]["generated_mm"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(pack.EvidencePackError, match="candidate contract"):
        pack._validate_migration_execution(path)

    payload = valid_execution()
    payload["evidence_boundary"] = "not proof that host-language code implements the same behavior"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(pack.EvidencePackError, match="boundary is malformed"):
        pack._validate_migration_execution(path)


def test_migration_execution_output_missing_or_malformed_is_operational_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline_input = tmp_path / "baseline.json"
    baseline_input.write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}))
    sarif = tmp_path / "audit.sarif"
    baseline = tmp_path / "audit-baseline.json"
    execution = tmp_path / "migration_execution.json"

    def fake_run(command, *, cwd, env):
        sarif.write_text(json.dumps({"version": "2.1.0", "runs": [{"results": []}]}))
        baseline.write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}))
        return _completed(json.dumps({key: [] for key in pack.FIXED_AUDIT_KEYS}))

    monkeypatch.setattr(pack, "_run", fake_run)
    kwargs = {
        "source": tmp_path / "x.py", "agent_repo": tmp_path, "agent_python": tmp_path / "python",
        "mumei_bin": tmp_path / "mumei", "baseline_input": baseline_input, "sarif_output": sarif,
        "write_baseline": baseline, "migration_execution_output": execution, "env": {},
    }
    with pytest.raises(pack.EvidencePackError, match="did not write"):
        pack.run_audit(**kwargs)

    execution.write_text("not json", encoding="utf-8")
    with pytest.raises(pack.EvidencePackError, match="not valid JSON"):
        pack.run_audit(**kwargs)

    execution.write_text(json.dumps(valid_execution()), encoding="utf-8")
    with pytest.raises(pack.EvidencePackError, match="generated artifact directory"):
        pack.run_audit(**kwargs)


def test_dynamic_evidence_metadata_keeps_closed_role_without_fabricating_file() -> None:
    unavailable = pack.evidence_metadata(False)
    assert "migration_execution.json" not in unavailable["artifact_paths"]
    assert unavailable["artifact_roles"]["migration_execution"] == []
    assert "migration_execution" in unavailable["evidence_boundary_by_role"]

    available = pack.evidence_metadata(True)
    assert "migration_execution.json" in available["artifact_paths"]
    assert available["artifact_roles"]["migration_execution"] == ["migration_execution.json"]


def test_write_summary_records_migration_execution_capability(tmp_path: Path) -> None:
    audit = {
        "verification_status": "unverifiable", "exit_code": 0,
        "spec_health_issues": [], "verification_violations": [], "baseline": {"suppressed": 0, "new": 0},
    }
    plan = {"summary": {"candidate_count": 1}}
    verification = {"proof_certificate": "reference.proof.json"}
    output = tmp_path / "summary.md"
    pack.write_summary(output, audit, plan, verification, "emitted_by_audit_cli")
    assert "| Migration execution | `emitted_by_audit_cli` |" in output.read_text(encoding="utf-8")


def test_build_evidence_pack_supported_migration_execution_is_hashed_and_role_scoped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent_python = tmp_path / "agent-python"
    mumei_bin = tmp_path / "mumei"
    agent_python.write_text("", encoding="utf-8")
    mumei_bin.write_text("", encoding="utf-8")
    output_dir = Path("relative-out")
    monkeypatch.chdir(tmp_path)
    audit = {key: [] for key in pack.FIXED_AUDIT_KEYS}
    audit.update({"verification_status": "unverifiable", "migration_hints": [{"function_name": "divide", "priority": "high"}]})

    def fake_audit(**kwargs):
        kwargs["sarif_output"].write_text(json.dumps({"version": "2.1.0", "runs": [{"results": []}]}), encoding="utf-8")
        kwargs["write_baseline"].write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}), encoding="utf-8")
        generated = kwargs["migration_execution_output"].parent / "migration_execution.migration-execution"
        generated.mkdir()
        payload = valid_execution_with_claimed_companions(generated)
        kwargs["migration_execution_output"].write_text(json.dumps(payload), encoding="utf-8")
        return audit, _completed(json.dumps(audit))

    def fake_verify(*, pack_dir: Path, **kwargs):
        (pack_dir / "reference.proof.json").write_text(json.dumps({"all_verified": True}), encoding="utf-8")
        return ({
            "schema": "mumei-demo.reference-verification/v1",
            "reference_contract": "reference/safe_divide.mm",
            "proof_certificate": "reference.proof.json",
            "verify_exit_code": 0,
            "verify_cert_exit_code": 0,
            "all_verified": True,
            "atoms": [],
            "boundary": "reference only",
        }, "verify log", "recheck log")

    monkeypatch.setattr(pack, "migration_execution_supported", lambda **_kwargs: True)
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
    pack_dir = tmp_path / output_dir / "evidence-pack"
    assert manifest["migration_execution"]["status"] == "emitted_by_audit_cli"
    assert manifest["migration_execution"]["path"] == "migration_execution.json"
    assert "migration_execution.json" in manifest["artifact_paths"]
    assert manifest["artifact_roles"]["migration_execution"] == ["migration_execution.json"]
    assert len(manifest["artifacts"]) == 12
    assert any(row["path"] == "migration_execution.json" for row in manifest["artifacts"])
    rows = manifest["migration_execution"]["generated_artifacts"]
    rows_by_path = {row["path"]: row for row in rows}
    assert set(rows_by_path) == {
        "migration_execution.migration-execution/.mumei/cache/verification_cache.json",
        "migration_execution.migration-execution/divide.mm",
        "migration_execution.migration-execution/divide.proof.json",
        "migration_execution.migration-execution/divide/report.sarif",
    }
    for relative, row in rows_by_path.items():
        artifact = pack_dir / relative
        assert row["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert row["bytes"] == artifact.stat().st_size
    assert json.loads((pack_dir / "audit.json").read_text())["artifact_roles"]["migration_execution"] == ["migration_execution.json"]
    assert json.loads((pack_dir / "migration_plan.json").read_text())["artifact_roles"]["migration_execution"] == ["migration_execution.json"]
    assert manifest["evidence_roles"]["native_bundle"]["status"] == "absent"
    assert manifest["evidence_roles"]["adapter_observation"]["status"] == "absent"

def test_build_evidence_pack_rejects_claimed_companion_hash_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent_python = tmp_path / "agent-python"
    mumei_bin = tmp_path / "mumei"
    agent_python.write_text("", encoding="utf-8")
    mumei_bin.write_text("", encoding="utf-8")
    audit = {key: [] for key in pack.FIXED_AUDIT_KEYS}
    audit.update({"verification_status": "unverifiable", "migration_hints": [{"function_name": "divide", "priority": "high"}]})

    def fake_audit(**kwargs):
        kwargs["sarif_output"].write_text(json.dumps({"version": "2.1.0", "runs": [{"results": []}]}), encoding="utf-8")
        kwargs["write_baseline"].write_text(json.dumps({"version": pack.BASELINE_SCHEMA, "fingerprints": []}), encoding="utf-8")
        generated = kwargs["migration_execution_output"].parent / "migration_execution.migration-execution"
        payload = valid_execution_with_claimed_companions(generated)
        payload["candidates"][0]["generated_mm"]["sha256"] = "0" * 64
        kwargs["migration_execution_output"].write_text(json.dumps(payload), encoding="utf-8")
        return audit, _completed(json.dumps(audit))

    def fake_verify(*, pack_dir: Path, **kwargs):
        (pack_dir / "reference.proof.json").write_text(json.dumps({"all_verified": True}), encoding="utf-8")
        return ({"schema": "mumei-demo.reference-verification/v1", "proof_certificate": "reference.proof.json", "verify_exit_code": 0, "verify_cert_exit_code": 0, "all_verified": True, "atoms": [], "boundary": "reference only"}, "", "")

    monkeypatch.setattr(pack, "migration_execution_supported", lambda **_kwargs: True)
    monkeypatch.setattr(pack, "run_audit", fake_audit)
    monkeypatch.setattr(pack, "run_reference_verification", fake_verify)

    with pytest.raises(pack.EvidencePackError, match="sha256 does not match"):
        pack.build_evidence_pack(
            scenario_dir=SCENARIO_DIR,
            output_dir=tmp_path / "out",
            agent_repo=tmp_path,
            agent_python=agent_python,
            mumei_bin=mumei_bin,
            env={},
        )


def test_migration_companion_hash_manifest_matches_claimed_generated_mm_proof_and_sarif(tmp_path: Path) -> None:
    payload, generated, pack_dir, rows = companion_rows_fixture(tmp_path)

    pack._validate_migration_companion_rows(payload, generated, pack_dir, rows)

    assert all(set(row) == {"path", "sha256", "bytes"} for row in rows)
    assert len(rows) == 4


def test_migration_companion_hash_mismatch_is_operational_failure(tmp_path: Path) -> None:
    payload, generated, pack_dir, rows = companion_rows_fixture(tmp_path)
    payload["candidates"][0]["generated_mm"]["sha256"] = "0" * 64

    with pytest.raises(pack.EvidencePackError, match="sha256 does not match"):
        pack._validate_migration_companion_rows(payload, generated, pack_dir, rows)


def test_migration_companion_missing_claimed_file_is_operational_failure(tmp_path: Path) -> None:
    payload, generated, pack_dir, rows = companion_rows_fixture(tmp_path)
    missing = generated / "missing.mm"
    payload["candidates"][0]["generated_mm"].update({"path": str(missing), "sha256": "0" * 64})

    with pytest.raises(pack.EvidencePackError, match="missing from the companion hash manifest"):
        pack._validate_migration_companion_rows(payload, generated, pack_dir, rows)


def test_migration_companion_path_outside_generated_directory_is_operational_failure(tmp_path: Path) -> None:
    payload, generated, pack_dir, rows = companion_rows_fixture(tmp_path)
    outside = pack_dir / "audit.json"
    outside.write_text("{}\n", encoding="utf-8")
    payload["candidates"][0]["generated_mm"].update({"path": str(outside), "sha256": _sha256_path(outside)})

    with pytest.raises(pack.EvidencePackError, match="outside the generated artifact directory"):
        pack._validate_migration_companion_rows(payload, generated, pack_dir, rows)


def test_migration_companion_symlink_escape_and_nonregular_file_are_operational_failures(tmp_path: Path) -> None:
    root = tmp_path / "migration_execution.migration-execution"
    root.mkdir()
    target = tmp_path / "target.mm"
    target.write_text("atom target\n", encoding="utf-8")
    (root / "linked.mm").symlink_to(target)
    with pytest.raises(pack.EvidencePackError, match="symlink|non-regular"):
        pack._generated_artifact_files(root)

    (root / "linked.mm").unlink()
    directory_target = tmp_path / "directory-target"
    directory_target.mkdir()
    (root / "linked-dir").symlink_to(directory_target, target_is_directory=True)
    with pytest.raises(pack.EvidencePackError, match="symlink"):
        pack._generated_artifact_files(root)

    (root / "linked-dir").unlink()
    os.mkfifo(root / "fifo")
    with pytest.raises(pack.EvidencePackError, match="non-regular file"):
        pack._generated_artifact_files(root)

    payload = valid_execution()
    payload["artifact_paths"]["generated_artifacts"] = "../outside"
    with pytest.raises(pack.EvidencePackError, match="escapes the evidence pack"):
        pack._migration_generated_dir(payload, tmp_path / "migration_execution.json")

    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(root, target_is_directory=True)
    payload["artifact_paths"]["generated_artifacts"] = "linked-root"
    with pytest.raises(pack.EvidencePackError, match="symlink component"):
        pack._migration_generated_dir(payload, tmp_path / "migration_execution.json")

    payload["artifact_paths"]["generated_artifacts"] = "."
    with pytest.raises(pack.EvidencePackError, match="does not match the migration execution output"):
        pack._migration_generated_dir(payload, tmp_path / "migration_execution.json")


def test_migration_companion_inconsistent_written_metadata_is_operational_failure(tmp_path: Path) -> None:
    payload, generated, pack_dir, rows = companion_rows_fixture(tmp_path)
    proof = payload["candidates"][0]["verification"]["proof_certificate"]
    proof["written"] = False

    with pytest.raises(pack.EvidencePackError, match="hash metadata is inconsistent"):
        pack._validate_migration_companion_rows(payload, generated, pack_dir, rows)
