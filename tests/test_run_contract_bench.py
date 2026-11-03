"""Unit tests for scripts/run_contract_bench.py.

No model and no mumei binary are called: the provider is a stub and
verification is replaced where a test needs it."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "run_contract_bench.py"
spec = importlib.util.spec_from_file_location("run_contract_bench", SCRIPT)
cb = importlib.util.module_from_spec(spec)
sys.modules["run_contract_bench"] = cb
spec.loader.exec_module(cb)

SENTINEL_KEY = "sk-test-sentinel-not-a-real-key"
APP = "def average(total, days):\n    return total // days\n\n\ndef other():\n    return 1\n"
PATCH = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,4 @@
 def average(total, days):
+    if days <= 0:
+        return 0
     return total // days
"""
DEFECTS = {"specimen": "py-09-x", "language": "python", "defects": [
    {"id": "PY09-D01", "file": "app.py", "function": "average", "line": 2, "category": "division-by-zero"},
    {"id": "PY09-D02", "file": "app.py", "function": "other", "line": 6, "category": "sql-injection"},
]}
HEADER = ("atom average(total: i64, days: i64) -> i64\n    requires: total >= 0;\n"
          "    ensures: (days <= 0 => result == 0) && (days > 0 => result == total / days);\n    ")
BUGGY = HEADER + "body: {\n        total / days\n    }\n"
FIXED = HEADER + "body: {\n        if days <= 0 { 0 } else { total / days }\n    }\n"
CONTRACT = {"id": "PY09-D01", "file": "app.py", "function": "average", "atom": "average",
            "requirement": "Average per day; 0 when there are no days.", "notes": ""}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    sdir = tmp_path / "specimens" / "python" / "py-09-x"
    sdir.mkdir(parents=True)
    (sdir / "app.py").write_text(APP)
    (sdir / "fixed.patch").write_text(PATCH)
    (sdir / "DEFECTS.json").write_text(json.dumps(DEFECTS))
    cdir = tmp_path / "proofs" / "python" / "py-09-x" / "PY09-D01"
    cdir.mkdir(parents=True)
    (cdir / "contract.json").write_text(json.dumps(CONTRACT))
    (cdir / "buggy.mm").write_text(BUGGY)
    (cdir / "fixed.mm").write_text(FIXED)
    (tmp_path / "README.md").write_text(f"# x\n\n{cb.README_START}\nold\n{cb.README_END}\n\ntail\n")
    for name, value in {"REPO_ROOT": tmp_path, "PROOFS_ROOT": tmp_path / "proofs",
                        "SPECIMENS_ROOT": tmp_path / "specimens",
                        "RESULTS_DIR": tmp_path / "proofs" / "results",
                        "RESULTS_MD": tmp_path / "proofs" / "RESULTS.md",
                        "README": tmp_path / "README.md"}.items():
        monkeypatch.setattr(cb, name, value)
    return tmp_path


def fake_verify(outcomes):
    """verify_text stand-in: outcome chosen by a substring of the .mm text."""
    def verify(_bin, text, _timeout):
        for needle, outcome in outcomes:
            if needle in text:
                return {"outcome": outcome, "status": outcome, "diagnostics": []}
        return {"outcome": "inconclusive", "status": "unmatched", "diagnostics": []}
    return verify


REFERENCE = [("ensures: false", "refuted"), ("if days <= 0", "proven"), ("total / days\n", "refuted")]


class StubProvider:
    model = "stub/model-1"

    def __init__(self, replies):
        self.replies, self.prompts = replies, []

    def complete(self, messages, seed):
        self.prompts.append(messages)
        text = self.replies(messages, seed)
        return text, {"prompt_tokens": 10, "completion_tokens": 5, "cost_usd": 0.001, "seconds": 0.5, "attempts": 1}


# --- splitting and loading ---------------------------------------------------

def test_split_port_separates_prelude_header_body():
    prelude = "atom helper(x: i64) -> i64\n    requires: true;\n    ensures: result == x;\n    body: { x }\n\n"
    parts = cb.split_port(prelude + FIXED, "average")
    assert parts[0] == prelude and parts[1] == HEADER and parts[2].startswith("body: {")


@pytest.mark.parametrize("text", ["", "atom other(x: i64) -> i64 body: { x }", HEADER])
def test_split_port_missing_atom_or_body(text):
    assert cb.split_port(text, "average") is None


@pytest.mark.parametrize("header,expected", [
    (HEADER, "(days <= 0 => result == 0) && (days > 0 => result == total / days)"),
    ("atom f(x: i64) -> i64\n    requires: true;\n", None),
])
def test_header_ensures(header, expected):
    assert cb.header_ensures(header) == expected


def test_load_cases_reads_case_and_hashes(repo):
    cases, errors = cb.load_cases()
    assert errors == []
    (case,) = cases
    assert case["id"] == "PY09-D01" and case["category"] == "division-by-zero"
    assert case["header"] == HEADER and case["prelude"] == ""
    assert "if days <= 0" in case["native"]["fixed"] and "if days <= 0" not in case["native"]["buggy"]
    assert case["functions"]["buggy"].startswith("def average")
    assert len(case["case_hash"]) == 64 and len(case["source_hash"]) == 64


def test_non_target_defects_need_no_case(repo):
    _, errors = cb.load_cases()
    assert not any("PY09-D02" in e for e in errors)


def test_missing_case_for_target_defect(repo):
    import shutil
    shutil.rmtree(repo / "proofs" / "python" / "py-09-x" / "PY09-D01")
    _, errors = cb.load_cases()
    assert errors == ["proofs/python/py-09-x/PY09-D01: no case for target defect (division-by-zero)"]


@pytest.mark.parametrize("variant,text,message", [
    ("buggy", BUGGY.replace("requires: total >= 0", "requires: true"), "different atom headers"),
    ("fixed", "atom helper(x: i64) -> i64\n    requires: true;\n    ensures: true;\n    body: { x }\n\n" + FIXED, "different preludes"),
    ("buggy", "trusted " + BUGGY, "must not use trusted"),
    ("fixed", FIXED + "\natom extra(x: i64) -> i64\n    requires: true;\n    ensures: true;\n    body: { x }\n", "must be the last atom"),
    ("fixed", FIXED.replace("atom average", "atom avg"), "is missing from a port"),
])
def test_port_validation_errors(repo, variant, text, message):
    (repo / "proofs" / "python" / "py-09-x" / "PY09-D01" / f"{variant}.mm").write_text(text)
    _, errors = cb.load_cases()
    assert any(message in e for e in errors), errors


