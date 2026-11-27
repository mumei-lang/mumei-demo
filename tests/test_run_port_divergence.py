"""Port-divergence diagnostics without Mumei or an LLM provider."""

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import run_port_divergence as pd  # noqa: E402

HEADER = "atom read(n: i64) -> i64\n    requires: n >= 0;\n    ensures: result >= 0;\n    "
WITNESS = {"name": "zero", "source": "fixture", "values": {"n": 0}}


def stub_case(reference, source="return read_native(n)", **other):
    return {"id": "X", "atom": "read", "header": HEADER, "prelude": "", "language": "rust", "category": "",
            "functions": {"buggy": source}, "ports": {"buggy": pd.bench.assemble(
                {"header": HEADER, "prelude": ""}, reference)}, **other}


def test_replays_only_misaccepts_with_same_input_and_contract(monkeypatch):
    case = stub_case("0 - 1")
    monkeypatch.setattr(pd.replay, "replay_inputs", lambda _case: ([WITNESS], "digest"))
    calls = []

    def verify(path, text, timeout):
        calls.append((path, text, timeout))
        return {"outcome": "refuted" if "0 - 1" in text else "proven", "status": "", "diagnostics": [],
                "seconds": 1.0, "budget_seconds": timeout}

    monkeypatch.setattr(pd.bench, "verify_text", verify)
    doc = {"model": "test", "runs": [
        [{"id": "X", "buggy": {"outcome": "proven", "body": "n"}}],
        [{"id": "X", "buggy": {"outcome": "refuted", "body": "0 - 1"}}],
        [{"id": "X", "buggy": {"outcome": "proven", "body": "0"}}],
    ]}
    report = pd.collect([case], doc, "/bin/mumei", 7)
    assert report["outcomes"] == {"diverged": 2}
    assert [r["run"] for r in report["misaccepts"]] == [1, 3]
    assert report["misaccepts"][0]["inputs"][0]["values"] == WITNESS["values"]
    assert len(calls) == 3  # The reference is checked once, then reused.
    assert report["measurement"]["reference"] == {
        "seconds": 1.0, "timed_calls": 1, "expected_calls": 1,
        "budget_seconds": 7.0, "budgeted_calls": 1}
    assert report["measurement"]["llm_ports"] == {
        "seconds": 2.0, "timed_calls": 2, "expected_calls": 2,
        "budget_seconds": 14.0, "budgeted_calls": 2}
    for path, text, timeout in calls:
        assert (path, timeout) == ("/bin/mumei", 7)
        assert "requires: (n >= 0) && n == 0;" in text
        assert "ensures: result >= 0;" in text


def test_recorded_corpus_requests_every_reference_and_accepted_port(monkeypatch):
    cases, errors = pd.bench.load_cases()
    assert not errors
    result_path = pd.bench.result_path("mumei-llm", "openai/gpt-6-luna")
    doc = json.loads(result_path.read_text())
    by_id = {case["id"]: case for case in cases}
    accepted = {(run, record["id"]): record["buggy"]["body"]
                for run, records in enumerate(doc["runs"], 1) for record in records
                if record["buggy"]["outcome"] == "proven"}
    assert len(accepted) == 26
    reference = {}
    candidates = []
    for (_, case_id), body in accepted.items():
        case = by_id[case_id]
        inputs, _ = pd.replay.replay_inputs(case)
        for witness in inputs:
            atom, values = case["atom"], witness["values"]
            reference[case_id, witness["name"]] = pd.replay.pinned_port(case["ports"]["buggy"], atom, values)
            candidates.append(pd.replay.pinned_port(pd.bench.assemble(case, body), atom, values))
    assert len({case_id for case_id, _ in reference}) == 12

    calls = Counter()
    reference_texts = set(reference.values())

    def verify(_bin, port, _timeout):
        calls[port] += 1
        return {"outcome": "refuted" if port in reference_texts else "proven", "status": "", "diagnostics": []}

    monkeypatch.setattr(pd.bench, "verify_text", verify)
    report = pd.collect(cases, doc, "/bin/mumei", 7)
    assert {(row["run"], row["case"]) for row in report["misaccepts"]} == set(accepted)
    assert report["outcomes"] == {"diverged": 26}
    assert calls == Counter(reference.values()) + Counter(candidates)
    assert report["lint_counts"]["silent_repair"] == 3
    silent_rows = {
        (row["run"], row["case"])
        for row in report["misaccepts"]
        if any(finding["kind"] == "silent_repair" for finding in row["lint_findings"])
    }
    assert silent_rows == {(1, "SOL01-D03"), (3, "SOL01-D03"), (3, "GO01-D04")}


