"""Tests for scripts/check_scenario_contracts.py docs alias checking."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_scenario_contracts import (
    FORBIDDEN_ALIAS_PATTERNS,
    _check_docs_forbidden_aliases,
    _in_code_fence,
    _is_key_context,
    _validate_claim_book,
    _validate_charter_gate,
    _validate_negative_controls,
    _validate_test_observations,
)


def test_is_key_context_backtick():
    assert _is_key_context("`recommendations`", "recommendations")
    assert _is_key_context("Use `audit_issues` key", "audit_issues")


def test_is_key_context_json_key():
    assert _is_key_context('"recommendations": [', "recommendations")
    assert _is_key_context("'actions': []", "actions")


def test_is_key_context_yaml_key():
    assert _is_key_context("- recommendations:", "recommendations")
    assert _is_key_context("  actions:", "actions")


def test_is_key_context_plain_prose_rejected():
    assert not _is_key_context(
        "We have some recommendations for improvement.", "recommendations"
    )
    assert not _is_key_context(
        "The next actions should be taken.", "actions"
    )


def test_is_key_context_array_notation():
    assert _is_key_context("recommendations[]", "recommendations")


def test_claim_book_shape_validation():
    assert _validate_claim_book(
        {"source": "{root_dir}/scenario.mm", "cert": "scenario.proof.json"},
        "$.l1_z3.steps[0].claim_book",
    ) == []

    assert _validate_claim_book(None, "$.claim_book")
    assert "missing `source`" in _validate_claim_book(
        {"cert": "scenario.proof.json"}, "$.claim_book"
    )[0]
    assert "missing `cert`" in _validate_claim_book(
        {"source": "scenario.mm"}, "$.claim_book"
    )[0]
    assert "source must be a string" in _validate_claim_book(
        {"source": 1, "cert": "scenario.proof.json"}, "$.claim_book"
    )[0]
    assert "cert must be a string" in _validate_claim_book(
        {"source": "scenario.mm", "cert": None}, "$.claim_book"
    )[0]
    assert "file name" in _validate_claim_book(
        {"source": "scenario.mm", "cert": "nested/scenario.proof.json"},
        "$.claim_book",
    )[0]
    assert "file name" in _validate_claim_book(
        {"source": "scenario.mm", "cert": "../scenario.proof.json"},
        "$.claim_book",
    )[0]


def test_charter_gate_must_be_boolean_true():
    assert _validate_charter_gate(True, "$.charter_gate") == []
    for value in (False, 1, "true", None, {}):
        failures = _validate_charter_gate(value, "$.charter_gate")
        assert failures == ["$.charter_gate must be the boolean true"]


def test_negative_controls_flag_must_be_boolean():
    assert _validate_negative_controls(True, "$.negative_controls") == []
    assert _validate_negative_controls(False, "$.negative_controls") == []
    for value in (1, "true", None, {}, []):
        failures = _validate_negative_controls(value, "$.negative_controls")
        assert failures == ["$.negative_controls must be a boolean"]


def test_test_observations_flag_accepts_valid_shape_and_rejects_invalid_shapes():
    valid = {
        "report": "observe.json",
        "expected_results": [{
            "target": "late_fee",
            "test": "test_example",
            "file_suffix": "test_late_fee.py",
            "verdict": "contradicts_ensures",
        }],
        "forbidden_verdicts": ["requires_admits_rejected"],
        "expected_totals": {"consistent": 2, "contradicts_ensures": 1},
    }
    assert _validate_test_observations(valid, "$.test_observations") == []

    for value in (
        None,
        {"report": ""},
        {"report": "../outside.json"},
        {"report": "observe.json", "expected_results": [{"test": "example"}]},
        {"report": "observe.json", "forbidden_verdicts": "contradicts_ensures"},
        {"report": "observe.json", "expected_totals": {"consistent": True}},
        {"report": "observe.json", "unexpected": True},
    ):
        assert _validate_test_observations(value, "$.test_observations")


def test_test_observation_demo_runs_agent_commands_from_repo_with_absolute_paths():
    scenario_path = (
        Path(__file__).resolve().parents[1]
        / "scenarios"
        / "test_observation_demo"
        / "scenario.json"
    )
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    agent_steps = [
        step
        for layer_name in scenario["layers"]
        for step in scenario[layer_name]["steps"]
        if step.get("repo") == "mumei-agent"
    ]

    assert agent_steps
    assert all(step.get("cwd") == "{mumei_agent_repo}" for step in agent_steps)
    expected_paths = {
        "harvest_tests": [
            "{output_dir}/project/test_late_fee.py",
            "{output_dir}/project/late_fee.py",
            "{output_dir}/project/late_fee.rs",
        ],
        "observe_wrong": [
            "{output_dir}/project/wrong_spec.json",
            "{output_dir}/project/test_late_fee.py",
            "{output_dir}/project/late_fee.py",
            "{output_dir}/project/late_fee.rs",
        ],
        "observe_aligned": [
            "{output_dir}/project/aligned_spec.json",
            "{output_dir}/project/test_late_fee.py",
            "{output_dir}/project/late_fee.py",
            "{output_dir}/project/late_fee.rs",
        ],
    }
    steps_by_id = {step["id"]: step for step in agent_steps}
    for step_id, paths in expected_paths.items():
        command = steps_by_id[step_id]["command"]
        assert all(path in command for path in paths)


def test_in_code_fence_detection():
    lines = [
        "normal text",
        "```json",
        '  "actions": []',
        "```",
        "normal again",
    ]
    assert not _in_code_fence(lines, 0)
    assert not _in_code_fence(lines, 1)
    assert _in_code_fence(lines, 2)
    assert _in_code_fence(lines, 3)
    assert not _in_code_fence(lines, 4)


def test_docs_check_detects_alias_in_code_fence(tmp_path, monkeypatch):
    doc = tmp_path / "test.md"
    doc.write_text(
        "# Title\n\n```json\n\"recommendations\": []\n```\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "check_scenario_contracts.DOCS_UNDER_CONTRACT", [doc]
    )
    monkeypatch.setattr("check_scenario_contracts.REPO_ROOT", tmp_path)
    failures = _check_docs_forbidden_aliases()
    assert len(failures) == 1
    assert "recommendations" in failures[0]


def test_docs_check_ignores_plain_prose(tmp_path, monkeypatch):
    doc = tmp_path / "test.md"
    doc.write_text(
        "# Title\n\nWe have some recommendations for the team.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "check_scenario_contracts.DOCS_UNDER_CONTRACT", [doc]
    )
    monkeypatch.setattr("check_scenario_contracts.REPO_ROOT", tmp_path)
    failures = _check_docs_forbidden_aliases()
    assert failures == []


def test_docs_check_detects_backtick_alias(tmp_path, monkeypatch):
    doc = tmp_path / "test.md"
    doc.write_text(
        "# Title\n\nUse `verification_gaps` for issues.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "check_scenario_contracts.DOCS_UNDER_CONTRACT", [doc]
    )
    monkeypatch.setattr("check_scenario_contracts.REPO_ROOT", tmp_path)
    failures = _check_docs_forbidden_aliases()
    assert len(failures) == 1
    assert "verification_gaps" in failures[0]
