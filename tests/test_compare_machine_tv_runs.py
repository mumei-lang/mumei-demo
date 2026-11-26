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


def test_changed_input_hashes_are_not_counted_as_repeat_variance():
    before = case("A")
    after = case("A")
    before["case_hash"] = "old-case"
    after["case_hash"] = "new-case"
    diff = compare.compare_reports(report([before]), report([after]))
    assert diff["summary"]["case_ids_in_both"] == 1
    assert diff["summary"]["cases_compared"] == 0
    assert diff["summary"]["verdict_changes"] == 0
    assert diff["summary"]["input_changes"] == [{
        "id": "A",
        "base": {"case_hash": "old-case", "source_hash": None},
        "repeat": {"case_hash": "new-case", "source_hash": None},
    }]


def test_unchanged_verdict_stage_time_regression_is_reported():
    before = native("accepted", "same", {"build": {"exit": 0, "seconds": 1.0, "budget_seconds": 120}})
    after = native("accepted", "same", {"build": {"exit": 0, "seconds": 1.5, "budget_seconds": 120}})
    diff = compare.compare_reports(report([case(fixed=before)]), report([case(fixed=after)]))
    assert diff["summary"]["verdict_changes"] == 0
    assert diff["summary"]["stage_changes"] == 1
    item = diff["stage_changes"][0]
    assert item["id"] == "GO01-D05" and item["variant"] == "fixed"
    assert item["stage_differences"]["build"]["seconds_delta"] == 0.5


def test_transition_counts_are_available_by_variant():
    before = native("accepted", "same")
    after = native("inconclusive", "solver unknown", failure_kind="inconclusive")
    diff = compare.compare_reports(report([case(fixed=before)]), report([case(fixed=after)]))
    assert diff["summary"]["outcome_transitions_by_variant"] == {"fixed": {"accepted->inconclusive": 1}}
    assert diff["summary"]["unresolved_group_transitions_by_variant"] == {
        "fixed": {"assurance->inconclusive": 1},
    }


def test_output_must_not_overwrite_an_input_report(tmp_path, capsys):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    original = json.dumps(report([case()]))
    first.write_text(original)
    second.write_text(original)
    assert compare.main([str(first), str(second), "--output", str(first)]) == 1
    assert first.read_text() == original
    assert "must not overwrite" in capsys.readouterr().err


def test_same_port_hashes_stay_comparable_when_case_metadata_hash_changes():
    before = case("A")
    after = case("A")
    hashes = {"buggy": "b", "fixed": "f"}
    before.update(case_hash="old", source_hash="old-native", port_hashes=hashes)
    after.update(case_hash="new", source_hash="new-native", port_hashes=hashes.copy())
    diff = compare.compare_reports(report([before]), report([after]))
    assert diff["summary"]["cases_compared"] == 1
    assert diff["summary"]["input_changes"] == []
