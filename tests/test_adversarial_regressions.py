from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_adversarial_port_corpus as adversarial  # noqa: E402
import check_fixed_alarm_regression as fixed_alarm  # noqa: E402
import run_port_divergence as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_committed_adversarial_corpus_is_valid_and_passes() -> None:
    result = adversarial.evaluate_corpus(adversarial.load_corpus())

    assert result["summary"]["failed"] == 0
    assert result["summary"]["total"] >= 8
    assert set(result["summary"]["by_failure_mode"]) == set(adversarial.FAILURE_MODES)
    assert all(row["cases"] > 0 for row in result["summary"]["by_failure_mode"].values())


def test_committed_adversarial_report_is_up_to_date() -> None:
    result = adversarial.evaluate_corpus(adversarial.load_corpus())

    assert (REPO_ROOT / "proofs" / "ADVERSARIAL.md").read_text(encoding="utf-8") == adversarial.render(result)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda doc: doc["cases"][0].update(kind="snapshot"), "kind must be"),
        (lambda doc: doc["cases"][0].pop("reference_body"), "missing required keys"),
        (lambda doc: doc["cases"][0].update(failure_mode="unknown"), "unknown failure_mode"),
        (lambda doc: doc["cases"][0].update(fixed_reference_body=3), "fixed_reference_body must be a string"),
        (lambda doc: doc["cases"].append(dict(doc["cases"][0])), "duplicate case id"),
        (lambda doc: doc.update(failure_modes=["weak_spec"]), "exactly cover"),
    ],
)
def test_adversarial_corpus_validation_rejects_bad_shapes(mutation, message: str) -> None:
    doc = json.loads((REPO_ROOT / "proofs" / "adversarial" / "intent-fidelity-corpus.json").read_text(encoding="utf-8"))
    mutation(doc)

    errors = adversarial.validate_corpus(doc)

    assert any(message in error for error in errors), errors


def test_adversarial_report_relative_path_write_and_check_diagnostic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    report = Path("custom") / "adversarial.md"

    assert adversarial.main(["--report", str(report)]) == 0
    assert report.is_file()
    assert "wrote custom/adversarial.md" in capsys.readouterr().out

    report.write_text("stale", encoding="utf-8")
    assert adversarial.main(["--report", str(report), "--check"]) == 1
    assert "custom/adversarial.md is out of date" in capsys.readouterr().err


def test_adversarial_evaluator_marks_mismatched_findings_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = adversarial.load_corpus()
    case = next(case for case in doc["cases"] if case["id"] == "faithful-port-negative-control")
    monkeypatch.setattr(
        adversarial.fidelity,
        "lint_findings",
        lambda *_args: [{"kind": "added_guard", "message": "possible added guard"}],
    )

    row = adversarial.evaluate_case(case)

    assert row["status"] == "fail"
    assert row["expected"] == []
    assert row["actual"] == ["added_guard"]


def _lint_case(reference: str, fixed: str | None = None) -> dict:
    header = "atom divide(numerator: i64, denominator: i64) -> Checked\n    requires: true;\n    ensures: result.ok => result.value >= 0;\n    "
    case = {
        "id": "X",
        "atom": "divide",
        "header": header,
        "prelude": "",
        "language": "rust",
        "category": "division-by-zero",
        "functions": {"buggy": "fn divide(numerator: i64, denominator: i64) -> i64 { numerator / denominator }"},
    }
    case["ports"] = {
        "buggy": pd.bench.assemble(case, reference),
        "fixed": pd.bench.assemble(case, fixed if fixed is not None else reference),
    }
    return case


def test_silent_repair_matching_is_exact_after_comments_and_whitespace() -> None:
    buggy = "numerator / denominator"
    fixed = "if denominator <= 0 { 0 } else { numerator / denominator }"
    case = _lint_case(buggy, fixed)

    assert [finding["kind"] for finding in pd.lint_findings(case, "  if denominator <= 0 { 0 } else { numerator / denominator }  // noise")] == ["silent_repair"]
    assert [finding["kind"] for finding in pd.lint_findings(case, "if denominator < 0 { 0 } else { numerator / denominator }")] == ["added_guard"]
    assert pd.lint_findings(case, buggy) == []