@pytest.mark.parametrize(("reference", "llm", "expected"), [
    ("breaks", "holds", "diverged"),
    ("breaks", "breaks", "still_refutes"),
    ("breaks", "inconclusive", "inconclusive"),
    ("breaks", "outside requires", "inconclusive"),
    ("holds", "holds", "inconclusive"),
    ("inconclusive", "holds", "inconclusive"),
])
def test_outcome_needs_a_refuted_reference(reference, llm, expected):
    assert pd.outcome([{"reference": {"verdict": reference}, "llm": {"verdict": llm}}]) == expected


def test_collect_separates_unresolved_taxonomy_from_verifier_measurement(monkeypatch):
    case = stub_case("0 - 1")
    monkeypatch.setattr(pd.replay, "replay_inputs", lambda _case: ([WITNESS], "digest"))

    def verify(_path, text, _timeout):
        if "0 - 1" in text:
            return {"outcome": "inconclusive", "status": "timeout", "diagnostics": [],
                    "seconds": 1.5, "budget_seconds": 7}
        return {"outcome": "inconclusive", "status": "input_error", "diagnostics": [],
                "seconds": 2.5, "budget_seconds": 8}

    monkeypatch.setattr(pd.bench, "verify_text", verify)
    doc = {"model": "test", "runs": [[
        {"id": "X", "buggy": {"outcome": "proven", "body": "0"}},
        {"id": "X", "buggy": {"outcome": "proven", "body": None}},
    ]]}
    report = pd.collect([case], doc, "/bin/mumei", 7)
    assert report["unresolved"]["reference"] == {
        "unsupported": 0, "inconclusive": 0, "environment_failure": 0, "budget_exhausted": 1}
    assert report["unresolved"]["llm_ports"] == {
        "unsupported": 2, "inconclusive": 0, "environment_failure": 0, "budget_exhausted": 0}
    assert report["measurement"]["reference"] == {
        "seconds": 1.5, "timed_calls": 1, "expected_calls": 1,
        "budget_seconds": 7.0, "budgeted_calls": 1}
    assert report["measurement"]["llm_ports"] == {
        "seconds": 2.5, "timed_calls": 1, "expected_calls": 1,
        "budget_seconds": 8.0, "budgeted_calls": 1}
    rendered = pd.render(report)
    assert "reference unresolved: unsupported 0, inconclusive 0, environment failure 0, budget exhausted 1" in rendered
    assert "LLM port verifier measurement: 2.5s across 1 of 1 calls; budget 8.0s across 1 of 1 calls" in rendered


def test_collect_counts_verifier_startup_failure_as_environment_failure(monkeypatch):
    case = stub_case("0 - 1")
    monkeypatch.setattr(pd.replay, "replay_inputs", lambda _case: ([WITNESS], "digest"))
    monkeypatch.setattr(pd.bench, "verify_text", lambda *_args: {
        "outcome": "inconclusive", "status": "verifier startup failed (FileNotFoundError)",
        "failure_kind": "environment_failure", "diagnostics": [], "seconds": 0.1, "budget_seconds": 7})
    doc = {"model": "test", "runs": [[{"id": "X", "buggy": {"outcome": "proven", "body": "0"}}]]}
    report = pd.collect([case], doc, "/bin/mumei", 7)
    for lane in ("reference", "llm_ports"):
        assert report["unresolved"][lane]["environment_failure"] == 1
        assert report["measurement"][lane]["expected_calls"] == 1
        assert report["measurement"][lane]["timed_calls"] == 1


def test_replays_candidate_even_without_a_reference_violation(monkeypatch):
    monkeypatch.setattr(pd.replay, "replay_inputs", lambda _case: ([WITNESS], "digest"))
    case = stub_case("n")
    calls = []

    def verify(_bin, port, _timeout):
        calls.append(port)
        return {"outcome": "proven", "status": "success", "diagnostics": []}

    monkeypatch.setattr(pd.bench, "verify_text", verify)
    doc = {"model": "test", "runs": [[{"id": "X", "buggy": {"outcome": "proven", "body": "0"}}]]}
    report = pd.collect([case], doc, "/bin/mumei", 7)
    assert report["outcomes"] == {"inconclusive": 1}
    witness = report["misaccepts"][0]["inputs"][0]
    assert witness["reference"]["verdict"] == witness["llm"]["verdict"] == "holds"
    assert len(calls) == 2


@pytest.mark.parametrize(("source", "reference", "warning"), [
    ("return xs[0]", "xs[0]", "index/slice"),
    ("return xs[:top]", "slice_to(n, top)", "index/slice"),
    ("return n / x", "n / x", "division/modulo"),
    ("return *ptr", "deref(present)", "dereference"),
    ("n as i32", "int32(n)", "narrow cast"),
])
def test_risky_op_lint_needs_source_and_modeled_evidence(source, reference, warning):
    assert pd.lint(stub_case(reference, source), "0") == [f"missing modeled {warning}"]
    assert pd.lint(stub_case(reference, source), reference) == []
    assert pd.lint(stub_case(reference, "n"), "0") == []