@pytest.mark.parametrize("key,value,message", [
    ("function", "avg", "function 'avg' differs from DEFECTS.json"),
    ("file", "main.py", "file 'main.py' differs from DEFECTS.json"),
    ("id", "PY09-D99", "does not match the directory"),
])
def test_contract_metadata_must_match_ground_truth(repo, key, value, message):
    path = repo / "proofs" / "python" / "py-09-x" / "PY09-D01" / "contract.json"
    path.write_text(json.dumps({**CONTRACT, key: value}))
    _, errors = cb.load_cases()
    assert any(message in e for e in errors), errors


def test_missing_port_file(repo):
    (repo / "proofs" / "python" / "py-09-x" / "PY09-D01" / "fixed.mm").unlink()
    _, errors = cb.load_cases()
    assert any("both required" in e for e in errors)


def test_unknown_defect_id(repo):
    cdir = repo / "proofs" / "python" / "py-09-x" / "PY09-D77"
    cdir.mkdir()
    (cdir / "contract.json").write_text(json.dumps({**CONTRACT, "id": "PY09-D77"}))
    _, errors = cb.load_cases()
    assert any("PY09-D77: no such defect" in e for e in errors)


# --- native source extraction -------------------------------------------------

@pytest.mark.parametrize("lang,source,name,expected", [
    ("python", "class A:\n    @staticmethod\n    def f(x):\n        return x\n\ndef g():\n    pass\n", "f",
     "    @staticmethod\n    def f(x):\n        return x"),
    ("python", "def f(:\n", "f", None),
    ("go", "package x\n\nfunc (s *S) Get(i int) int {\n\treturn s.a[i]\n}\n", "Get", "func (s *S) Get(i int) int {\n\treturn s.a[i]\n}"),
    ("rust", "pub fn split(a: u64) -> u64 {\n    if a > 0 { a } else { 0 }\n}\n", "split", "pub fn split(a: u64) -> u64 {\n    if a > 0 { a } else { 0 }\n}"),
    ("typescript", "export function page<T>(xs: T[]) {\n  return xs;\n}\n", "page", "export function page<T>(xs: T[]) {\n  return xs;\n}"),
    ("solidity", "contract C {\n    function withdraw() external {\n        x = 0;\n    }\n}\n", "withdraw", "    function withdraw() external {\n        x = 0;\n    }"),
    ("go", "func Other() {}\n", "Missing", None),
])
def test_extract_function(lang, source, name, expected):
    assert cb.extract_function(lang, source, name) == expected


# --- verdict extraction ------------------------------------------------------

@pytest.mark.parametrize("doc,code,outcome", [
    ({"status": "success", "diagnostics": []}, 0, "proven"),
    ({"status": "success", "diagnostics": []}, 1, "inconclusive"),
    ({"status": "failed", "diagnostics": [{"severity": "error", "message": "Verification Error: Postcondition (ensures) is not satisfied.", "atom": "f"}]}, 1, "refuted"),
    ({"status": "failed", "unverifiable": 1, "diagnostics": []}, 1, "inconclusive"),
    ({"status": "failed", "infra_errors": 1, "diagnostics": []}, 1, "inconclusive"),
    ({"status": "error", "diagnostics": []}, 1, "inconclusive"),
    (None, 2, "inconclusive"),
])
def test_classify(doc, code, outcome):
    assert cb.classify(doc, code)["outcome"] == outcome


def test_classify_keeps_errors_only_and_truncates():
    doc = {"status": "failed", "diagnostics": [
        {"severity": "warning", "message": "w"}, {"severity": "error", "message": "x" * 500, "code": "E1"}]}
    (d,) = cb.classify(doc, 1)["diagnostics"]
    assert d["code"] == "E1" and len(d["message"]) == 300


def test_verify_text_parses_json_after_preamble(monkeypatch):
    class Proc:
        returncode, stdout = 0, 'log line\n{"status": "success", "diagnostics": []}'
    monkeypatch.setattr(cb.subprocess, "run", lambda *a, **k: Proc())
    assert cb.verify_text("mumei", FIXED, 5)["outcome"] == "proven"


def test_verify_text_timeout_is_inconclusive(monkeypatch):
    def boom(*a, **k):
        raise cb.subprocess.TimeoutExpired("mumei", 5)
    monkeypatch.setattr(cb.subprocess, "run", boom)
    assert cb.verify_text("mumei", FIXED, 5) == {"outcome": "inconclusive", "status": "timeout", "diagnostics": []}


# --- reference arm and vacuity control ---------------------------------------

def test_vacuity_text_replaces_only_target_ensures(repo):
    (case,) = cb.load_cases()[0]
    text = cb.vacuity_text(case)
    assert "ensures: false;" in text and "result == total / days" not in text and "if days <= 0" in text


@pytest.mark.parametrize("control,expected", [("refuted", "ok"), ("proven", "vacuous"), ("inconclusive", "inconclusive")])
def test_run_mumei_case_vacuity(repo, monkeypatch, control, expected):
    monkeypatch.setattr(cb, "verify_text", fake_verify([("ensures: false", control)] + REFERENCE[1:]))
    (case,) = cb.load_cases()[0]
    r = cb.run_mumei_case(case, "mumei", 5)
    assert (r["buggy"]["outcome"], r["fixed"]["outcome"], r["vacuity"]) == ("refuted", "proven", expected)


# --- LLM arms -----------------------------------------------------------------

@pytest.mark.parametrize("reply,outcome", [
    ('{"verdict": "violated", "witness": "days=0"}', "refuted"),
    ('{"verdict": "holds"}', "proven"),
    ('```json\n{"verdict": "holds"}\n```', "proven"),
    ('{"verdict": "maybe"}', "inconclusive"),
    ("not json", "inconclusive"),
    ("[1, 2]", "inconclusive"),
])
def test_llm_arm_verdicts(repo, reply, outcome):
    (case,) = cb.load_cases()[0]
    r = cb.run_llm_case(case, StubProvider(lambda m, s: reply), "llm", 0, None, 5)
    assert r["buggy"]["outcome"] == r["fixed"]["outcome"] == outcome


