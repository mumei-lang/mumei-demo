from __future__ import annotations

import json

import pytest

from scripts import compare_machine_tv_runs as compare


def native(outcome, reason="reason", stages=None, failure_kind=None):
    result = {"outcome": outcome, "reason": reason, "stages": stages or {}}
    if failure_kind:
        result["failure_kind"] = failure_kind
    return result


def case(case_id="GO01-D05", fixed=None, buggy=None):
    return {
        "id": case_id,
        "fixed": {"native": fixed or native("accepted", "checked_source_machine_tv_within_profile")},
        "buggy": {"native": buggy or native("source_refuted", "source verification failed")},
    }


def report(cases, schema="mumei-demo.machine-tv-bench/v1"):
    return {"schema_version": schema, "recorded_at": "2026-11-25T00:00:00+00:00", "cases": cases}


def test_unchanged_reports_have_no_case_or_stage_diffs():
    diff = compare.compare_reports(report([case()]), report([case()]))
    assert diff["summary"]["cases_compared"] == 1
    assert diff["summary"]["verdict_changes"] == 0
    assert diff["summary"]["stage_result_changes"] == 0
    assert diff["changes"] == []


def test_acceptance_change_is_split_by_variant_reason_and_stage():
    before = native(
        "accepted",
        "checked_source_machine_tv_within_profile",
        {"build": {"exit": 0, "seconds": 1.0, "budget_seconds": 120},
         "accept_object": {"exit": 0, "seconds": 2.0, "budget_seconds": 120}},
    )
    after = native(
        "inconclusive",
        "machine_tv_needs_profile_diagnosis",
        {"build": {"exit": 0, "seconds": 1.2, "budget_seconds": 120},
         "accept_object": {"exit": 3, "seconds": 4.0, "budget_seconds": 120}},
        failure_kind="inconclusive",
    )
    diff = compare.compare_reports(report([case(fixed=before)]), report([case(fixed=after)]))
    assert diff["summary"]["verdict_changes"] == 1
    assert diff["summary"]["verdict_changes_by_variant"] == {"fixed": 1}
    assert diff["summary"]["outcome_transitions"] == {"accepted->inconclusive": 1}
    assert diff["summary"]["unresolved_group_transitions"] == {"assurance->inconclusive": 1}
    assert diff["summary"]["stage_result_changes"] == 1
    change = diff["changes"][0]
    assert change["classification"] == "acceptance_changed"
    assert change["base"]["reason"] == "checked_source_machine_tv_within_profile"
    assert change["repeat"]["failure_kind"] == "inconclusive"
    assert change["stage_differences"]["accept_object"]["base_status"] == "ok"
    assert change["stage_differences"]["accept_object"]["repeat_status"] == "failed"
    assert change["stage_differences"]["accept_object"]["seconds_delta"] == 2.0


def test_missing_cases_are_reported_not_compared():
    diff = compare.compare_reports(report([case("A")]), report([case("B")]))
    assert diff["summary"]["cases_compared"] == 0
    assert diff["summary"]["missing_in_base"] == ["B"]
    assert diff["summary"]["missing_in_repeat"] == ["A"]
    assert diff["changes"] == []


def test_load_report_rejects_other_json(tmp_path):
    path = tmp_path / "not-machine-tv.json"
    path.write_text(json.dumps({"schema_version": "other", "cases": []}))
    with pytest.raises(ValueError, match="machine-tv-bench"):
        compare.load_report(path)
