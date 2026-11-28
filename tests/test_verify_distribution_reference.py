"""Regression tests for the verify-distribution reference validation wiring."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_verify_distribution_reference.py"
spec = importlib.util.spec_from_file_location("check_verify_distribution_reference", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def report(*, runtime_status="skipped", native_status="accepted"):
    runtime = {"status": runtime_status}
    if runtime_status == "skipped":
        runtime["reason"] = "runtime_observations_not_enabled"
    return {
        "schema_version": "mumei.verify-distribution-report/v1",
        "scope": "native_first_distribution_role_orchestration",
        "checks_not_performed": [
            "adapter_evidence",
            "deep_acceptance_fold",
            "unified_verdict",
        ],
        "roles": {
            "proof_certificate": {"status": "accepted"},
            "native_source_llvm": {"status": native_status, "reason": "unclaimed_exit_outcome", "exit_code": 1},
            "artifact_reproduction": {"status": native_status, "reason": "unclaimed_exit_outcome", "exit_code": 1},
            "runtime_observation": runtime,
        },
    }


def test_positive_runtime_off_requires_role_separation():
    module.validate_positive_report(report(), runtime=False)


def test_positive_runtime_on_requires_explicit_runtime_acceptance():
    data = report(runtime_status="accepted")
    module.validate_positive_report(data, runtime=True)


def test_runtime_off_rejects_silent_runtime_acceptance_or_skip_change():
    data = report(runtime_status="accepted")
    with pytest.raises(AssertionError):
        module.validate_positive_report(data, runtime=False)


def test_wrong_build_id_requires_unclaimed_inconclusive_native_roles():
    module.validate_wrong_build_id_report(report(native_status="inconclusive"))
    with pytest.raises(AssertionError):
        module.validate_wrong_build_id_report(report(native_status="accepted"))


def test_integration_workflow_uses_trusted_fixture_and_generated_bundle():
    workflow = (ROOT / ".github/workflows/integration.yml").read_text()
    assert "scripts/check_verify_distribution_reference.py" in workflow
    assert "scenarios/native_observations_accept/src/main.mm" in workflow
    assert "reports/verify_distribution/latest" in workflow
    step_start = workflow.index("Validate verify-distribution reference fixture")
    step_end = workflow.index("Run integrated demo scenarios", step_start)
    step = workflow[step_start:step_end]
    assert "--enable-runtime-observations" not in step
    assert "external" not in step.lower()


def test_script_runtime_opt_in_is_internal_to_trusted_reference_validation():
    script = SCRIPT_PATH.read_text()
    assert "--enable-runtime-observations" in script
    assert "trusted fixture" in script
    assert "adapter_evidence" in script
    assert "--memory-bound-mb" in script
    assert "--attempt-timeout" in script


def test_docs_state_role_boundary_and_runtime_opt_in():
    docs = (ROOT / "docs/CI_REFERENCE.md").read_text()
    for fragment in (
        "role-separated orchestration, not a deep acceptance fold",
        "not a unified verdict, not a proof grade",
        "adapter evidence is outside the verifier's scope",
        "trusted fixture source and the bundle built from it only",
        "unconditional execution of external input artifacts",
    ):
        assert fragment in docs


def test_reference_test_is_in_explicit_pytest_list():
    workflow = (ROOT / ".github/workflows/integration.yml").read_text()
    assert "tests/test_verify_distribution_reference.py" in workflow


def test_positive_report_rejects_input_drift_or_missing_boundary_checks():
    data = report()
    data["inputs_changed"] = True
    with pytest.raises(AssertionError):
        module.validate_positive_report(data, runtime=False)

    data = report()
    data["checks_not_performed"].remove("adapter_evidence")
    with pytest.raises(AssertionError):
        module.validate_positive_report(data, runtime=False)


def test_generated_workdir_preserves_unexpected_files(tmp_path, monkeypatch):
    unexpected = tmp_path / "user-file.txt"
    unexpected.write_text("keep", encoding="utf-8")
    fixture = tmp_path / "fixture.mm"
    fixture.write_text("atom main() -> i64\nrequires: true;\nbody: { 0 };\n", encoding="utf-8")
    monkeypatch.setattr(module, "TRUSTED_FIXTURE", fixture.resolve())
    fake_core = tmp_path / "mumei"
    fake_core.write_text("#!/bin/sh\n", encoding="utf-8")
    parser = module.build_parser()
    args = parser.parse_args([
        "--mumei-bin", str(fake_core),
        "--mumei-agent-python", "python",
        "--mumei-agent-repo", str(tmp_path),
        "--source", str(fixture),
        "--work-dir", str(tmp_path),
    ])
    with pytest.raises(ValueError, match="not generated"):
        module.validate_fixture(args)
    assert unexpected.read_text(encoding="utf-8") == "keep"


def test_runtime_validation_rejects_non_reference_source(tmp_path):
    parser = module.build_parser()
    fixture = tmp_path / "other.mm"
    fixture.write_text("atom main() -> i64\nrequires: true;\nbody: { 0 };\n", encoding="utf-8")
    args = parser.parse_args([
        "--mumei-bin", "mumei",
        "--mumei-agent-python", "python",
        "--mumei-agent-repo", str(tmp_path),
        "--source", str(fixture),
        "--work-dir", str(tmp_path / "out"),
    ])
    with pytest.raises(ValueError, match="trusted fixture"):
        module.validate_fixture(args)
