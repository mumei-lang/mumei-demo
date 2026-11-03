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
    ({"status": "failed", "diagnostics": [{"severity": "error", "message": "Postcondition", "atom": "f"}]}, 1, "refuted"),
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
        assert "division-by-zero" not in text and "DEFECTS" not in text and "ensures" not in text
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

def run_reference(repo, monkeypatch):
    monkeypatch.setattr(cb, "verify_text", fake_verify(REFERENCE))
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
