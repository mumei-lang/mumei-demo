from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_evidence_regressions import CASES, mutate, relocate, run_suite
from scenario_evidence import load_result
from test_scenario_evidence import evidence  # noqa: F401


def test_matrix_saves_each_negative_reader_result_and_preserves_original(evidence):
    data, _, _, root = evidence
    original = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    output = root.parent / (root.name + "-regressions")
    summary = run_suite(root / "result.json", output)
    assert summary["status"] == "PASS"
    assert summary["kind"] == "synthetic_artifact_mutations"
    assert [row["case"] for row in summary["cases"]] == list(CASES)
    assert all(row["matched"] for row in summary["cases"])
    for row in summary["cases"]:
        saved = json.loads((output / row["case"] / "reader_result.json").read_text())
        assert saved["overall_status"] == row["actual_status"]
        if row["case"] not in {"unchanged", "existing_failure"}:
            assert row["issues"]
    assert load_result(root / "result.json")["overall_status"] == "PASS"
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == original


@pytest.mark.parametrize("failure", ["legacy", "failed", "missing", "tampered", "corrupt"])
def test_invalid_initial_report_cannot_become_a_successful_regression_suite(evidence, failure):
    data, _, _, root = evidence
    if failure == "legacy":
        for key in ("evidence_requirements", "evidence_summary", "evidence_identities"):
            data.pop(key, None)
    elif failure == "failed":
        data["overall_status"] = "FAIL"
    elif failure == "missing":
        (root / "proof.json").unlink()
    elif failure == "tampered":
        (root / "book.json").write_text("{}")
    (root / "result.json").write_text("{" if failure == "corrupt" else json.dumps(data))
    output = root.parent / (root.name + "-regressions")
    summary = run_suite(root / "result.json", output)
    assert summary["status"] == "FAIL"
    assert summary["cases"] == []
    assert summary["error"]
    assert (output / "summary.json").is_file()


@pytest.mark.parametrize("location", ["input", "child", "ancestor"])
def test_output_cannot_overwrite_or_recursively_copy_the_input(evidence, location):
    _, _, _, root = evidence
    output = {"input": root, "child": root / "nested", "ancestor": root.parent}[location]
    with pytest.raises(ValueError, match="separate"):
        run_suite(root / "result.json", output)


def test_output_cannot_overwrite_existing_artifacts(evidence):
    _, _, _, root = evidence
    output = root.parent / (root.name + "-regressions")
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("existing result")
    with pytest.raises(ValueError, match="empty"):
        run_suite(root / "result.json", output)
    assert marker.read_text() == "existing result"


@pytest.mark.parametrize("case,key", [("direct_dependency", "direct_unresolved_dependencies"), ("transitive_dependency", "transitive_unresolved_dependencies")])
def test_high_grade_does_not_mask_the_missing_dependency_reason(evidence, case, key):
    data, _, _, root = evidence
    mutate(case, data, root)
    (root / "result.json").write_text(json.dumps(data))
    summary = load_result(root / "result.json")["evidence_summary"]
    assert summary["status"] == "incomplete"
    claim = summary["claims"][0]
    assert claim["effective_grade"] == "G4"
    assert claim["dependency_coverage"][key] == ["__regression_missing_dependency__"]


def test_relocation_only_changes_absolute_paths_within_the_original_root():
    value = {"files": ["/old/a", "/old-other/b", "relative.mm", {"path": "/old/nested/c"}]}
    assert relocate(value, Path("/old"), Path("/new")) == {"files": ["/new/a", "/old-other/b", "relative.mm", {"path": "/new/nested/c"}]}


def test_unknown_case_is_not_a_passing_noop(evidence):
    data, _, _, root = evidence
    with pytest.raises(ValueError, match="unknown"):
        mutate("typo", copy.deepcopy(data), root)
