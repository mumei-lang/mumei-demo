from __future__ import annotations

import json

from scripts import check_machine_tv_stability as stability


def report(false_acceptance=False):
    native = {"outcome": "accepted" if false_acceptance else "source_refuted"}
    return {
        "schema_version": "mumei-demo.machine-tv-bench/v1",
        "cases": [{"id": "A", "buggy": {"z3": {"outcome": "refuted"}, "native": native}, "fixed": {"z3": {"outcome": "proven"}, "native": {"outcome": "accepted"}}}],
        "summary": {"native": {"buggy": {"outcomes": {}}, "fixed": {"outcomes": {}}}},
    }


def diff(**summary_overrides):
    summary = {
        "cases_compared": 1,
        "input_changes": [],
        "missing_in_base": [],
        "missing_in_repeat": [],
        "outcome_transitions": {},
        "unresolved_group_transitions": {},
        "stage_result_changes": 0,
        "stage_changes": 0,
        **summary_overrides,
    }
    return {"summary": summary}


def test_clean_repeat_has_no_stability_failures():
    assert stability.stability_failures(diff(), report(), report()) == []


def test_outcome_and_unresolved_group_transitions_fail():
    failures = stability.stability_failures(
        diff(outcome_transitions={"accepted->inconclusive": 1}, unresolved_group_transitions={"assurance->inconclusive": 1}),
        report(), report(),
    )
    assert any("accepted->inconclusive" in failure for failure in failures)
    assert any("assurance->inconclusive" in failure for failure in failures)


def test_input_missing_and_stage_result_changes_fail():
    failures = stability.stability_failures(
        diff(input_changes=[{"id": "A"}], missing_in_repeat=["A"], stage_result_changes=1),
        report(), report(),
    )
    assert len(failures) == 3
    assert "input identity changed" in failures[0]
    assert "case presence changed" in failures[1]
    assert "stage result changes" in failures[2]


def test_timing_only_difference_does_not_fail():
    assert stability.stability_failures(diff(stage_changes=3), report(), report()) == []


def test_false_acceptance_is_failure_independent_of_outcome_transition():
    failures = stability.stability_failures(diff(), report(False), report(True))
    assert failures == ["repeat false acceptance count is 1"]


def test_matrix_covers_representative_stability_and_gap_cases_without_expected_outcomes():
    assert set(stability.MATRIX) == {
        "GO01-D05", "RS01-D04", "RS03-D02", "PY02-D02", "GO01-D04", "PY02-D08", "RS03-D03", "GO01-D02", "PY02-D05",
    }
    assert len(stability.MATRIX) == len(set(stability.MATRIX))


def test_summary_is_bounded_and_not_a_verdict(tmp_path):
    path = tmp_path / "summary.md"
    stability.write_summary(path, diff(stage_changes=2), [])
    text = path.read_text()
    assert "not a proof grade" in text
    assert "Timing-only stage differences: 2" in text
    assert "loadavg" not in text and "environment" not in text
    json.dumps(diff())