def test_result_state_folding_is_not_limited_to_success_contracts() -> None:
    reference = "if transfer_ok { Payout { ok: true, owed: 0 } } else { Payout { ok: false, owed: amount } }"
    case = _lint_case(reference)
    case["header"] = case["header"].replace("result.ok => result.value >= 0", "result.owed >= 0")
    case["functions"]["fixed"] = case["functions"]["buggy"]
    case["ports"] = {"buggy": pd.bench.assemble(case, reference), "fixed": pd.bench.assemble(case, reference)}
    folded = "Payout { ok: transfer_ok, owed: amount }"

    kinds = [finding["kind"] for finding in pd.lint_findings(case, folded, "fixed")]

    assert "guard_folding" in kinds


def test_guard_folding_needs_reference_failure_semantics() -> None:
    reference = "if denominator == 0 { Checked { ok: false, value: 0 } } else { Checked { ok: true, value: numerator / denominator } }"
    case = _lint_case(reference)
    folded = "if denominator > 0 { Checked { ok: true, value: numerator / denominator } } else { Checked { ok: true, value: 0 } }"

    assert [finding["kind"] for finding in pd.lint_findings(case, folded)] == ["guard_folding"]
    assert pd.lint_findings(case, reference) == []


@pytest.mark.parametrize(
    ("requires", "ensures", "expected"),
    [
        ("false", "result >= 0", ["vacuous_spec"]),
        ("days > 0 && days < 0", "result >= 0", ["vacuous_spec"]),
        ("days > 0 && !(days > 0)", "result >= 0", ["vacuous_spec"]),
        ("days >= 0 && days <= 0", "result >= 0", []),
        ("(ready && !ready)", "result >= 0", ["vacuous_spec"]),
        ("(days > 0 && days < 0)", "result >= 0", ["vacuous_spec"]),
        ("days > 0 || days < 0", "result >= 0", []),
        ("(days > 0 || days < 0) && total >= 0", "result >= 0", []),
        ("days >= 0", "true", ["weak_spec"]),
        ("days >= 0", "(result == result) && true", ["weak_spec"]),
        ("days >= 0", "((result == result) && true)", ["weak_spec"]),
        ("days >= 0", "prior_result >= 0", ["weak_spec"]),
        ("days >= 0", "result2 >= 0", ["weak_spec"]),
        ("days >= 0", "days > 0 => result == total / days", []),
        ("days >= 0", "result >= 0", []),
    ],
)
def test_contract_lint_matrix(requires: str, ensures: str, expected: list[str]) -> None:
    assert [finding["kind"] for finding in pd.lint_contract(requires, ensures)] == expected


# --- fixed-alarm regression gate ---------------------------------------------


def _write_budget(path: Path, false_alarms: int = 1, unreviewed: int = 0, specimens: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": fixed_alarm.BUDGET_SCHEMA,
        "mode": "no_llm",
        "max_false_alarms": false_alarms,
        "max_unreviewed": unreviewed,
        "min_specimens": specimens,
        "notes": "test",
    }), encoding="utf-8")


def _write_fixed_tree(root: Path, *, false_alarms: int = 1, unreviewed: int = 0, specimens: int = 1) -> None:
    for index in range(specimens):
        path = root / "python" / f"py-{index:02d}-x" / "audit" / "coverage.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "specimen": f"py-{index:02d}-x",
            "fixed": {
                "false_alarms": false_alarms,
                "still_reported": [],
                "finding_counts": {"total": false_alarms, "real": 0, "unreviewed": unreviewed},
            },
        }), encoding="utf-8")


def _write_history(path: Path, *, false_alarms: int = 1, specimens: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"runs": [
        {"llm": True, "fixed": {"specimens": specimens, "findings": 99, "real": 0, "false_alarms": 99, "still_reported": 0}},
        {"llm": False, "fixed": {"specimens": specimens, "findings": false_alarms, "real": 0, "false_alarms": false_alarms, "still_reported": 0}},
    ]}), encoding="utf-8")


def test_fixed_alarm_gate_passes_committed_artifacts() -> None:
    result = fixed_alarm.evaluate()

    assert result["status"] == "pass"
    assert 0 <= result["total"]["false_alarms"] <= result["budget"]["max_false_alarms"]
    assert 0 <= result["total"]["unreviewed"] <= result["budget"]["max_unreviewed"]
    assert result["history_comparison"] == "match"
    assert bool(result["top_offenders"]) == (result["total"]["false_alarms"] > 0)
    assert all(row["false_alarms"] > 0 for row in result["top_offenders"])