def test_llm_prompt_has_no_ground_truth_or_ports(repo):
    (case,) = cb.load_cases()[0]
    for v in cb.VARIANTS:
        text = json.dumps(cb.llm_prompt(case, v))
        assert "division-by-zero" not in text and "DEFECTS" not in text and "if days <= 0 { 0 }" not in text
        assert HEADER.rstrip() in json.loads(text)[1]["content"]
        assert case["requirement"] in text and case["native"][v].split("\n")[1] in json.loads(text)[1]["content"]


def test_port_prompt_pins_header_without_bodies(repo):
    (case,) = cb.load_cases()[0]
    text = cb.port_prompt(case, "fixed")[1]["content"]
    assert HEADER in text and "if days <= 0 { 0 }" not in text and "division-by-zero" not in text


def test_mumei_llm_assembles_body_under_pinned_header(repo, monkeypatch):
    seen = []

    def verify(_bin, text, _t):
        seen.append(text)
        return {"outcome": "proven", "status": "success", "diagnostics": []}
    monkeypatch.setattr(cb, "verify_text", verify)
    (case,) = cb.load_cases()[0]
    reply = json.dumps({"body": "        if days <= 0 { 0 } else { total / days }"})
    r = cb.run_llm_case(case, StubProvider(lambda m, s: reply), "mumei-llm", 0, "mumei", 5)
    assert r["fixed"]["outcome"] == "proven" and seen[0].startswith(HEADER) and seen[0] == cb.assemble(case, json.loads(reply)["body"])


@pytest.mark.parametrize("reply", ['{"body": ""}', '{"body": 3}', "nope",
                                   '{"body": "0\\n    }\\natom evil(x: i64) -> i64 requires: true; ensures: true; body: { 0 }"}'])
def test_mumei_llm_rejects_missing_or_escaping_body(repo, monkeypatch, reply):
    monkeypatch.setattr(cb, "verify_text", lambda *a: pytest.fail("must not verify"))
    (case,) = cb.load_cases()[0]
    r = cb.run_llm_case(case, StubProvider(lambda m, s: reply), "mumei-llm", 0, "mumei", 5)
    assert r["buggy"]["outcome"] == "inconclusive" and r["buggy"]["status"] == "no-body"


def test_provider_error_is_inconclusive(repo):
    class Failing(StubProvider):
        def complete(self, messages, seed):
            raise RuntimeError("LLM request failed: HTTP 500")
    (case,) = cb.load_cases()[0]
    r = cb.run_llm_case(case, Failing(None), "llm", 0, None, 5)
    assert r["buggy"] == {"outcome": "inconclusive", "status": "LLM request failed: HTTP 500", "usage": None}


# --- scoring and aggregation ------------------------------------------------

def rec(i, lang, b, f, vac="ok", cost=None):
    usage = None if cost is None else {"cost_usd": cost, "seconds": 1.0}
    return {"id": i, "language": lang, "case_hash": "h", "source_hash": "s", "vacuity": vac,
            "buggy": {"outcome": b, "usage": usage}, "fixed": {"outcome": f, "usage": usage}}


def test_score_counts_every_kind():
    s = cb.score([rec("a", "go", "refuted", "proven"), rec("b", "go", "proven", "refuted"),
                  rec("c", "go", "inconclusive", "proven", vac="vacuous"), rec("d", "go", "refuted", "inconclusive")])
    assert s == {"cases": 4, "buggy_refuted": 2, "fixed_proven": 2, "both": 1, "wrong_accept": 1,
                 "wrong_reject": 1, "inconclusive": 2, "errors": 0, "vacuous": 1}


def test_score_separates_transport_errors():
    r = rec("a", "go", "inconclusive", "inconclusive")
    r["buggy"]["status"] = "LLM request failed: HTTP 429"
    s = cb.score([r])
    assert (s["errors"], s["inconclusive"]) == (1, 1)


