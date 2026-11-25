"""Tests for scripts/run_mutation_control.py (offline; Mumei is stubbed)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("run_mutation_control", SCRIPTS / "run_mutation_control.py")
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)

BODY = "body: {\n        if days <= 0 { 0 } else { total / days }\n    }\n"
CASES, CASE_ERRORS = mc.cb.load_cases()


def ops(body):
    return [(m["op"], m["from"], m["to"]) for m in mc.mutants(body)]


@pytest.mark.parametrize("body, expected", [
    ("a < b", [("relational", "<", "<=")]),
    ("a <= b", [("relational", "<=", "<")]),
    ("a > b", [("relational", ">", ">=")]),
    ("a >= b", [("relational", ">=", ">")]),
    ("a == b", [("relational", "==", "!=")]),
    ("a != b", [("relational", "!=", "==")]),
    ("a && b", [("logical", "&&", "||")]),
    ("a || b", [("logical", "||", "&&")]),
    ("a + b", [("arithmetic", "+", "-")]),
    ("a - b", [("arithmetic", "-", "+")]),
    ("a + 9", [("arithmetic", "+", "-"), ("constant", "9", "10")]),
    ("a => b", []),
    ("f(a) -> i64", []),
    ("x1 + y22", [("arithmetic", "+", "-")]),
    ("a * b / c % d", []),
    ("a // b < c\n", []),
    ("a < b // c > d\nx >= 0", [("relational", "<", "<="), ("relational", ">=", ">"), ("constant", "0", "1")]),
    ("", []),
    ("while i < n\n    invariant: i >= 0 && i <= n\n    decreases: n - i\n    { i = i + 1; }",
     [("relational", "<", "<="), ("arithmetic", "+", "-"), ("constant", "1", "2")]),
])
def test_mutation_operators(body, expected):
    assert ops(body) == expected


def test_mutants_drop_duplicates_and_keep_source_order():
    got = mc.mutants("a < b && a < b")
    assert [m["at"] for m in got] == [2, 6, 11]
    assert len({mc.apply("a < b && a < b", m) for m in got}) == len(got)


def test_apply_round_trips_every_mutant():
    for m in mc.mutants(BODY):
        text = mc.apply(BODY, m)
        assert text != BODY and text[:m["at"]] == BODY[:m["at"]]
        assert text[m["at"]:].startswith(m["to"])


def test_apply_refuses_a_stale_offset():
    with pytest.raises(AssertionError):
        mc.apply("a < b", {"op": "relational", "at": 0, "from": "<", "to": "<="})


def test_body_mutants_leave_prelude_and_contract_alone():
    case = next(c for c in CASES if c["id"] == "PY01-D08")
    head, body = mc.split_fixed(case)
    assert "requires:" in head and "requires:" not in body
    assert all(m["at"] < len(body) for m in mc.mutants(body))


def test_every_benchmark_port_has_mutants_that_apply():
    assert not CASE_ERRORS
    total = 0
    for c in CASES:
        _, body = mc.split_fixed(c)
        for m in mc.mutants(body):
            mc.apply(body, m)
            total += 1
    assert total > len(CASES)


def fake_verify(rule):
    fixed = {c["ports"]["fixed"] for c in CASES}

    def verify(_bin, text, _timeout):
        outcome = "proven" if text in fixed else rule(text)
        return {"outcome": outcome, "status": outcome,
                "diagnostics": [{"message": f"Verification Error: {outcome}\nmore"}] if outcome != "proven" else []}
    return verify


@pytest.mark.parametrize("outcome, expected", [("refuted", "killed"), ("proven", "survived"),
                                               ("inconclusive", "invalid"), ("unverifiable", "invalid")])
def test_run_case_maps_outcomes(monkeypatch, outcome, expected):
    case = CASES[0]
    monkeypatch.setattr(mc.cb, "verify_text", fake_verify(lambda t: outcome))
    r = mc.run_case(case, "mumei", 5)
    assert r["baseline"] == "proven"
    assert r["id"] == case["id"] and r["case_hash"] == case["case_hash"]
    assert r["mutants"] and {m["outcome"] for m in r["mutants"]} == {expected}
    assert all("\n" not in m["message"] for m in r["mutants"])


def test_run_case_verifies_the_mutated_body_under_the_original_contract(monkeypatch):
    seen = []
    case = CASES[0]
    monkeypatch.setattr(mc.cb, "verify_text", lambda b, t, to: seen.append(t) or {
        "outcome": "proven" if t == case["ports"]["fixed"] else "refuted", "status": "failed", "diagnostics": []})
    head, body = mc.split_fixed(case)
    mc.run_case(case, "mumei", 5)
    assert seen[0] == case["ports"]["fixed"]
    assert len(seen) == 1 + len(mc.mutants(body))
    assert all(t.startswith(head) and t != case["ports"]["fixed"] for t in seen[1:])


@pytest.mark.parametrize("baseline", ["refuted", "inconclusive", "unverifiable"])
def test_run_case_scores_no_mutant_when_the_fixed_port_is_not_proven(monkeypatch, baseline):
    seen = []
    monkeypatch.setattr(mc.cb, "verify_text", lambda b, t, to: seen.append(t) or {
        "outcome": baseline, "status": "failed", "diagnostics": []})
    r = mc.run_case(CASES[0], "mumei", 5)
    assert r["baseline"] == baseline and r["mutants"] == [] and len(seen) == 1


@pytest.mark.parametrize("baseline", ["refuted", None])
def test_check_rejects_a_case_whose_fixed_port_was_not_proven(monkeypatch, tmp_path, baseline):
    doc = json.loads(mc.RESULT.read_text())
    target = doc["cases"][0]
    if baseline is None:
        target.pop("baseline")
    else:
        target["baseline"] = baseline
    result = tmp_path / "mutation.json"
    result.write_text(json.dumps(doc))
    monkeypatch.setattr(mc, "RESULT", result)
    problems = mc.check(mc.cb.load_cases()[0])
    assert any(p.startswith(f"{target['id']}: the unmutated fixed port was not proven") for p in problems)


@pytest.mark.parametrize("outcomes, score", [
    ([], None), (["invalid"], None), (["killed"], 1.0), (["survived"], 0.0),
    (["killed", "killed", "survived", "invalid"], 0.667),
])
def test_tally(outcomes, score):
    t = mc.tally([{"outcome": o} for o in outcomes])
    assert t["score"] == score and t["mutants"] == len(outcomes)
    assert t["killed"] + t["survived"] + t["invalid"] == len(outcomes)


@pytest.mark.parametrize("status, message, expected", [
    ("input_error", "", "unsupported"),
    ("failed", "Unknown function `missing`", "unsupported"),
    ("timeout", "", "budget_exhausted"),
    ("no-json (exit 2)", "", "environment_failure"),
    ("failed", "", "inconclusive"),
])
def test_mutation_failure_kind_infers_legacy_rows(status, message, expected):
    row = {"outcome": "invalid", "status": status, "message": message}
    assert mc.mutation_failure_kind(row) == expected


def test_mutation_failure_kind_honors_explicit_values_and_decided_rows():
    assert mc.mutation_failure_kind({"outcome": "invalid", "failure_kind": "environment_failure"}) == "environment_failure"
    assert mc.mutation_failure_kind({"outcome": "invalid", "failure_kind": "bogus"}) == "inconclusive"
    assert mc.mutation_failure_kind({"outcome": "killed"}) is None


def test_tally_separates_invalid_failure_kinds():
    rows = [
        {"outcome": "killed"},
        {"outcome": "survived"},
        {"outcome": "invalid", "status": "input_error", "message": ""},
        {"outcome": "invalid", "status": "timeout", "message": ""},
        {"outcome": "invalid", "status": "no-json (exit 2)", "message": ""},
        {"outcome": "invalid", "status": "failed", "message": ""},
    ]
    t = mc.tally(rows)
    assert t["invalid"] == 4
    assert (t["unsupported"], t["budget_exhausted"], t["environment_failure"], t["inconclusive"]) == (1, 1, 1, 1)


def test_run_case_preserves_baseline_and_mutant_measurement(monkeypatch):
    case = CASES[0]
    fixed = case["ports"]["fixed"]

    def verify(_bin, text, timeout):
        outcome = "proven" if text == fixed else "inconclusive"
        result = {"outcome": outcome, "status": "success" if outcome == "proven" else "input_error",
                  "diagnostics": [], "seconds": 0.25, "budget_seconds": timeout}
        if outcome == "inconclusive":
            result["failure_kind"] = "unsupported"
        return result

    monkeypatch.setattr(mc.cb, "verify_text", verify)
    record = mc.run_case(case, "mumei", 7)
    assert record["baseline_check"]["seconds"] == 0.25
    assert record["baseline_check"]["budget_seconds"] == 7
    assert record["mutants"]
    assert {m["failure_kind"] for m in record["mutants"]} == {"unsupported"}
    assert all(m["seconds"] == 0.25 and m["budget_seconds"] == 7 for m in record["mutants"])


def test_baseline_tally_separates_false_positive_and_failure_kinds():
    cases = [
        {"baseline": "proven"},
        {"baseline": "refuted"},
        {"baseline": "inconclusive",
         "baseline_check": {"outcome": "inconclusive", "status": "timeout", "diagnostics": []}},
        {"baseline": "inconclusive",
         "baseline_check": {"outcome": "inconclusive", "status": "input_error", "diagnostics": []}},
        {"baseline": "inconclusive"},
    ]
    got = mc.baseline_tally(cases)
    assert got["proven"] == 1 and got["false_positive"] == 1
    assert got["budget_exhausted"] == 1 and got["unsupported"] == 1 and got["inconclusive"] == 1


def test_verification_measurements_count_legacy_slots_without_inventing_time():
    cases = [{
        "baseline": "proven",
        "baseline_check": {"outcome": "proven", "seconds": 1.25, "budget_seconds": 5},
        "mutants": [
            {"outcome": "killed", "seconds": 0.75, "budget_seconds": 5},
            {"outcome": "invalid", "status": "failed"},
            {"outcome": "invalid", "status": "timeout", "seconds": True, "budget_seconds": 5},
        ],
    }]
    got = mc.verification_measurements(cases)
    assert got == {"seconds": 2.0, "timed_calls": 2, "expected_calls": 4,
                   "budget_seconds": 15.0, "budgeted_calls": 3}


def test_render_exposes_failure_taxonomy_and_measurement_coverage():
    doc = {"verifier": {"version": "mumei test", "commit": "a" * 40},
           "cases": [{"id": "X", "language": "python", "function": "f", "baseline": "proven",
                      "baseline_check": {"outcome": "proven", "seconds": 1.0, "budget_seconds": 5},
                      "mutants": [{"op": "relational", "at": 0, "from": "<", "to": "<=",
                                   "outcome": "invalid", "status": "timeout", "message": "",
                                   "failure_kind": "budget_exhausted", "seconds": 5.0, "budget_seconds": 5}]}]}
    text = mc.render(doc)
    assert "| | Mutants | Killed | Potential false acceptance | Unsupported | Inconclusive | Env failure | Budget exhausted | Score |" in text
    assert "| **all** | 1 | 0 | 0 | 0 | 0 | 0 | 1 | — |" in text
    assert "Baseline fixed ports: 1 proven, 0 false positive" in text
    assert "| Verifier calls | 6.0s / 2 of 2 calls | 10.0s / 2 of 2 calls |" in text


def test_render_keeps_legacy_verifier_timing_unknown():
    doc = {"cases": [{"id": "X", "language": "python", "function": "f", "baseline": "proven",
                      "mutants": [{"op": "relational", "at": 0, "from": "<", "to": "<=",
                                   "outcome": "killed", "status": "failed", "message": ""}]}]}
    text = mc.render(doc)
    assert "| Verifier calls | — / 0 of 2 calls | — / 0 of 2 calls |" in text


def test_render_distinguishes_unscored_baseline_from_no_mutable_token():
    doc = {"cases": [
        {"id": "NO-TOKEN", "language": "python", "function": "f", "baseline": "proven", "mutants": []},
        {"id": "TIMEOUT", "language": "python", "function": "g", "baseline": "inconclusive", "mutants": []},
    ]}
    text = mc.render(doc)
    assert "Ports with no mutable token: `NO-TOKEN`." in text
    assert "Cases with no mutant verifier calls because the baseline fixed port was not proven: `TIMEOUT`." in text
    assert "Ports with no mutable token: `NO-TOKEN`, `TIMEOUT`" not in text


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "RESULT", tmp_path / "mutation.json")
    monkeypatch.setattr(mc, "REPORT", tmp_path / "MUTATION.md")
    monkeypatch.setattr(mc.cb, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mc.cb, "verifier_identity", lambda b: {"version": "mumei 0", "commit": "c" * 40, "dirty": False})
    monkeypatch.setattr(mc.cb, "load_cases", lambda: (CASES[:3], []))
    return tmp_path


def run_all(monkeypatch, rule=lambda t: "refuted"):
    monkeypatch.setattr(mc.cb, "verify_text", fake_verify(rule))
    assert mc.main(["--mumei-bin", "mumei", "--jobs", "2"]) == 0


def test_main_writes_result_and_report_that_check_accepts(results, monkeypatch, capsys):
    run_all(monkeypatch)
    doc = json.loads(mc.RESULT.read_text())
    assert [c["id"] for c in doc["cases"]] == [c["id"] for c in CASES[:3]]
    assert doc["verifier"]["commit"] == "c" * 40
    md = mc.REPORT.read_text()
    assert "Generated by scripts/run_mutation_control.py" in md and "| **all** |" in md and "None." in md
    assert mc.main(["--check"]) == 0, capsys.readouterr().err


def test_report_lists_survivors_with_their_line(results, monkeypatch):
    run_all(monkeypatch, lambda t: "proven" if "<=" not in t else "refuted")
    md = mc.REPORT.read_text()
    assert "## Surviving mutants" in md and "relational `<=` → `<`" in md and "None." not in md


@pytest.mark.parametrize("tamper, message", [
    (lambda d: d["cases"].pop(), "no mutation result"),
    (lambda d: d["cases"][0].update(case_hash="0"), "port or contract changed"),
    (lambda d: d["cases"][0]["mutants"].pop(), "recorded mutants differ"),
    (lambda d: d["cases"][0]["mutants"][0].update(at=d["cases"][0]["mutants"][0]["at"] + 1), "recorded mutants differ"),
    (lambda d: d["cases"][0]["mutants"][0].update(outcome="maybe"), "without a valid outcome"),
    (lambda d: d["cases"][0]["mutants"][0].update(failure_kind="maybe"), "without a valid failure kind"),
    (lambda d: d["cases"][0]["mutants"][0].update(outcome="killed", failure_kind="inconclusive"),
     "without a valid failure kind"),
    (lambda d: d["cases"][0]["baseline_check"].update(outcome="refuted"), "does not match the recorded baseline"),
    (lambda d: d["cases"][0]["baseline_check"].update(failure_kind="inconclusive"),
     "baseline measurement has an invalid failure kind"),
    (lambda d: d["cases"][0]["baseline_check"].update(seconds=True), "time or budget is not numeric"),
    (lambda d: d["cases"].append({**d["cases"][0], "id": "XX99-D99"}), "no longer exists"),
    (lambda d: d.pop("verifier"), "does not record the mumei commit"),
    (lambda d: d["cases"].append(dict(d["cases"][0])), "recorded more than once"),
    (lambda d: d["cases"][0]["mutants"][0].update(outcome="survived"), "MUTATION.md is out of date"),
])
def test_check_catches_tampering(results, monkeypatch, capsys, tamper, message):
    run_all(monkeypatch)
    doc = json.loads(mc.RESULT.read_text())
    tamper(doc)
    mc.RESULT.write_text(json.dumps(doc))
    assert mc.main(["--check"]) == 1
    assert message in capsys.readouterr().err


def test_check_without_result(results, capsys):
    assert mc.main(["--check"]) == 1
    assert "mutation.json is missing" in capsys.readouterr().err


def test_render_only_rewrites_the_report(results, monkeypatch, capsys):
    run_all(monkeypatch)
    mc.REPORT.write_text("stale")
    assert mc.main(["--render-only"]) == 0
    assert mc.main(["--check"]) == 0, capsys.readouterr().err


def test_only_merges_into_the_committed_result(results, monkeypatch):
    run_all(monkeypatch)
    monkeypatch.setattr(mc.cb, "verify_text", fake_verify(lambda t: "proven"))
    assert mc.main(["--mumei-bin", "mumei", "--only", CASES[1]["id"]]) == 0
    doc = json.loads(mc.RESULT.read_text())
    outcomes = {c["id"]: {m["outcome"] for m in c["mutants"]} for c in doc["cases"]}
    assert outcomes[CASES[0]["id"]] == {"killed"} and outcomes[CASES[1]["id"]] == {"survived"}


def test_only_needs_a_committed_result(results):
    with pytest.raises(SystemExit, match="does not exist yet"):
        mc.main(["--mumei-bin", "mumei", "--only", CASES[0]["id"]])


def test_needs_mumei(results):
    with pytest.raises(SystemExit, match="mumei binary not found"):
        mc.main(["--mumei-bin", ""])


def test_context_shows_the_whole_short_line():
    body = "x\n  if a < b { 1 }\ny"
    (m,) = [m for m in mc.mutants(body) if m["from"] == "<"]
    assert mc.context(body, m) == "if a <= b { 1 }"


def test_context_trims_long_lines_around_the_change():
    body = "p " * 40 + "a < b" + " q" * 40
    (m,) = [m for m in mc.mutants(body) if m["from"] == "<"]
    got = mc.context(body, m)
    assert got.startswith("… p") and got.endswith("q …") and "a <= b" in got
    assert len(got) < 120


def test_only_refuses_a_result_from_another_build(results, monkeypatch):
    run_all(monkeypatch)
    monkeypatch.setattr(mc.cb, "verifier_identity", lambda b: {"version": "mumei 0", "commit": "d" * 40, "dirty": False})
    with pytest.raises(SystemExit, match="another mumei build"):
        mc.main(["--mumei-bin", "mumei", "--only", CASES[0]["id"]])


def test_loop_annotations_are_not_mutated():
    case = next(c for c in CASES if c["id"] == "PY02-D05")
    _, body = mc.split_fixed(case)
    for m in mc.mutants(body):
        line = body[body.rfind("\n", 0, m["at"]) + 1:].lstrip()
        assert not line.startswith(("invariant:", "decreases:"))