def test_fixed_alarm_gate_counts_multiple_specimens(tmp_path: Path) -> None:
    root = tmp_path / "specimens"
    _write_fixed_tree(root, false_alarms=2, unreviewed=1, specimens=2)
    _write_history(tmp_path / "history.json", false_alarms=4, specimens=2)
    _write_budget(tmp_path / "budget.json", false_alarms=4, unreviewed=2, specimens=2)

    result = fixed_alarm.evaluate(root, tmp_path / "history.json", tmp_path / "budget.json")

    assert result["status"] == "pass"
    assert result["total"] == {
        "specimens": 2,
        "false_alarms": 4,
        "findings": 4,
        "real": 0,
        "unreviewed": 2,
        "still_reported": 0,
    }


def test_fixed_alarm_gate_allows_zero_false_alarms(tmp_path: Path) -> None:
    root = tmp_path / "specimens"
    _write_fixed_tree(root, false_alarms=0, unreviewed=0, specimens=1)
    _write_history(tmp_path / "history.json", false_alarms=0, specimens=1)
    _write_budget(tmp_path / "budget.json", false_alarms=0, unreviewed=0, specimens=1)

    result = fixed_alarm.evaluate(root, tmp_path / "history.json", tmp_path / "budget.json")

    assert result["status"] == "pass"
    assert result["top_offenders"] == []


@pytest.mark.parametrize(
    ("budget", "fragment"),
    [
        ({"false_alarms": 0, "unreviewed": 0, "specimens": 1}, "false alarms regressed: 1 > budget 0"),
        ({"false_alarms": 1, "unreviewed": -1, "specimens": 1}, "must be a non-negative integer"),
        ({"false_alarms": 1, "unreviewed": 0, "specimens": 2}, "expected at least 2"),
    ],
)
def test_fixed_alarm_gate_budget_failures(tmp_path: Path, budget: dict, fragment: str) -> None:
    root = tmp_path / "specimens"
    _write_fixed_tree(root, false_alarms=1, unreviewed=0, specimens=1)
    _write_history(tmp_path / "history.json", false_alarms=1, specimens=1)
    if budget["unreviewed"] < 0:
        budget_path = tmp_path / "budget.json"
        budget_path.write_text(json.dumps({
            "schema": fixed_alarm.BUDGET_SCHEMA,
            "mode": "no_llm",
            "max_false_alarms": budget["false_alarms"],
            "max_unreviewed": budget["unreviewed"],
            "min_specimens": budget["specimens"],
            "notes": "test",
        }), encoding="utf-8")
        with pytest.raises(ValueError, match="non-negative integer"):
            fixed_alarm.evaluate(root, tmp_path / "history.json", budget_path)
        return
    _write_budget(tmp_path / "budget.json", **budget)

    result = fixed_alarm.evaluate(root, tmp_path / "history.json", tmp_path / "budget.json")

    assert result["status"] == "fail"
    assert any(fragment in error for error in result["errors"])


def test_fixed_alarm_gate_detects_history_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "specimens"
    _write_fixed_tree(root, false_alarms=2, specimens=1)
    _write_history(tmp_path / "history.json", false_alarms=1, specimens=1)
    _write_budget(tmp_path / "budget.json", false_alarms=2, specimens=1)

    result = fixed_alarm.evaluate(root, tmp_path / "history.json", tmp_path / "budget.json")

    assert result["status"] == "fail"
    assert result["history_comparison"] == "mismatch"
    assert any("coverage 2 != history 1" in error for error in result["errors"])


def test_fixed_alarm_json_cli_is_serializable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "specimens"
    _write_fixed_tree(root, false_alarms=1, specimens=1)
    _write_history(tmp_path / "history.json", false_alarms=1, specimens=1)
    _write_budget(tmp_path / "budget.json", false_alarms=1, specimens=1)

    assert fixed_alarm.main([
        "--root", str(root),
        "--history", str(tmp_path / "history.json"),
        "--budget", str(tmp_path / "budget.json"),
        "--json",
    ]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["status"] == "pass"
    assert output["top_offenders"][0]["specimen"] == "py-00-x"
    assert "path" not in output["top_offenders"][0]
    assert "path" not in output["rows"][0]


def test_fixed_alarm_gate_rejects_wrong_budget_mode(tmp_path: Path) -> None:
    budget = tmp_path / "budget.json"
    budget.write_text(json.dumps({
        "schema": fixed_alarm.BUDGET_SCHEMA,
        "mode": "with_llm",
        "max_false_alarms": 0,
        "max_unreviewed": 0,
        "min_specimens": 0,
        "notes": "test",
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="deterministic no-LLM"):
        fixed_alarm.load_budget(budget)