def test_llm_runs_raise_retry_budget(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    prov = StubProvider(lambda m, s: '{"verdict": "holds"}')
    prov.retries = 2
    assert cb.main(["--arm", "llm", "--jobs", "1"], provider=prov) == 0
    assert prov.retries == cb.RATE_LIMIT_RETRIES


def test_usage_total_counts_unknown_cost():
    u = cb.usage_total([rec("a", "go", "refuted", "proven", cost=0.25), rec("b", "go", "refuted", "proven")])
    assert u == {"calls": 2, "cost_usd": 0.5, "model_seconds": 2.0, "cost_unknown_calls": 0}
    r = rec("c", "go", "refuted", "proven")
    r["buggy"]["usage"] = {"cost_usd": None, "seconds": 1}
    assert cb.usage_total([r])["cost_unknown_calls"] == 1


@pytest.mark.parametrize("values,expected", [([3], 3), ([1, 5, 2], 2), ([1, 2, 3, 4], 2.5)])
def test_median(values, expected):
    assert cb.median(values) == expected


def test_arm_rows_medians_ranges_and_languages():
    runs = [[rec("a", "go", "refuted", "proven"), rec("b", "rust", "proven", "proven")],
            [rec("a", "go", "refuted", "proven"), rec("b", "rust", "refuted", "proven")],
            [rec("a", "go", "proven", "proven"), rec("b", "rust", "refuted", "proven")]]
    (row,) = cb.arm_rows([{"arm": "llm", "model": "m", "runs": runs}])
    assert row["runs"] == 3 and row["both"] == 1 and row["both_range"] == (1, 2)
    assert row["by_language"]["go"]["both"] == 1 and row["by_language"]["rust"]["cases"] == 1
    assert "python" not in row["by_language"]


def test_arm_rows_order_reference_first():
    docs = [{"arm": a, "model": m, "runs": [[rec("a", "go", "refuted", "proven")]]}
            for a, m in (("mumei-llm", "m"), ("llm", "m"), ("mumei", None))]
    assert [r["arm"] for r in cb.arm_rows(docs)] == ["mumei", "llm", "mumei-llm"]


def test_render_table_shows_ranges_and_cost():
    runs = [[rec("a", "go", "refuted", "proven", cost=0.1)], [rec("a", "go", "proven", "proven", cost=0.1)]]
    table = cb.render_table(cb.arm_rows([{"arm": "llm", "model": "m", "runs": runs}]))
    assert "| LLM only (judges the source) | m | 2 |" in table and "(0–1)" in table and "$0.40" in table


# --- staleness, offline check, rendering --------------------------------------

VERIFIER = {"version": "mumei 0.0.0", "commit": "0" * 40, "dirty": False}


def run_reference(repo, monkeypatch):
    monkeypatch.setattr(cb, "verify_text", fake_verify(REFERENCE))
    monkeypatch.setattr(cb, "verifier_identity", lambda _bin: dict(VERIFIER))
    assert cb.main(["--arm", "mumei", "--mumei-bin", "mumei"]) == 0


def test_reference_run_writes_results_and_renders(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    doc = json.loads((repo / "proofs" / "results" / "mumei.json").read_text())
    assert doc["arm"] == "mumei" and doc["prompt_hash"] is None
    assert cb.score(doc["runs"][0])["both"] == 1
    md = (repo / "proofs" / "RESULTS.md").read_text()
    assert "1 / 1 pass" in md and "Generated by scripts/run_contract_bench.py" in md
    readme = (repo / "README.md").read_text()
    assert "old" not in readme and "proofs/RESULTS.md" in readme and readme.endswith("tail\n")


def test_check_passes_offline_without_mumei_or_model(repo, monkeypatch, capsys):
    run_reference(repo, monkeypatch)
    monkeypatch.setattr(cb, "verify_text", lambda *a: pytest.fail("check must not verify"))
    monkeypatch.setattr(cb.llm_only, "provider_from_env", lambda **k: pytest.fail("check must not call a model"))
    real_run = cb.subprocess.run
    monkeypatch.setattr(cb.subprocess, "run", lambda *a, **k: pytest.fail("check must not run mumei")
                        if a and a[0] and a[0][0] != "git" else real_run(*a, **k))
    assert cb.main(["--check"]) == 0
    assert "1 cases, 0 problem(s)" in capsys.readouterr().out


@pytest.mark.parametrize("mutate,message", [
    (lambda r: (r / "proofs/python/py-09-x/PY09-D01/fixed.mm").write_text(FIXED.replace("{ 0 }", "{ 0 + 0 }")), "PY09-D01 is stale"),
    (lambda r: (r / "specimens/python/py-09-x/app.py").write_text(APP + "\n# edit\n"), "PY09-D01 is stale"),
    (lambda r: (r / "proofs/RESULTS.md").write_text("hand edit"), "RESULTS.md is out of date"),
    (lambda r: (r / "README.md").write_text((r / "README.md").read_text().replace("Details", "Detail")), "README.md is out of date"),
])
def test_check_rejects_stale_inputs(repo, monkeypatch, capsys, mutate, message):
    run_reference(repo, monkeypatch)
    mutate(repo)
    assert cb.main(["--check"]) == 1
    assert message in capsys.readouterr().err


def test_check_reports_case_without_result(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    doc = json.loads((repo / "proofs/results/mumei.json").read_text())
    doc["runs"][0] = []
    (repo / "proofs/results/mumei.json").write_text(json.dumps(doc))
    assert any("PY09-D01 has no result" in s for s in cb.stale_records(cb.load_cases()[0], cb.load_results()))


def test_prompt_change_marks_llm_results_stale(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    (case,) = cb.load_cases()[0]
    cb.write_result("llm", "stub/model-1", [[cb.run_llm_case(case, StubProvider(lambda m, s: '{"verdict": "holds"}'), "llm", 0, None, 5)]])
    assert cb.stale_records(cb.load_cases()[0], cb.load_results()) == []
    monkeypatch.setattr(cb, "LLM_SYSTEM", cb.LLM_SYSTEM + " changed")
    assert "llm (stub/model-1): prompt changed" in cb.stale_records(cb.load_cases()[0], cb.load_results())


def test_check_fails_on_case_errors(repo, capsys):
    (repo / "proofs/python/py-09-x/PY09-D01/buggy.mm").write_text("trusted " + BUGGY)
    assert cb.main(["--check"]) == 1
    assert "must not use trusted" in capsys.readouterr().err


def test_run_refuses_invalid_cases(repo, monkeypatch):
    (repo / "proofs/python/py-09-x/PY09-D01/buggy.mm").write_text("trusted " + BUGGY)
    monkeypatch.setattr(cb, "verify_text", lambda *a: pytest.fail("must not verify"))
    assert cb.main(["--arm", "mumei", "--mumei-bin", "mumei"]) == 1


def test_replace_block_without_markers():
    assert cb.replace_block("no markers", "x") is None


def test_llm_runs_record_seeds_and_never_write_the_key(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    seeds = []
    prov = StubProvider(lambda m, s: seeds.append(s) or '{"verdict": "violated"}')
    prov.api_key = SENTINEL_KEY
    assert cb.main(["--arm", "llm", "--runs", "2", "--jobs", "1"], provider=prov) == 0
    assert sorted(set(seeds)) == [0, 1]
    path = repo / "proofs/results/llm-stub-model-1.json" if (repo / "proofs/results/llm-stub-model-1.json").exists() else next((repo / "proofs/results").glob("llm-*.json"))
    doc = json.loads(path.read_text())
    assert len(doc["runs"]) == 2 and doc["prompt_hash"] == cb.prompt_hash()
    for p in [path, repo / "proofs/RESULTS.md", repo / "README.md"]:
        assert SENTINEL_KEY not in p.read_text()


def test_missing_mumei_binary(repo):
    with pytest.raises(SystemExit, match="mumei binary not found"):
        cb.main(["--arm", "mumei-llm", "--mumei-bin", ""])


# --- the committed corpus ------------------------------------------------------

def test_committed_cases_cover_every_target_defect():
    cases, errors = cb.load_cases()
    assert errors == []
    assert {c["id"] for c in cases} == {d["id"] for _, _, d in cb.target_defects()}
    assert all(c["functions"]["buggy"] and c["functions"]["fixed"] for c in cases)


def test_markdown_lists_wrong_answers_per_case():
    llm = {"arm": "mumei-llm", "model": "m", "runs": [
        [rec("A", "go", "proven", "proven"), rec("B", "go", "refuted", "refuted")],
        [rec("A", "go", "proven", "proven"), rec("B", "go", "refuted", "proven")],
    ]}
    rows = cb.arm_rows([llm])
    text = cb.render_markdown(rows, [llm], [])
    assert "`A` buggy accepted (2/2)" in text and "`B` fixed rejected (1/2)" in text
    assert "translation problem" in text


def test_markdown_omits_wrong_answer_section_when_all_right():
    llm = {"arm": "llm", "model": "m", "runs": [[rec("A", "go", "refuted", "proven")]]}
    assert "Wrong answers by case" not in cb.render_markdown(cb.arm_rows([llm]), [llm], [])


def test_markdown_shows_llm_witness_for_fixed_rejections():
    r = rec("A", "go", "refuted", "refuted")
    r["fixed"]["reply"] = {"verdict": "violated", "witness": "epoch =\n max i64", "reason": "x"}
    llm = {"arm": "llm", "model": "m", "runs": [[r]]}
    text = cb.render_markdown(cb.arm_rows([llm]), [llm], [])
    assert "`A` fixed rejected, witness: epoch = max i64" in text


@pytest.mark.parametrize("message,outcome", [
    ("Verification Error: Unknown function: %", "inconclusive"),
    ("Verification Error: Unknown function: overflow", "inconclusive"),
    ("Verification Error: Unknown function: invariant_holds", "inconclusive"),
    ("Verification Error: Potential division by zero. Counter-example: d = 0", "refuted"),
    ("Verification Error: Call to 'f': precondition (requires) not satisfied", "refuted"),
])
def test_classify_refutes_only_on_verification_failures(message, outcome):
    doc = {"status": "failed", "diagnostics": [{"severity": "error", "message": message}]}
    assert cb.classify(doc, 1)["outcome"] == outcome


def test_classify_failed_without_diagnostics_is_inconclusive():
    assert cb.classify({"status": "failed", "diagnostics": []}, 1)["outcome"] == "inconclusive"


def test_check_reports_case_missing_from_one_run(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    (case,) = cb.load_cases()[0]
    r = cb.run_llm_case(case, StubProvider(lambda m, s: '{"verdict": "holds"}'), "llm", 0, None, 5)
    cb.write_result("llm", "stub/model-1", [[r], []])
    assert "llm (stub/model-1): PY09-D01 has no result in run 2" in cb.stale_records(cb.load_cases()[0], cb.load_results())


def test_check_fails_without_reference_result(repo, capsys):
    assert cb.main(["--check"]) == 1
    assert "no reference result" in capsys.readouterr().err


def test_prompt_template_change_marks_llm_results_stale(repo, monkeypatch):
    before = cb.prompt_hash()

    def other_prompt(case, variant):
        return []

    monkeypatch.setattr(cb, "llm_prompt", other_prompt)
    assert cb.prompt_hash() != before


def test_only_merges_into_committed_result(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    doc = json.loads((repo / "proofs/results/mumei.json").read_text())
    doc["runs"][0].append({**doc["runs"][0][0], "id": "OTHER"})
    (repo / "proofs/results/mumei.json").write_text(json.dumps(doc))
    assert cb.main(["--arm", "mumei", "--mumei-bin", "mumei", "--only", "PY09-D01"]) == 0
    ids = sorted(r["id"] for r in json.loads((repo / "proofs/results/mumei.json").read_text())["runs"][0])
    assert ids == ["OTHER", "PY09-D01"]


def test_only_refuses_to_merge_other_run_count(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    (case,) = cb.load_cases()[0]
    prov = StubProvider(lambda m, s: '{"verdict": "holds"}')
    r = cb.run_llm_case(case, prov, "llm", 0, None, 5)
    cb.write_result("llm", prov.model, [[r], [r]])
    with pytest.raises(SystemExit, match="rerun without --only"):
        cb.main(["--arm", "llm", "--runs", "1", "--only", "PY09-D01"], provider=prov)


CONTRADICTION = "Verification Error: Spec contradiction in atom 'f': ensures clause 1 is inconsistent with requires"


@pytest.mark.parametrize("message,buggy,vacuity", [
    (CONTRADICTION, "refuted", "ok"),
    (CONTRADICTION, "proven", "inconclusive"),
    ("Verification Error: Unknown function: %", "refuted", "inconclusive"),
])
def test_vacuity_control_accepts_spec_contradiction_only_with_a_refuted_buggy_port(repo, message, buggy, vacuity, monkeypatch):
    def verify(_bin, text, _timeout):
        if "ensures: false" in text:
            return {"outcome": "inconclusive", "status": "failed", "diagnostics": [{"message": message}]}
        outcome = buggy if "total / days\n" in text else "proven"
        return {"outcome": outcome, "status": outcome, "diagnostics": []}
    monkeypatch.setattr(cb, "verify_text", verify)
    (case,) = cb.load_cases()[0]
    assert cb.run_mumei_case(case, "mumei", 5)["vacuity"] == vacuity


def test_check_reports_duplicate_case_in_a_run(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    doc = json.loads((repo / "proofs/results/mumei.json").read_text())
    doc["runs"][0] *= 2
    (repo / "proofs/results/mumei.json").write_text(json.dumps(doc))
    assert "mumei (reference): PY09-D01 appears more than once in run 1" in cb.stale_records(cb.load_cases()[0], cb.load_results())


def test_only_needs_a_committed_result(repo, monkeypatch):
    monkeypatch.setattr(cb, "verify_text", fake_verify(REFERENCE))
    with pytest.raises(SystemExit, match="run every case before using --only"):
        cb.main(["--arm", "mumei", "--mumei-bin", "mumei", "--only", "PY09-D01"])


def _git(cwd, *args):
    import subprocess
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _fake_mumei(directory):
    binary = directory / "mumei"
    binary.write_text("#!/bin/sh\necho 'mumei 9.9.9'\n")
    binary.chmod(0o755)
    return binary


def test_reference_result_records_the_verifier(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    doc = json.loads((repo / "proofs" / "results" / "mumei.json").read_text())
    assert doc["verifier"] == VERIFIER
    assert list(doc)[-1] == "runs"


@pytest.mark.parametrize("dirty", [False, True])
def test_verifier_identity_reads_the_checkout_commit(tmp_path, dirty):
    checkout = tmp_path / "mumei"
    (checkout / "target" / "debug").mkdir(parents=True)
    (checkout / "src.rs").write_text("fn main() {}\n")
    _git(checkout, "init", "-q")
    _git(checkout, "add", "src.rs")
    _git(checkout, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "init")
    if dirty:
        (checkout / "src.rs").write_text("fn main() { println!(); }\n")
    binary = _fake_mumei(checkout / "target" / "debug")
    got = cb.verifier_identity(str(binary))
    assert got["version"] == "mumei 9.9.9"
    assert got["commit"] is not None and len(got["commit"]) == 40
    assert got["dirty"] is dirty


def test_verifier_identity_outside_a_checkout(tmp_path):
    binary = _fake_mumei(tmp_path)
    got = cb.verifier_identity(str(binary))
    assert got == {"version": "mumei 9.9.9", "commit": None, "dirty": None}


@pytest.mark.parametrize("binary", ["/nonexistent/mumei", "definitely-not-a-mumei-binary"])
def test_verifier_identity_without_a_binary(binary):
    got = cb.verifier_identity(binary)
    assert got["version"] is None and got["commit"] is None


def test_llm_result_has_no_verifier(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    (case,) = cb.load_cases()[0]
    r = cb.run_llm_case(case, StubProvider(lambda m, s: '{"verdict": "holds"}'), "llm", 0, None, 5)
    path = cb.write_result("llm", "stub/model-1", [[r]], "mumei")
    assert "verifier" not in json.loads(path.read_text())


@pytest.mark.parametrize("verifier", [None, {}, {"version": "mumei 0.6.23", "commit": None, "dirty": None}])
def test_check_requires_the_reference_verifier_commit(repo, monkeypatch, capsys, verifier):
    run_reference(repo, monkeypatch)
    path = repo / "proofs" / "results" / "mumei.json"
    doc = json.loads(path.read_text())
    if verifier is None:
        del doc["verifier"]
    else:
        doc["verifier"] = verifier
    path.write_text(json.dumps(doc))
    assert cb.main(["--check"]) == 1
    assert "does not record the mumei commit" in capsys.readouterr().err


# --- llm-contract arm --------------------------------------------------------

BLIND_REQUIRES = "total >= 0 && days >= (0 - 5)"
BLIND_ENSURES = "(days <= 0 => result == 0) && (days > 0 => result == total / days)"
BLIND_REPLY = json.dumps({"requires": BLIND_REQUIRES, "ensures": BLIND_ENSURES})


def test_contract_prompt_hides_code_and_reference_contract(repo):
    (case,) = cb.load_cases()[0]
    text = "\n".join(m["content"] for m in cb.contract_prompt(case))
    assert cb.signature(case) == "atom average(total: i64, days: i64) -> i64"
    assert cb.signature(case) in text and case["requirement"] in text
    for hidden in ("requires: total >= 0", "result == total / days", "total // days", "if days <= 0", "body:"):
        assert hidden not in text


@pytest.mark.parametrize("notes, expected", [
    ("", ""),
    ("Err is ok == false.", "Err is ok == false."),
    ("`unchecked` uint256 wrap-around is modelled as the exact difference going below 0; "
     "the fixed version's checked subtraction reverts (ok == false).",
     "`unchecked` uint256 wrap-around is modelled as the exact difference going below 0; a revert is ok == false."),
    ("Raising is ok == false. `distinct_open` stands for the fixed version's closed/same-account check.",
     "Raising is ok == false. `distinct_open` stands for the check that both accounts are open and different."),
    ("Account state is passed in; Err is ok == false. In the original, the allowance comes from the wrapping "
     "remaining_daily_allowance, so an overspent account never hits the limit check; the fixed version also "
     "subtracts already queued amounts. Same-account and closed checks are outside the ported part.",
     "Account state is passed in; Err is ok == false. Same-account and closed checks are outside the ported part."),
])
def test_blind_notes_rewrite_wording_about_either_implementation(notes, expected):
    assert cb.blind_notes(notes) == expected


@pytest.mark.parametrize("case_id, kept", [
    ("SOL03-D02", "ok == false"),
    ("GO01-D04", "`has_sku`"),
    ("PY03-D01", "`distinct_open` stands for"),
    ("GO02-D03", "A negative -top is rejected"),
])
def test_blind_notes_keep_the_modelling_conventions(case_id, kept):
    cases, _ = cb.load_cases()
    (case,) = [c for c in cases if c["id"] == case_id]
    assert kept in cb.blind_notes(case["notes"])


def test_contract_prompt_uses_the_blind_notes(repo, monkeypatch):
    (case,) = cb.load_cases()[0]
    monkeypatch.setattr(cb, "BLIND_NOTE_REWRITES", (("the fixed version returns 0", "a zero result is 0"),))
    case = {**case, "notes": "Days are whole; the fixed version returns 0."}
    text = "\n".join(m["content"] for m in cb.contract_prompt(case))
    assert "Modelling notes: Days are whole; a zero result is 0.\n" in text and "fixed version" not in text


def test_prompt_hash_covers_the_blind_note_rewrites(monkeypatch):
    before = cb.prompt_hash("llm-contract")
    monkeypatch.setattr(cb, "BLIND_NOTE_REWRITES", cb.BLIND_NOTE_REWRITES + (("x", "y"),))
    assert cb.prompt_hash("llm-contract") != before


def test_committed_notes_leak_nothing_to_the_blind_arm():
    cases, _ = cb.load_cases()
    leaks = [c["id"] for c in cases if cb.BLIND_NOTE_LEAK.search(cb.blind_notes(c["notes"]))]
    assert leaks == []


@pytest.mark.parametrize("error", ["LLM request failed: HTTP 500", "LLM response has no message content"])
def test_contract_request_failure_is_one_error(repo, error):
    class Failing(StubProvider):
        def complete(self, messages, seed):
            raise RuntimeError(error)
    (case,) = cb.load_cases()[0]
    r = cb.run_contract_case(case, Failing(None), 0, "mumei", 5)
    assert all(r[v]["status"].startswith(cb.TRANSPORT_ERROR) for v in cb.VARIANTS)
    s = cb.score([r])
    assert s["errors"] == 1 and s["inconclusive"] == 0


def test_contract_header_replaces_only_the_clauses(repo):
    (case,) = cb.load_cases()[0]
    header = cb.contract_header(case, "a > 0", "result == a")
    assert header == "atom average(total: i64, days: i64) -> i64\n    requires: a > 0;\n    ensures: result == a;\n    "
    assert cb.header_ensures(header) == "result == a"


@pytest.mark.parametrize("reply, expected", [
    ({"requires": "true", "ensures": "result >= 0"}, ("true", "result >= 0")),
    ({"requires": "a > 0;", "ensures": "result == a ;"}, ("a > 0", "result == a")),
    ({"requires": "a > 0\n  && b > 0", "ensures": "result\t== a"}, ("a > 0 && b > 0", "result == a")),
    ({"requires": "!found", "ensures": "!result.ok"}, ("!found", "!result.ok")),
    ({"requires": "true"}, None),
    ({"ensures": "true"}, None),
    ({"requires": 1, "ensures": "true"}, None),
    ({"requires": "true", "ensures": ["result"]}, None),
    ({"requires": "", "ensures": "true"}, None),
    ({"requires": "true", "ensures": " ; "}, None),
    ({"requires": "true", "ensures": "a; ensures: true"}, None),
    ({"requires": "true", "ensures": "true body: { 0 }"}, None),
    ({"requires": "true", "ensures": "true\natom evil() -> i64"}, None),
    ({"requires": "trusted", "ensures": "true"}, None),
    ({"requires": "requires: true", "ensures": "true"}, None),
    ({"requires": "true", "ensures": "x" * 2001}, None),
    (None, None),
])
def test_contract_clauses_accept_only_single_expressions(reply, expected):
    assert cb.contract_clauses(reply) == expected


def test_contract_clauses_keep_names_that_contain_keywords():
    assert cb.contract_clauses({"requires": "atomic > 0 && bodyless", "ensures": "result == ensures_count"}) == \
        ("atomic > 0 && bodyless", "result == ensures_count")


def recording_verify(seen):
    inner = fake_verify(REFERENCE)

    def verify(b, text, t):
        seen.append(text)
        return inner(b, text, t)
    return verify


def test_contract_case_checks_both_reference_bodies_under_one_contract(repo, monkeypatch):
    seen = []
    monkeypatch.setattr(cb, "verify_text", recording_verify(seen))
    (case,) = cb.load_cases()[0]
    r = cb.run_contract_case(case, StubProvider(lambda m, s: BLIND_REPLY), 0, "mumei", 5)
    assert r["contract"] == {"requires": BLIND_REQUIRES, "ensures": BLIND_ENSURES}
    assert (r["buggy"]["outcome"], r["fixed"]["outcome"], r["vacuity"]) == ("refuted", "proven", "ok")
    assert len(seen) == 3
    for text in seen:
        assert f"requires: {BLIND_REQUIRES};" in text and "requires: total >= 0;" not in text
    assert "total / days\n" in seen[0] and "if days <= 0" in seen[1] and "ensures: false;" in seen[2]
    assert r["usage"]["cost_usd"] == 0.001 and cb.usage_total([r])["calls"] == 1


@pytest.mark.parametrize("outcomes, expected", [
    ([("ensures: false", "refuted"), ("body", "proven")], ("proven", "proven", "ok")),
    ([("ensures: false", "refuted"), ("body", "refuted")], ("refuted", "refuted", "ok")),
    ([("ensures: false", "proven"), ("body", "proven")], ("proven", "proven", "vacuous")),
    ([("body", "inconclusive")], ("inconclusive", "inconclusive", "inconclusive")),
])
def test_contract_case_scores_weak_strong_and_vacuous_contracts(repo, monkeypatch, outcomes, expected):
    monkeypatch.setattr(cb, "verify_text", fake_verify(outcomes))
    (case,) = cb.load_cases()[0]
    r = cb.run_contract_case(case, StubProvider(lambda m, s: BLIND_REPLY), 0, "mumei", 5)
    assert (r["buggy"]["outcome"], r["fixed"]["outcome"], r["vacuity"]) == expected


@pytest.mark.parametrize("reply", ["not json", '{"requires": "true"}', '{"requires": "true", "ensures": "a; b"}', "[]"])
def test_contract_case_without_a_usable_contract_is_inconclusive(repo, monkeypatch, reply):
    monkeypatch.setattr(cb, "verify_text", lambda *a: pytest.fail("must not verify"))
    (case,) = cb.load_cases()[0]
    r = cb.run_contract_case(case, StubProvider(lambda m, s: reply), 0, "mumei", 5)
    assert r["buggy"] == r["fixed"] == {"outcome": "inconclusive", "status": "no-contract"}
    assert "contract" not in r and r["reply"] == reply
    s = cb.score([r])
    assert (s["inconclusive"], s["errors"], s["both"]) == (2, 0, 0)


def test_contract_case_transport_error_counts_as_error(repo, monkeypatch):
    monkeypatch.setattr(cb, "verify_text", lambda *a: pytest.fail("must not verify"))
    (case,) = cb.load_cases()[0]

    def boom(m, s):
        raise RuntimeError("LLM request failed: HTTP 429")
    r = cb.run_contract_case(case, StubProvider(boom), 0, "mumei", 5)
    assert r["usage"] is None and cb.score([r])["errors"] == 1


def test_prompt_hash_is_per_arm():
    assert cb.prompt_hash() == cb.prompt_hash("llm") == cb.prompt_hash("mumei-llm")
    assert cb.prompt_hash("llm-contract") != cb.prompt_hash()


def test_contract_prompt_change_marks_only_that_arm_stale(repo, monkeypatch):
    llm_hash = cb.prompt_hash()
    before = cb.prompt_hash("llm-contract")
    monkeypatch.setattr(cb, "CONTRACT_SYSTEM", cb.CONTRACT_SYSTEM + " ")
    assert cb.prompt_hash("llm-contract") != before and cb.prompt_hash() == llm_hash


def run_blind(repo, monkeypatch, runs=1):
    run_reference(repo, monkeypatch)
    assert cb.main(["--arm", "llm-contract", "--runs", str(runs), "--jobs", "1", "--mumei-bin", "mumei"],
                   provider=StubProvider(lambda m, s: BLIND_REPLY)) == 0
    return json.loads((repo / "proofs" / "results" / "llm-contract-stub__model-1.json").read_text())


def test_main_runs_the_contract_arm_and_check_passes(repo, monkeypatch, capsys):
    doc = run_blind(repo, monkeypatch, runs=2)
    assert doc["prompt_hash"] == cb.prompt_hash("llm-contract") and doc["verifier"] == VERIFIER
    assert len(doc["runs"]) == 2 and doc["runs"][0][0]["contract"]["ensures"] == BLIND_ENSURES
    md = (repo / "proofs" / "RESULTS.md").read_text()
    assert cb.ARM_LABEL["llm-contract"] in md and cb.ARM_LABEL["llm-contract"] in (repo / "README.md").read_text()
    capsys.readouterr()
    assert cb.main(["--check"]) == 0, capsys.readouterr().err


def test_check_flags_a_contract_arm_verified_by_another_build(repo, monkeypatch, capsys):
    run_blind(repo, monkeypatch)
    path = repo / "proofs" / "results" / "llm-contract-stub__model-1.json"
    doc = json.loads(path.read_text())
    doc["verifier"] = {**VERIFIER, "commit": "1" * 40}
    path.write_text(json.dumps(doc))
    capsys.readouterr()
    assert cb.main(["--check"]) == 1
    assert "llm-contract" in capsys.readouterr().err


def test_check_flags_a_contract_arm_with_another_prompt(repo, monkeypatch, capsys):
    run_blind(repo, monkeypatch)
    monkeypatch.setattr(cb, "CONTRACT_SYSTEM", cb.CONTRACT_SYSTEM + " changed")
    assert cb.main(["--check"]) == 1
    err = capsys.readouterr().err
    assert "llm-contract (stub/model-1): prompt changed" in err and "llm (" not in err


def test_only_merges_into_the_contract_arm_result(repo, monkeypatch):
    run_blind(repo, monkeypatch)
    assert cb.main(["--arm", "llm-contract", "--only", "PY09-D01", "--jobs", "1", "--mumei-bin", "mumei"],
                   provider=StubProvider(lambda m, s: BLIND_REPLY)) == 0


def test_contract_arm_needs_mumei(repo):
    with pytest.raises(SystemExit, match="mumei binary not found"):
        cb.main(["--arm", "llm-contract", "--mumei-bin", ""])


def test_wrong_contract_answers_are_listed(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    monkeypatch.setattr(cb, "verify_text", fake_verify([("ensures: false", "refuted"), ("body", "proven")]))
    assert cb.main(["--arm", "llm-contract", "--jobs", "1", "--mumei-bin", "mumei"],
                   provider=StubProvider(lambda m, s: BLIND_REPLY)) == 0
    md = (repo / "proofs" / "RESULTS.md").read_text()
    assert "`PY09-D01` buggy accepted (1/1)" in md
    assert f"`PY09-D01` model's ensures (from a wrong run): `{BLIND_ENSURES}`" in md
    assert "vacuity control not passed" not in md
    assert "per run: 1 / 1 pass" in md
    assert "contract-writing error" in md


def _contract_rec(i, b, f, ensures, vac="ok"):
    r = rec(i, "go", b, f, vac=vac)
    r["contract"] = {"requires": "true", "ensures": ensures}
    r["usage"] = {"cost_usd": 0.0, "seconds": 1.0}
    return r


def test_wrong_answer_contract_comes_from_a_wrong_run():
    runs = [[_contract_rec("A", "refuted", "proven", "right")],
            [_contract_rec("A", "refuted", "refuted", "too strong", vac="inconclusive")]]
    md = cb.render_markdown([], [{"arm": "llm-contract", "model": "m", "runs": runs}], [])
    assert "`A` fixed rejected (1/2)" in md
    assert "`A` model's ensures (from a wrong run): `too strong` — vacuity control not passed in that run" in md
    assert "`right`" not in md
    assert "per run: 1 / 1, 0 / 1 pass" in md


def test_score_counts_a_failed_contract_request_once():
    r = rec("a", "go", "inconclusive", "inconclusive")
    r["usage"] = None
    for v in cb.VARIANTS:
        r[v]["status"] = "LLM request failed: HTTP 429"
    assert (cb.score([r])["errors"], cb.score([r])["inconclusive"]) == (1, 0)


def test_score_counts_a_missing_contract_per_variant():
    r = rec("a", "go", "inconclusive", "inconclusive")
    r["usage"] = {"cost_usd": 0.0}
    for v in cb.VARIANTS:
        r[v]["status"] = "no-contract"
    assert (cb.score([r])["errors"], cb.score([r])["inconclusive"]) == (0, 2)



def _checkout(tmp_path):
    checkout = tmp_path / "mumei"
    (checkout / "target" / "debug").mkdir(parents=True)
    (checkout / "src.rs").write_text("fn main() {}\n")
    _git(checkout, "init", "-q")
    _git(checkout, "add", "src.rs")
    _git(checkout, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "init")
    return checkout


def test_verifier_identity_ignores_a_binary_outside_target(tmp_path):
    checkout = _checkout(tmp_path)
    (checkout / "bin").mkdir()
    got = cb.verifier_identity(str(_fake_mumei(checkout / "bin")))
    assert got == {"version": "mumei 9.9.9", "commit": None, "dirty": None}


def test_verifier_identity_ignores_a_binary_older_than_the_checkout(tmp_path):
    import os
    checkout = _checkout(tmp_path)
    binary = _fake_mumei(checkout / "target" / "debug")
    os.utime(binary, (1_000_000_000, 1_000_000_000))
    got = cb.verifier_identity(str(binary))
    assert got["version"] == "mumei 9.9.9" and got["commit"] is None


def test_only_refuses_a_result_from_another_build(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    monkeypatch.setattr(cb, "verify_text", fake_verify(REFERENCE))
    monkeypatch.setattr(cb, "verifier_identity", lambda _bin: {**VERIFIER, "commit": "1" * 40})
    with pytest.raises(SystemExit, match="another mumei build"):
        cb.main(["--arm", "mumei", "--mumei-bin", "mumei", "--only", "PY09-D01"])


def test_only_merges_into_a_result_without_a_verifier_and_keeps_it_unrecorded(repo, monkeypatch):
    run_reference(repo, monkeypatch)
    (case,) = cb.load_cases()[0]
    prov = StubProvider(lambda m, s: "no port here")
    r = cb.run_llm_case(case, prov, "mumei-llm", 0, "mumei", 5)
    cb.write_result("mumei-llm", prov.model, [[r]])
    assert cb.main(["--arm", "mumei-llm", "--runs", "1", "--mumei-bin", "mumei", "--only", "PY09-D01"],
                   provider=prov) == 0
    assert "verifier" not in json.loads(cb.result_path("mumei-llm", prov.model).read_text())
