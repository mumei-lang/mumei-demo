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
    assert row["flaky"] == []
    assert row["cost_per_pass"] == 0.06


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
    assert m == {"killed": 2, "survived": 1, "invalid": 1, "score": 67}
    assert "blocks 2 of 3 scored mutants (67%)" in rg.render([], m)


def test_committed_report_is_up_to_date(capsys):
    assert rg.main(["--check"]) == 0