def test_possible_added_guard_and_success_rewrite_ignore_comments_and_strings():
    case = stub_case("Window { ok: true, start: n }")
    case["header"] = HEADER.replace("result >= 0", "result.ok => result.start >= 0")
    assert pd.lint(case, 'Window { ok: true, start: n } // if read(0)') == []
    assert pd.lint(case, 'let message = "if"; Window { ok: n > 0, start: n }') == [
        "success flag can mask a postcondition clause"]
    assert pd.lint(case, "if n > 0 { read(n) } else { Window { ok: true, start: n } }") == [
        "possible added guard", "target atom calls itself"]


def test_priority_fallback_does_not_change_the_success_flag():
    reference = ("if missing { Parsed { ok: true, value: 3 } } "
                 "else { if numeric && (value < 1 || value > 5) { Parsed { ok: false, value: 0 } } "
                 "else { Parsed { ok: true, value: value } } }")
    candidate = ("if missing { Parsed { ok: true, value: 3 } } "
                 "else if numeric && (value < 1 || value > 5) { Parsed { ok: false, value: 0 } } "
                 "else if numeric { Parsed { ok: true, value: value } } else { Parsed { ok: true, value: 3 } }")
    case = stub_case(reference)
    case["header"] = HEADER.replace("result >= 0", "result.ok => result.value >= 0")
    assert pd.lint(case, candidate) == ["possible added guard"]
    assert "success flag can mask a postcondition clause" in pd.lint(
        case, candidate.replace("else if numeric &&", "else if !numeric &&"))


@pytest.mark.parametrize("body", [None, "", "}", "if true { 0", "0\n}\natom extra()", "trusted atom x()"])
def test_body_must_not_escape_pinned_contract(body):
    assert not pd.usable_body(body)


def test_body_braces_in_comments_and_strings_do_not_escape():
    assert pd.usable_body('if true { "}" /* atom x() */ } else { "" }')


def test_python_docstrings_do_not_count_as_risky_operations():
    assert "/" not in pd.scrub('"""x / y; xs[3]"""\nreturn n  # n / 0', "python")
    assert "//" in pd.scrub("return n // y", "python")


def test_lint_findings_are_structured_and_keep_message_compatibility():
    case = stub_case("xs[0]", "return xs[0]")
    findings = pd.lint_findings(case, "0")
    assert findings == [{"kind": "missing_modeled_operation", "operation": "index/slice",
                         "message": "missing modeled index/slice"}]
    assert pd.lint(case, "0") == ["missing modeled index/slice"]


def test_lint_findings_cover_guard_success_rewrite_and_self_call():
    case = stub_case("Window { ok: true, start: n }")
    case["header"] = HEADER.replace("result >= 0", "result.ok => result.start >= 0")
    body = "if n > 0 { read(n) } else { Window { ok: n > 0, start: n } }"
    kinds = {finding["kind"] for finding in pd.lint_findings(case, body)}
    assert kinds == {"added_guard", "success_flag_rewrite", "self_call"}


def test_collect_aggregates_structured_lint_counts(monkeypatch):
    case = stub_case("xs[0]", "return xs[0]")
    monkeypatch.setattr(pd.replay, "replay_inputs", lambda _case: ([WITNESS], "digest"))
    monkeypatch.setattr(pd.bench, "verify_text", lambda *_args: {
        "outcome": "refuted", "status": "", "diagnostics": []})
    doc = {"model": "test", "runs": [[{"id": "X", "buggy": {"outcome": "proven", "body": "0"}}],
                                     [{"id": "X", "buggy": {"outcome": "proven", "body": "0"}}]]}
    report = pd.collect([case], doc, "/bin/mumei", 7)
    assert report["lint_counts"] == {"missing_modeled_operation:index/slice": 2}
    assert report["misaccepts"][0]["lint"] == ["missing modeled index/slice"]
    assert report["misaccepts"][0]["lint_findings"][0]["kind"] == "missing_modeled_operation"
    assert "lint findings: missing_modeled_operation:index/slice 2" in pd.render(report)


def test_collect_omits_empty_lint_counts(monkeypatch):
    case = stub_case("0", "return 0")
    monkeypatch.setattr(pd.replay, "replay_inputs", lambda _case: ([WITNESS], "digest"))
    monkeypatch.setattr(pd.bench, "verify_text", lambda *_args: {
        "outcome": "refuted", "status": "", "diagnostics": []})
    doc = {"model": "test", "runs": [[{"id": "X", "buggy": {"outcome": "proven", "body": "0"}}]]}
    report = pd.collect([case], doc, "/bin/mumei", 7)
    assert report["lint_counts"] == {}
    assert "lint findings:" not in pd.render(report)
