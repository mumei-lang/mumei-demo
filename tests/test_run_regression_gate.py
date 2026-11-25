"""Tests for scripts/run_regression_gate.py (offline)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("run_regression_gate", SCRIPTS / "run_regression_gate.py")
rg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rg)


def rec(case_id, buggy, fixed, cost=0.01):
    usage = {"cost_usd": cost, "seconds": 1.0}
    return {"id": case_id, "buggy": {"outcome": buggy, "usage": usage}, "fixed": {"outcome": fixed, "usage": usage}}


def doc(arm, runs, model="m"):
    return {"arm": arm, "model": None if arm == "mumei" else model, "runs": runs}


def test_decisions_map_outcomes_to_block_pass_and_unresolved():
    r = rec("A", "refuted", "inconclusive")
    assert rg.decision(r, "buggy") == "block"
    assert rg.decision(r, "fixed") == "unresolved"
    assert rg.decision(rec("A", "proven", "refuted"), "buggy") == "pass"


def test_gate_row_counts_regressions_and_good_changes_per_run():
    runs = [[rec("A", "refuted", "proven"), rec("B", "proven", "refuted"), rec("C", "inconclusive", "inconclusive")]] * 3
    row = rg.gate_row(doc("llm", runs))
    assert (row["regression_block"], row["regression_pass"], row["regression_unresolved"]) == (1, 1, 1)
    assert (row["keep_pass"], row["keep_block"], row["keep_unresolved"]) == (1, 1, 1)
    assert row["regression_unresolved_inconclusive"] == 1 and row["keep_unresolved_inconclusive"] == 1
    assert row["flaky"] == []
    assert row["cost_per_pass"] == 0.06


def test_unresolved_kind_uses_the_shared_failure_taxonomy():
    r = rec("A", "inconclusive", "proven")
    assert rg.unresolved_kind(r, "buggy") == "inconclusive"
    assert rg.unresolved_kind(r, "fixed") is None
    for status, expected in (("input_error", "unsupported"), ("timeout", "budget_exhausted"),
                             ("no-json (exit 2)", "environment_failure")):
        r["buggy"].update(status=status, diagnostics=[])
        assert rg.unresolved_kind(r, "buggy") == expected


def test_render_separates_unresolved_taxonomy_and_measurement_coverage():
    r = rec("A", "inconclusive", "inconclusive")
    r["buggy"].update(status="input_error", diagnostics=[], seconds=1.0, budget_seconds=5)
    r["fixed"].update(status="timeout", diagnostics=[], seconds=5.0, budget_seconds=5)
    text = rg.render([doc("mumei", [[r]])], None)
    assert "## Unresolved outcome taxonomy" in text
    assert "| mumei (hand-written ports) | — | regression | 1 | 0 | 0 | 0 |" in text
    assert "| mumei (hand-written ports) | — | keep fix | 0 | 0 | 0 | 1 |" in text
    assert "## Verification measurement" in text
    assert "| mumei (hand-written ports) | — | — | 6.0s / 2 of 2 calls | 10.0s / 2 of 2 calls |" in text


def test_measurement_cell_keeps_uninstrumented_verifier_coverage_visible():
    row = {"verification_expected_calls": 3, "verification_timed_calls": 0, "verification_seconds": 0.0,
           "verification_budgeted_calls": 0, "verification_budget_seconds": 0.0}
    assert rg.measurement_cell(row, "verification_seconds", "verification_timed_calls") == "— / 0 of 3 calls"
    row["verification_expected_calls"] = 0
    assert rg.measurement_cell(row, "verification_seconds", "verification_timed_calls") == "—"


def test_a_case_with_different_answers_across_runs_is_flaky():
    runs = [[rec("A", "refuted", "proven"), rec("B", "refuted", "proven")],
            [rec("A", "refuted", "proven"), rec("B", "proven", "proven")]]
    assert rg.flaky_cases(doc("mumei-llm", runs)) == ["B"]


def test_mumei_gate_has_no_model_cost_and_no_flakiness_column():
    text = rg.render([doc("mumei", [[rec("A", "refuted", "proven")]])], None)
    assert "| mumei (hand-written ports) | — | 1 | 1 | 0 | 0 | 0 | 0 | — | $0 (no model) |" in text


def test_other_arms_are_left_out_of_the_gate():
    text = rg.render([doc("llm-contract", [[rec("A", "refuted", "proven")]])], None)
    assert "llm-contract" not in text and "| LLM review" not in text


def test_every_model_of_an_arm_gets_its_own_row():
    docs = [{**doc("llm", [[rec("A", "refuted", "proven")]]), "model": m} for m in ("m-1", "m-2")]
    text = rg.render(docs, None)
    assert "| m-1 |" in text and "| m-2 |" in text


def test_flaky_cases_are_listed_by_id():
    runs = [[rec("X1", "refuted", "proven")], [rec("X1", "inconclusive", "proven")]]
    assert "Flaky under mumei + LLM port: `X1`." in rg.render([doc("mumei-llm", runs)], None)


def test_mutation_summary_scores_killed_over_scored():
    m = rg.mutation_summary({"cases": [{"mutants": [{"outcome": "killed"}, {"outcome": "survived"},
                                                    {"outcome": "killed"}, {"outcome": "invalid"}]}]})
    assert m == {"killed": 2, "survived": 1, "invalid": 1, "unsupported": 0, "inconclusive": 1,
                 "environment_failure": 0, "budget_exhausted": 0, "score": 67}
    text = rg.render([], m)
    assert "blocks 2 of 3 scored mutants (67%)" in text
    assert "1 do not verify either way: 0 unsupported, 1 residual inconclusive" in text


def test_mutation_summary_separates_invalid_failure_kinds():
    m = rg.mutation_summary({"cases": [{"mutants": [
        {"outcome": "invalid", "status": "input_error", "message": ""},
        {"outcome": "invalid", "status": "timeout", "message": ""},
        {"outcome": "invalid", "status": "no-json (exit 2)", "message": ""},
    ]}]})
    assert (m["unsupported"], m["budget_exhausted"], m["environment_failure"], m["inconclusive"]) == (1, 1, 1, 0)


def test_committed_report_is_up_to_date(capsys):
    assert rg.main(["--check"]) == 0
