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
    doc = diff(stage_changes=1)
    doc["stage_changes"] = [{"stage_differences": {"build": {"base_status": "ok", "repeat_status": "ok"}}}]
    stability.write_summary(path, doc, [])
    text = path.read_text()
    assert "not a proof grade" in text
    assert "Timing-only stage differences: 1" in text
    assert "loadavg" not in text and "environment" not in text
    json.dumps(diff())


def valid_report(case_id="A"):
    return {
        "schema_version": "mumei-demo.machine-tv-bench/v1",
        "recorded_at": "2026-01-01T00:00:00+00:00",
        "cases": [{
            "id": case_id,
            "case_hash": "same",
            "source_hash": "same",
            "buggy": {"z3": {"outcome": "refuted"}, "native": {"outcome": "source_refuted", "reason": "refuted", "stages": {}}},
            "fixed": {"z3": {"outcome": "proven"}, "native": {"outcome": "accepted", "reason": "checked", "stages": {}}},
        }],
        "summary": {"native": {"buggy": {"outcomes": {"accepted": 0}}, "fixed": {"outcomes": {"accepted": 1}}}},
    }


def test_main_writes_repeat_artifacts_for_stable_reports(monkeypatch, tmp_path, capsys):
    def fake_run(binary, output, jobs, timeout):
        output.write_text(json.dumps(valid_report()))

    monkeypatch.setattr(stability, "run_benchmark", fake_run)
    assert stability.main(["--mumei-bin", "/fake/mumei", "--output-dir", str(tmp_path)]) == 0
    assert (tmp_path / "machine_tv_base.json").is_file()
    assert (tmp_path / "machine_tv_repeat.json").is_file()
    diff_doc = json.loads((tmp_path / "machine_tv_diff.json").read_text())
    assert diff_doc["summary"]["verdict_changes"] == 0
    assert "not a proof grade" in (tmp_path / "summary.md").read_text()
    assert '"failures": []' in capsys.readouterr().out


def test_main_returns_failure_when_repeat_outcome_changes(monkeypatch, tmp_path):
    def fake_run(binary, output, jobs, timeout):
        doc = valid_report()
        if output.name == "machine_tv_repeat.json":
            doc["cases"][0]["fixed"]["native"]["outcome"] = "inconclusive"
        output.write_text(json.dumps(doc))

    monkeypatch.setattr(stability, "run_benchmark", fake_run)
    assert stability.main(["--mumei-bin", "/fake/mumei", "--output-dir", str(tmp_path)]) == 1
    assert "accepted->inconclusive" in (tmp_path / "machine_tv_diff.json").read_text()


def test_run_benchmark_repeats_only_flags_and_raises_on_failure(monkeypatch):
    calls = []

    def fake_run(cmd, cwd, capture_output, text):
        calls.append(cmd)
        return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "failed"})()

    monkeypatch.setattr(stability.subprocess, "run", fake_run)
    try:
        stability.run_benchmark("/fake/mumei", stability.REPO_ROOT / "out.json", 2, 30)
    except RuntimeError as exc:
        assert "failed" in str(exc)
    else:
        raise AssertionError("expected failure")
    cmd = calls[0]
    assert cmd.count("--only") == len(stability.MATRIX)
    assert all(case_id in cmd for case_id in stability.MATRIX)
    assert "--jobs" in cmd and "2" in cmd and "--timeout" in cmd and "30" in cmd


def test_stage_status_difference_is_not_reported_as_timing_only():
    doc = diff(stage_changes=1)
    doc["stage_changes"] = [{
        "id": "A",
        "variant": "fixed",
        "stage_differences": {"build": {"base_status": "ok", "repeat_status": "failed"}},
    }]
    assert stability.stability_failures(doc, report(), report()) == []
    assert stability.timing_only_stage_changes(doc) == 0
    doc["stage_changes"][0]["stage_differences"]["build"]["repeat_status"] = "ok"
    assert stability.timing_only_stage_changes(doc) == 1


def test_same_outcome_diagnostic_change_is_not_an_outcome_transition():
    doc = diff(outcome_transitions={"inconclusive->inconclusive": 1},
               unresolved_group_transitions={"inconclusive->inconclusive": 1})
    assert stability.stability_failures(doc, report(), report()) == []
    assert stability.changed_transitions({"accepted->inconclusive": 1, "inconclusive->inconclusive": 2}) == {
        "accepted->inconclusive": 1,
    }


def test_main_resolves_relative_output_dir_before_child_runs(monkeypatch, tmp_path):
    seen = []

    def fake_run(binary, output, jobs, timeout):
        seen.append(output)
        output.write_text(json.dumps(valid_report()))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(stability, "run_benchmark", fake_run)
    assert stability.main(["--mumei-bin", "/fake/mumei", "--output-dir", "relative-out"]) == 0
    assert all(path.is_absolute() for path in seen)
    assert (tmp_path / "relative-out/machine_tv_diff.json").is_file()


def test_stability_step_runs_after_existing_integration_validation_with_always_condition():
    workflow = (stability.REPO_ROOT / ".github/workflows/integration.yml").read_text()
    assert workflow.index("Run integrated demo scenarios") < workflow.index("Check focused machine-TV repeat stability")
    assert workflow.index("Check planner selection-policy regression") < workflow.index("Check focused machine-TV repeat stability")
    assert workflow.index("Check separate record model and execution evidence") < workflow.index("Check focused machine-TV repeat stability")
    assert "- name: Check focused machine-TV repeat stability\n        if: always()" in workflow
    assert 'if [ ! -x "$MUMEI_BIN" ]; then' in workflow
