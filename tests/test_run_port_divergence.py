"""Port-divergence diagnostics without Mumei or an LLM provider."""

import sys
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
        return {"outcome": "refuted" if "0 - 1" in text else "proven", "status": "", "diagnostics": []}

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
    for path, text, timeout in calls:
        assert (path, timeout) == ("/bin/mumei", 7)
        assert "requires: (n >= 0) && n == 0;" in text
        assert "ensures: result >= 0;" in text


@pytest.mark.parametrize(("reference", "llm", "expected"), [
    ("breaks", "holds", "diverged"),
    ("breaks", "breaks", "still_refutes"),
    ("breaks", "inconclusive", "inconclusive"),
    ("breaks", "outside requires", "inconclusive"),
    ("holds", None, "inconclusive"),
    ("inconclusive", None, "inconclusive"),
])
def test_outcome_needs_a_refuted_reference(reference, llm, expected):
    assert pd.outcome([{"reference": {"verdict": reference},
                        "llm": {"verdict": llm} if llm else None}]) == expected


def test_does_not_replay_candidate_without_a_reference_violation(monkeypatch):
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
    assert len(calls) == 1


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


@pytest.mark.parametrize("body", [None, "", "}", "if true { 0", "0\n}\natom extra()", "trusted atom x()"])
def test_body_must_not_escape_pinned_contract(body):
    assert not pd.usable_body(body)


def test_body_braces_in_comments_and_strings_do_not_escape():
    assert pd.usable_body('if true { "}" /* atom x() */ } else { "" }')


def test_python_docstrings_do_not_count_as_risky_operations():
    assert "/" not in pd.scrub('"""x / y; xs[3]"""\nreturn n  # n / 0', "python")
    assert "//" in pd.scrub("return n // y", "python")
