from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import record_scenario as scenario


def test_fixed_checks_are_nonvacuous_and_cover_state_and_input_boundaries():
    report = scenario.run_checks()
    assert report["status"] == "passed"
    names = {row["name"] for row in report["cases"]}
    assert len(names) == len(report["cases"]) == 25
    assert {"owner_update", "administrator_update", "reader_read", "replayed_update",
            "changed_principal", "changed_policy", "missing_policy", "missing_record",
            "concurrent_conflict", "self_asserted_role", "arbitrary_dispatch",
            "protected_field_organization", "protected_field_owner", "protected_field_version"} <= names
    assert sum(row.get("reason") == "accepted" for row in report["cases"]) == 3


@pytest.mark.parametrize("variant,name", [
    ("missing_organization", "cross_organization"), ("missing_ownership", "wrong_owner"),
    ("changed_identity", "owner_update"), ("direct_write", "reader_update"),
])
def test_broken_hosts_are_detected_by_the_same_reference_cases(variant, name):
    report = scenario.run_checks(scenario.VARIANTS[variant])
    assert report["status"] == "failed"
    assert name in report["failed_cases"]
    assert len(report["cases"]) == 25


@pytest.mark.parametrize("variant", scenario.VARIANTS)
def test_cli_exit_and_diagnostic_match_the_saved_observation(tmp_path, variant):
    output = tmp_path / "cases.json"
    process = subprocess.run([sys.executable, str(ROOT / "scripts/record_scenario.py"),
                              "--variant", variant, "--output", str(output)], capture_output=True, text=True)
    report = json.loads(output.read_text())
    assert report["variant"] == variant
    assert process.returncode == (0 if report["status"] == "passed" else 1)
    for name in report["failed_cases"]:
        assert f"Violated case: {name}" in process.stdout
    assert process.stderr == ""


def test_observations_never_contain_record_bodies_proposals_or_exceptions():
    report = scenario.run_checks()
    for row in report["cases"]:
        assert not {"value", "records", "payload", "exception", "credentials"} & set(row)
        if "audit" in row:
            assert not {"value", "records", "payload", "exception", "credentials"} & set(row["audit"])


@pytest.mark.parametrize("payload", [
    scenario.proposal(variant="direct_write"), scenario.proposal(callback="execute"),
    scenario.proposal(policy={"update_enabled": True}), scenario.proposal(principal={"role": "administrator"}),
])
def test_proposals_cannot_select_test_variants_or_host_inputs(payload):
    executor = scenario.RecordExecutor(scenario.INITIAL, scenario.POLICY)
    assert executor.execute(scenario.WRITER, payload).reason == "invalid_proposal"
    assert executor._state.records == scenario.INITIAL


def test_scenario_requires_every_proof_observation_and_specific_negative_control():
    config = json.loads((ROOT / "scenarios/record_execution_demo/scenario.json").read_text())
    steps = {s["id"]: s for layer in config["layers"] for s in config[layer]["steps"]}
    assert set(steps) == set(config["evidence_requirements"]["steps"])
    assert "optional_toolchain" not in steps["audit_model"]
    assert "optional_path" not in steps["audit_model"]
    assert steps["reject_broken_local"]["expected_exit"] == 1
    assert "Postcondition (ensures) is not satisfied" in steps["reject_broken_local"]["expected_patterns"]
    model = config["evidence_requirements"]["independent_models"][0]
    artifacts = config["evidence_requirements"]["artifacts"]
    assert model["report"] in artifacts
    assert all(f"model/{name}" in artifacts for name in model["sources"])
    assert all("{output_dir}" in steps[name]["command"] for name in ("verify_local", "reject_broken_local", "check_runtime"))
    for variant, case in (("missing_organization", "cross_organization"), ("missing_ownership", "wrong_owner"),
                          ("changed_identity", "owner_update"), ("direct_write", "reader_update")):
        step = steps[f"detect_{variant}"]
        assert step["expected_exit"] == 1 and step["expect_failure"] is True
        assert f"Violated case: {case}" in step["expected_patterns"]
        assert f"{variant}.json" in artifacts


@pytest.mark.parametrize("variant", ["baseline", "missing_organization"])
@pytest.mark.parametrize("damage", ["invalid_json", "wrong_content", "missing", "write_error"])
def test_bad_saved_observations_fail_instead_of_satisfying_an_expected_rejection(tmp_path, monkeypatch, capsys, variant, damage):
    original = Path.write_text

    def write(path, content, **kwargs):
        if damage == "write_error":
            raise OSError("unavailable")
        if damage == "missing":
            return len(content)
        return original(path, "{" if damage == "invalid_json" else "{}", **kwargs)

    monkeypatch.setattr(Path, "write_text", write)
    assert scenario.main(["--variant", variant, "--output", str(tmp_path / "report.json")]) == 2
    output = capsys.readouterr().out
    assert "Violated case:" not in output and "Fixed record checks:" not in output
