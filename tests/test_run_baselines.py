"""Unit tests for scripts/run_baselines.py.

No analyzer is run: tool output is fed in as parsed JSON, and the CLI tests
stub the tool runs."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "run_baselines.py"

spec = importlib.util.spec_from_file_location("run_baselines", SCRIPT)
rb = importlib.util.module_from_spec(spec)
sys.modules["run_baselines"] = rb
spec.loader.exec_module(rb)
rsa = rb.rsa


# --- parse_cwes / cwe_related ----------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (None, []),
    ("CWE-89: Improper Neutralization", [89]),
    (["CWE-79: XSS", "CWE-80: basic XSS"], [79, 80]),
    ({"id": 259, "link": "https://example.invalid/259"}, [259]),
    ([{"id": 78}, "CWE-78"], [78]),
    (502, [502]),
    (["no number here"], []),
    ([], []),
])
def test_parse_cwes(value, expected):
    assert rb.parse_cwes(value) == expected


@pytest.mark.parametrize("a,b,related", [
    (89, 89, True),
    (798, 259, True),
    (259, 321, True),
    (327, 328, True),
    (330, 338, True),
    (78, 77, True),
    (22, 23, True),
    (400, 770, True),
    (89, 79, False),
    (798, 327, False),
    (400, 404, False),
])
def test_cwe_related(a, b, related):
    assert rb.cwe_related(a, b) is related
    assert rb.cwe_related(b, a) is related


# --- enclosing_function ----------------------------------------------------

PY_SRC = """import os

TOKEN = "x"

class Handler:
    def do_get(self):
        x = 1
        return x

    async def fetch(self):
        await go()

def top():
    def inner():
        return 1
    return inner()

value = top()
"""


@pytest.mark.parametrize("line,expected", [
    (3, None),          # module-level constant
    (7, "do_get"),
    (8, "do_get"),
    (6, "do_get"),      # the def line itself
    (11, "fetch"),
    (15, "inner"),
    (16, "top"),        # back in the outer function after the nested def
    (18, None),         # module-level code after a function
    (0, None),
    (99, None),
])
def test_enclosing_function_python(line, expected):
    assert rb.enclosing_function(PY_SRC, line, "python") == expected


GO_SRC = """package main

var token = "x"

func (s *Store) Get(sku string) *Item {
	return s.items[sku]
}

func main() {
	run()
}
"""


@pytest.mark.parametrize("line,expected", [(3, None), (6, "Get"), (10, "main")])
def test_enclosing_function_go(line, expected):
    assert rb.enclosing_function(GO_SRC, line, "go") == expected


RS_SRC = """const LIMIT: u64 = 3;

impl Bank {
    pub fn deposit(&mut self) {
        self.n += 1;
    }
    pub(crate) async fn settle(&self) {}
    unsafe fn raw() {}
}

fn main() {
    let args = std::env::args();
}
"""


@pytest.mark.parametrize("line,expected", [
    (1, None), (5, "deposit"), (7, "settle"), (8, "raw"), (12, "main"),
])
def test_enclosing_function_rust(line, expected):
    assert rb.enclosing_function(RS_SRC, line, "rust") == expected


SOL_SRC = """contract Vault {
    uint256 public total;
    constructor(address o) {
        owner = o;
    }
    modifier onlyOwner() {
        _;
    }
    function deposit() external payable {
        total += msg.value;
    }
    receive() external payable {}
}
"""


@pytest.mark.parametrize("line,expected", [
    (2, None), (4, "constructor"), (7, "onlyOwner"), (10, "deposit"), (12, "receive"),
])
def test_enclosing_function_solidity(line, expected):
    assert rb.enclosing_function(SOL_SRC, line, "solidity") == expected


TS_SRC = """const LIMIT = 3;

export function renderResults(results: Task[]): string {
  if (results.length) {
    return "x";
  }
  return "";
}

export const invoiceId = (name: string) => {
  return name.replaceAll(" ", "-");
};

class Board {
  private move(id: number): void {
    for (const t of this.tasks) {
      t.id = id;
    }
  }
}

const handler = async (req) => {
  return req;
};
"""


@pytest.mark.parametrize("line,expected", [
    (1, None),
    (5, "renderResults"),  # `if (...) {` is not a method
    (11, "invoiceId"),
    (17, "move"),          # `for (...) {` is not a method
    (23, "handler"),
])
def test_enclosing_function_typescript(line, expected):
    assert rb.enclosing_function(TS_SRC, line, "typescript") == expected


def test_enclosing_function_unknown_language():
    assert rb.enclosing_function("def f():\n    pass\n", 2, "cobol") is None


# --- parsers ----------------------------------------------------------------

def _semgrep_result(path, line, check_id, category, cwe=None, message="msg"):
    meta = {"category": category}
    if cwe is not None:
        meta["cwe"] = cwe
    return {"path": path, "start": {"line": line}, "check_id": check_id,
            "extra": {"severity": "WARNING", "message": message, "metadata": meta}}


def test_parse_semgrep_keeps_security_and_correctness_only(tmp_path):
    doc = {"results": [
        _semgrep_result(str(tmp_path / "app.py"), 3, "python.sql", "security", ["CWE-89: SQL"]),
        _semgrep_result("app.py", 4, "python.mistake", "correctness"),
        _semgrep_result("app.py", 5, "sol.gas", "performance"),
        _semgrep_result("app.py", 6, "py.style", "best-practice"),
        _semgrep_result("app.py", 7, "py.nocat", None),
    ], "errors": [{"message": "parse"}]}
    findings, errors = rb.parse_semgrep(doc, tmp_path)
    assert [f["rule"] for f in findings] == ["python.sql", "python.mistake"]
    assert findings[0] == {"file": "app.py", "line": 3, "rule": "python.sql", "severity": "warning",
                           "cwe": [89], "message": "msg"}
    assert findings[1]["cwe"] == []
    assert errors == 1


def test_parse_semgrep_collapses_message_whitespace(tmp_path):
    doc = {"results": [_semgrep_result("a.go", 1, "r", "security", message="line one\n   line  two")]}
    findings, errors = rb.parse_semgrep(doc, tmp_path)
    assert findings[0]["message"] == "line one line two"
    assert errors == 0


def test_parse_semgrep_empty():
    assert rb.parse_semgrep({}, Path("/x")) == ([], 0)


def test_parse_bandit(tmp_path):
    doc = {"results": [{
        "filename": str(tmp_path / "pkg" / "app.py"), "line_number": 12, "test_id": "B608",
        "test_name": "hardcoded_sql_expressions", "issue_severity": "MEDIUM",
        "issue_cwe": {"id": 89, "link": "https://example.invalid"},
        "issue_text": "Possible SQL injection.",
    }], "errors": []}
    findings, errors = rb.parse_bandit(doc, tmp_path)
    assert findings == [{"file": "pkg/app.py", "line": 12, "rule": "B608:hardcoded_sql_expressions",
                         "severity": "medium", "cwe": [89], "message": "Possible SQL injection."}]
    assert errors == 0


def test_relpath_outside_scratch_kept(tmp_path):
    assert rb._relpath("/elsewhere/a.py", tmp_path) == "/elsewhere/a.py"
    assert rb._relpath("./a.py", tmp_path) == "a.py"


def test_normalize_adds_function_and_sorts(tmp_path):
    (tmp_path / "app.py").write_text("X = 1\n\ndef f():\n    return 2\n")
    raw = [
        {"file": "app.py", "line": 4, "rule": "b", "severity": "", "cwe": [], "message": "m"},
        {"file": "app.py", "line": 1, "rule": "a", "severity": "", "cwe": [], "message": "m"},
        {"file": "gone.py", "line": 1, "rule": "c", "severity": "", "cwe": [], "message": "m"},
    ]
    out = rb.normalize(raw, tmp_path, "python")
    assert [(f["file"], f["line"], f["function"]) for f in out] == [
        ("app.py", 1, None), ("app.py", 4, "f"), ("gone.py", 1, None)]


def test_normalize_drops_exact_duplicates(tmp_path):
    (tmp_path / "a.ts").write_text("const x = 1;\n")
    f = {"file": "a.ts", "line": 1, "rule": "r", "severity": "", "cwe": [], "message": "m"}
    out = rb.normalize([f, dict(f), dict(f, message="other"), dict(f, line=2)], tmp_path, "typescript")
    assert len(out) == 3


def test_finding_text():
    f = {"rule": "B608:sql", "function": "list_expenses", "line": 7, "cwe": [89], "message": "SQL"}
    assert rb.finding_text(f) == "B608:sql in `list_expenses` (line 7, CWE-89): SQL"
    f = {"rule": "r", "function": None, "line": 2, "cwe": [], "message": "m"}
    assert rb.finding_text(f) == "r (line 2): m"


# --- matching ---------------------------------------------------------------

DEFECT = {"id": "PY01-D01", "file": "app.py", "function": "Handler.list_expenses", "line": 40,
          "category": "sql-injection", "cwe": "CWE-89", "class": "vulnerability"}


def _f(line=40, function="list_expenses", file="app.py", rule="r", cwe=(), message="m"):
    return {"file": file, "line": line, "function": function, "rule": rule,
            "severity": "", "cwe": list(cwe), "message": message}


@pytest.mark.parametrize("finding,expected", [
    (_f(), True),
    (_f(line=200), True),                          # same function far away
    (_f(function=None, line=43), True),            # within LINE_SLACK
    (_f(function=None, line=37), True),
    (_f(function=None, line=44), False),
    (_f(function="other", line=200), False),
    (_f(function="other", line=41), True),         # nearby lines still count
    (_f(file="store.py"), False),
])
def test_located(finding, expected):
    assert rb.located(finding, DEFECT) is expected


def test_located_defect_without_line():
    d = dict(DEFECT, line=None)
    assert not rb.located(_f(function=None, line=1), d)


@pytest.mark.parametrize("finding,expected", [
    (_f(cwe=[89]), True),
    (_f(cwe=[79]), False),
    (_f(message="Possible SQL injection vector"), True),
    (_f(rule="python.lang.security.formatted-sql-query"), True),
    (_f(message="Use TLS"), False),
])
def test_category_evidence(finding, expected):
    assert rb.category_evidence(finding, DEFECT) is expected


def test_category_evidence_equivalent_cwe():
    d = dict(DEFECT, category="hardcoded-secret", cwe="CWE-798")
    assert rb.category_evidence(_f(cwe=[259], message="Possible hardcoded password"), d)
    assert rb.category_evidence(_f(cwe=[259], message="x"), d)


def test_category_evidence_defect_without_cwe_uses_keywords():
    d = dict(DEFECT, category="division-by-zero", cwe=None)
    assert rb.category_evidence(_f(message="possible division by zero"), d)
    assert not rb.category_evidence(_f(cwe=[369], message="x"), d)


# --- score ------------------------------------------------------------------

DOC = {"specimen": "py-01-x", "language": "python", "defects": [
    DEFECT,
    {"id": "PY01-D02", "file": "app.py", "function": "export", "line": 90,
     "category": "path-traversal", "cwe": "CWE-22", "class": "vulnerability"},
    {"id": "PY01-D03", "file": "config.py", "function": "ADMIN_TOKEN", "line": 3,
     "category": "hardcoded-secret", "cwe": "CWE-798", "class": "vulnerability"},
]}


def _review(contains, verdict, tool="semgrep", file="app.py", specimen="py-01-x"):
    return {"tool": tool, "specimen": specimen, "file": file, "finding_contains": contains,
            "verdict": verdict, "reason": "because"}


def test_score_statuses_and_precision():
    findings = [
        _f(cwe=[89], rule="sql"),                                     # D01 detected
        _f(function="export", line=91, rule="tls", message="Use TLS"),  # D02 flagged only
        _f(file="config.py", function=None, line=3, cwe=[259], rule="pw"),  # D03 detected
        _f(function="main", line=150, rule="noise"),                  # unrelated
    ]
    out = rb.score(DOC, findings, "py-01-x", [_review("noise", "false_positive")])
    assert [d["status"] for d in out["defects"]] == ["detected", "function_flagged", "detected"]
    assert out["counts"] == {"total": 3, "detected": 2, "function_flagged": 1, "missed": 0}
    assert out["finding_counts"] == {"total": 4, "defect_evidence": 2, "real": 0,
                                     "false_positive": 1, "unreviewed": 1}
    assert out["defects"][1]["findings"] == ["tls in `export` (line 91): Use TLS"]


def test_score_no_findings():
    out = rb.score(DOC, [], "py-01-x", [])
    assert out["counts"]["missed"] == 3
    assert out["finding_counts"]["total"] == 0


def test_score_one_finding_can_be_evidence_for_two_defects():
    doc = {"specimen": "s", "defects": [
        dict(DEFECT, id="A"), dict(DEFECT, id="B", line=41)]}
    out = rb.score(doc, [_f(cwe=[89])], "s", [])
    assert out["counts"]["detected"] == 2
    assert out["finding_counts"]["defect_evidence"] == 1


def test_score_real_review_counts_for_precision():
    findings = [_f(function="main", line=150, rule="pickle-import")]
    out = rb.score(DOC, findings, "py-01-x", [_review("pickle-import", "real")])
    assert out["finding_counts"]["real"] == 1
    assert rsa.precision_range(out["finding_counts"]) == (1.0, 1.0)


def test_score_conflicting_reviews_fail():
    findings = [_f(function="main", line=150, rule="noise")]
    with pytest.raises(SystemExit):
        rb.score(DOC, findings, "py-01-x",
                 [_review("noise", "real"), _review("noi", "false_positive")])


def test_score_fixed_counts_false_alarms_and_still_reported():
    findings = [_f(cwe=[89], rule="sql"), _f(function="main", line=150, rule="kept")]
    out = rb.score_fixed(DOC, findings, "py-01-x", [_review("kept", "real")])
    assert out["defects"] == 3
    assert out["still_reported"] == ["PY01-D01"]
    assert out["false_alarms"] == 1
    assert out["finding_counts"]["defect_evidence"] == 0


def test_score_fixed_false_positive_review_still_false_alarm():
    out = rb.score_fixed(DOC, [_f(rule="noise", function="main", line=150)], "py-01-x",
                         [_review("noise", "false_positive")])
    assert out["false_alarms"] == 1


# --- reviews ----------------------------------------------------------------

def _tree(tmp_path, reviews=None):
    root = tmp_path / "specimens"
    d = root / "python" / "py-01-x"
    d.mkdir(parents=True)
    (d / "DEFECTS.json").write_text(json.dumps(DOC))
    (d / "app.py").write_text("def list_expenses():\n    return 1\n")
    if reviews is not None:
        (root / "scoreboard").mkdir()
        (root / "scoreboard" / rb.REVIEWS_FILE).write_text(json.dumps({"finding_reviews": reviews}))
    return root, d


def test_load_reviews_missing_file(tmp_path):
    root, _ = _tree(tmp_path)
    assert rb.load_reviews(root, {"semgrep"}) == []


def test_load_reviews_same_text_for_two_tools(tmp_path):
    root, _ = _tree(tmp_path, [_review("x", "real"), _review("x", "real", tool="bandit")])
    assert len(rb.load_reviews(root, {"semgrep", "bandit"})) == 2


@pytest.mark.parametrize("bad,message", [
    ([_review("x", "real", tool="gosec")], "unknown tool"),
    ([dict(_review("x", "real"), tool="")], "missing or empty 'tool'"),
    ([_review("x", "real"), _review("x", "false_positive")], "duplicate"),
    ([_review("x", "maybe")], "unsupported verdict"),
    ([_review("x", "real", file="nope.py")], "unknown file"),
    ([_review("x", "real", specimen="py-99")], "unknown specimen"),
])
def test_load_reviews_rejects(tmp_path, bad, message):
    root, _ = _tree(tmp_path, bad)
    with pytest.raises(SystemExit, match=message):
        rb.load_reviews(root, {"semgrep", "bandit"})


def test_mumei_reviews_unaffected_by_extra_fields(tmp_path):
    root, _ = _tree(tmp_path)
    (root / "scoreboard").mkdir()
    (root / "scoreboard" / rsa.ADJUDICATIONS_FILE).write_text(json.dumps({"finding_reviews": [
        {"specimen": "py-01-x", "file": "app.py", "finding_contains": "x",
         "verdict": "real", "reason": "r"}]}))
    assert len(rsa.load_finding_reviews(root)) == 1


def test_stale_reviews():
    rec = {"tool": "semgrep", "specimen": "py-01-x",
           "reviews_used": [["py-01-x", "app.py", "used"]], "fixed": {"reviews_used": []}}
    reviews = [_review("used", "real"), _review("unused", "real"),
               _review("unused", "real", tool="bandit"),
               _review("other", "real", specimen="py-02-y")]
    assert [r["finding_contains"] + r["tool"] for r in rb.stale_reviews([rec], reviews)] == ["unusedsemgrep"]


# --- records, rescore, aggregate ---------------------------------------------

def _record(tool="semgrep", fixed=True):
    t = rb.TOOLS[tool]
    findings = [_f(cwe=[89], rule="sql")]
    return rb.build_record(t, DOC, findings, 1, ([_f(rule="kept", function="main", line=150)], 0)
                           if fixed else None, [], "hash", "2026-01-01T00:00:00Z")


def test_build_record_fields():
    rec = _record()
    assert rec["tool"] == "semgrep" and rec["version"] == rb.SEMGREP_VERSION
    assert rec["rules_commit"] == rb.SEMGREP_RULES_COMMIT
    assert rec["rule_categories"] == ["correctness", "security"]
    assert rec["counts"]["detected"] == 1
    assert rec["fixed"]["false_alarms"] == 1
    assert rec["source_hash"] == "hash"
    assert "rules_commit" not in _record("bandit")


def test_build_record_uses_only_own_tool_reviews():
    t = rb.TOOLS["bandit"]
    rec = rb.build_record(t, DOC, [_f(rule="noise", function="main", line=150)], 0, None,
                          [_review("noise", "real")], "h", "now")
    assert rec["finding_counts"]["unreviewed"] == 1
    assert "fixed" not in rec


def _git_tree(tmp_path, monkeypatch, with_fixed=False):
    root, d = _tree(tmp_path)
    if with_fixed:
        (d / rsa.FIXED_PATCH).write_text("")
    monkeypatch.setattr(rsa, "REPO_ROOT", tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    return root, d


def test_rescore_record_roundtrip(tmp_path, monkeypatch):
    _, d = _git_tree(tmp_path, monkeypatch)
    rec = rb.build_record(rb.TOOLS["semgrep"], DOC, [_f(rule="noise", function="main", line=150)], 2,
                          None, [], rb.baseline_hash(d), "then")
    rb.write_json(d / "baselines" / "semgrep.json", rec)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    out = rb.rescore_record(d, rb.TOOLS["semgrep"], [_review("noise", "false_positive")])
    assert out["finding_counts"]["false_positive"] == 1
    assert out["generated_at"] == "then" and out["tool_errors"] == 2


@pytest.mark.parametrize("field,value", [
    ("version", "0.0.1"), ("rules_commit", "0" * 40), ("rule_categories", ["security"]),
    ("tool", "bandit"),
])
def test_rescore_record_refuses_other_pins(tmp_path, monkeypatch, field, value):
    _, d = _git_tree(tmp_path, monkeypatch)
    rec = rb.build_record(rb.TOOLS["semgrep"], DOC, [], 0, None, [], rb.baseline_hash(d), "then")
    rec[field] = value
    rb.write_json(d / "baselines" / "semgrep.json", rec)
    with pytest.raises(SystemExit, match="current pins"):
        rb.rescore_record(d, rb.TOOLS["semgrep"], [])


def test_rescore_record_refuses_missing_pin(tmp_path, monkeypatch):
    _, d = _git_tree(tmp_path, monkeypatch)
    rec = rb.build_record(rb.TOOLS["bandit"], DOC, [], 0, None, [], rb.baseline_hash(d), "then")
    del rec["version"]
    rb.write_json(d / "baselines" / "bandit.json", rec)
    with pytest.raises(SystemExit, match="current pins"):
        rb.rescore_record(d, rb.TOOLS["bandit"], [])


def test_baseline_outputs_do_not_change_hashes(tmp_path, monkeypatch):
    _, d = _git_tree(tmp_path, monkeypatch)
    before = rsa.specimen_hash(d)
    rb.write_json(d / "baselines" / "semgrep.json", {"x": 1})
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    assert rsa.specimen_hash(d) == before
    assert all("baselines" not in f.parts for f in rsa.audit_files(d))


def test_rescore_record_refuses_changed_source(tmp_path, monkeypatch):
    _, d = _git_tree(tmp_path, monkeypatch)
    rec = rb.build_record(rb.TOOLS["semgrep"], DOC, [], 0, None, [], rb.baseline_hash(d), "then")
    rb.write_json(d / "baselines" / "semgrep.json", rec)
    (d / "app.py").write_text("def list_expenses():\n    return 2\n")
    with pytest.raises(SystemExit, match="changed since"):
        rb.rescore_record(d, rb.TOOLS["semgrep"], [])


def test_rescore_record_missing_file(tmp_path, monkeypatch):
    _, d = _git_tree(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="missing"):
        rb.rescore_record(d, rb.TOOLS["bandit"], [])


def test_rescore_record_needs_fixed_findings(tmp_path, monkeypatch):
    _, d = _git_tree(tmp_path, monkeypatch, with_fixed=True)
    rec = rb.build_record(rb.TOOLS["semgrep"], DOC, [], 0, None, [], rb.baseline_hash(d), "then")
    rb.write_json(d / "baselines" / "semgrep.json", rec)
    with pytest.raises(SystemExit, match="fixed-variant"):
        rb.rescore_record(d, rb.TOOLS["semgrep"], [])


def test_aggregate_and_render():
    recs = [_record(), _record(), _record("bandit", fixed=False)]
    summary = rb.aggregate(recs)
    tools = {t["tool"]: t for t in summary["tools"]}
    assert list(tools) == ["bandit", "semgrep"]
    s = tools["semgrep"]
    assert s["specimens"] == 2 and s["languages"] == ["python"]
    assert s["counts"]["detected"] == 2 and s["counts"]["total"] == 6
    assert s["fixed"] == {"specimens": 2, "defects": 6, "still_reported": 0, "findings": 2,
                          "real": 0, "false_alarms": 2}
    assert s["tool_errors"] == 2
    assert tools["bandit"]["fixed"]["specimens"] == 0
    md = rb.render_summary(summary, [])
    assert "| semgrep | 1.150.0 | python | 2 | 2/6 (33%) |" in md
    assert "semgrep-rules `16b9e6d45f10`" in md
    assert "2 parse or scan errors" in md
    assert "matched no finding" not in md
    assert "matched no finding" in rb.render_summary(summary, [_review("x", "real")])


def test_aggregate_empty():
    assert rb.aggregate([]) == {"tools": []}


# --- tool wiring and CLI ------------------------------------------------------

def test_semgrep_command_uses_language_configs(tmp_path):
    t = rb.TOOLS["semgrep"]
    cmd = rb._semgrep_cmd(t, tmp_path, "typescript")
    assert cmd[cmd.index("--config") + 1] == "typescript"
    assert cmd.count("--config") == 2 and "--metrics=off" in cmd
    assert cmd[-1] == str(tmp_path)


def test_every_language_has_semgrep_configs():
    assert set(rb.SEMGREP_CONFIGS) == {"python", "typescript", "go", "rust", "solidity"}
    assert rb.TOOLS["bandit"].languages == {"python"}


def test_tool_run_rejects_bad_exit_and_non_json(tmp_path, monkeypatch):
    t = rb.Tool("fake", {"python"}, "1", lambda tool, s, l: ["fake"], rb.parse_bandit)

    class P:
        def __init__(self, rc, out):
            self.returncode, self.stdout, self.stderr = rc, out, "boom"
    monkeypatch.setattr(rb.subprocess, "run", lambda *a, **k: P(2, "{}"))
    with pytest.raises(SystemExit, match="exit 2"):
        t.run(tmp_path, "python", 5)
    monkeypatch.setattr(rb.subprocess, "run", lambda *a, **k: P(1, "not json"))
    with pytest.raises(SystemExit, match="did not return JSON"):
        t.run(tmp_path, "python", 5)
    monkeypatch.setattr(rb.subprocess, "run", lambda *a, **k: P(1, json.dumps({"results": []})))
    assert t.run(tmp_path, "python", 5) == ([], 0)


def test_check_rules_dir(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="no semgrep-rules checkout"):
        rb.check_rules_dir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(rsa, "git_rev", lambda p: "0" * 40)
    with pytest.raises(SystemExit, match="expected"):
        rb.check_rules_dir(tmp_path)
    monkeypatch.setattr(rsa, "git_rev", lambda p: rb.SEMGREP_RULES_COMMIT)

    class P:
        def __init__(self, rc, out):
            self.returncode, self.stdout = rc, out
    monkeypatch.setattr(rb.subprocess, "run", lambda *a, **k: P(0, ""))
    rb.check_rules_dir(tmp_path)
    for proc in (P(0, " M python/lang/security/rule.yaml\n"), P(0, "?? extra.yaml\n"), P(128, "")):
        monkeypatch.setattr(rb.subprocess, "run", lambda *a, _p=proc, **k: _p)
        with pytest.raises(SystemExit, match="local changes"):
            rb.check_rules_dir(tmp_path)


def test_find_binary_override_and_missing(monkeypatch, tmp_path):
    assert rb.find_binary("semgrep", "/opt/semgrep") == "/opt/semgrep"
    monkeypatch.setattr(rb, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(rb.shutil, "which", lambda n: None)
    with pytest.raises(SystemExit, match="setup_baselines.sh"):
        rb.find_binary("semgrep", None)


@pytest.mark.parametrize("tools", ["cppcheck", "semgrep,nope", ","])
def test_main_rejects_unknown_tools(tools):
    with pytest.raises(SystemExit, match="unknown tool"):
        rb.main(["--tools", tools])


def test_main_refuses_version_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(rb, "load_reviews", lambda root, tools: [])
    monkeypatch.setattr(rb, "find_binary", lambda name, override, *rest: "/bin/" + name)
    monkeypatch.setattr(rb, "installed_version", lambda b: "0.0.1")
    with pytest.raises(SystemExit, match="pinned"):
        rb.main(["--tools", "bandit"])


def test_main_runs_tools_and_writes_outputs(monkeypatch, tmp_path):
    root, d = _tree(tmp_path)
    monkeypatch.setattr(rb, "SPECIMENS_ROOT", root)
    monkeypatch.setattr(rb, "find_binary", lambda name, override, *rest: "/bin/" + name)
    monkeypatch.setattr(rb, "installed_version", lambda b: rb.BANDIT_VERSION)
    monkeypatch.setattr(rb, "run_specimen", lambda d, tool, reviews, timeout, at: rb.build_record(
        tool, DOC, [_f(cwe=[89])], 0, None, reviews, "h", at))
    summary = tmp_path / "BASELINES.md"
    assert rb.main(["--tools", "bandit", "--summary", str(summary),
                    "--scoreboard-dir", str(root / "scoreboard")]) == 0
    rec = json.loads((d / "baselines" / "bandit.json").read_text())
    assert rec["counts"]["detected"] == 1
    agg = json.loads((root / "scoreboard" / "baselines.json").read_text())
    assert agg["tools"][0]["tool"] == "bandit"
    assert "| bandit |" in summary.read_text()


def test_main_skips_languages_a_tool_does_not_cover(monkeypatch, tmp_path):
    root, d = _tree(tmp_path)
    doc = json.loads((d / "DEFECTS.json").read_text())
    doc["language"] = "go"
    (d / "DEFECTS.json").write_text(json.dumps(doc))
    monkeypatch.setattr(rb, "SPECIMENS_ROOT", root)
    monkeypatch.setattr(rb, "find_binary", lambda name, override, *rest: "/bin/" + name)
    monkeypatch.setattr(rb, "installed_version", lambda b: rb.BANDIT_VERSION)
    calls = []
    monkeypatch.setattr(rb, "run_specimen", lambda *a: calls.append(a))
    rb.main(["--tools", "bandit", "--summary", str(tmp_path / "s.md"),
             "--scoreboard-dir", str(tmp_path / "sb")])
    assert calls == []
    assert json.loads((tmp_path / "sb" / "baselines.json").read_text()) == {"tools": []}


# --- committed outputs ----------------------------------------------------------

def test_committed_baseline_records_match_summary():
    summary_path = REPO_ROOT / "specimens" / "scoreboard" / "baselines.json"
    if not summary_path.is_file():
        pytest.skip("no committed baseline run")
    records = [json.loads(p.read_text()) for p in sorted(REPO_ROOT.glob("specimens/*/*/baselines/*.json"))]
    assert rb.aggregate(records) == json.loads(summary_path.read_text())
    for rec in records:
        for f in rec["raw_findings"] + rec.get("fixed_raw_findings", []):
            assert not Path(f["file"]).is_absolute(), f


# --- gosec / slither / clippy adapters ---------------------------------------

def _gosec_issue(file, line, rule="G401", cwe="328", details="Use of weak cryptographic primitive"):
    return {"rule_id": rule, "cwe": {"id": cwe, "url": "x"}, "file": file, "line": line,
            "severity": "MEDIUM", "confidence": "HIGH", "details": details}


def test_parse_gosec(tmp_path):
    doc = {"Issues": [_gosec_issue(str(tmp_path / "auth.go"), "27"),
                      _gosec_issue("handlers.go", "68-70", "G704", "918", "SSRF via\n taint analysis")],
           "Golang errors": {}}
    findings, errors = rb.parse_gosec(doc, tmp_path)
    assert errors == 0
    assert findings[0] == {"file": "auth.go", "line": 27, "rule": "G401", "severity": "medium",
                           "cwe": [328], "message": "Use of weak cryptographic primitive"}
    assert findings[1]["line"] == 68 and findings[1]["cwe"] == [918]
    assert findings[1]["message"] == "SSRF via taint analysis"


@pytest.mark.parametrize("golang_errors,expected", [
    ({}, 0), (None, 0), ({"a.go": [{"line": 1}, {"line": 2}]}, 2),
    ({"a.go": [{"line": 1}], "b.go": [{"line": 3}]}, 2), ({"a.go": "boom"}, 1),
])
def test_parse_gosec_counts_golang_errors(golang_errors, expected):
    assert rb.parse_gosec({"Issues": [], "Golang errors": golang_errors}, Path("/x")) == ([], expected)


def test_parse_gosec_empty():
    assert rb.parse_gosec({}, Path("/x")) == ([], 0)


def _slither_result(check, impact, lines=(10,), file="src/A.sol", elements=None, description="desc"):
    if elements is None:
        elements = [{"type": "function", "name": "f",
                     "source_mapping": {"filename_relative": file, "lines": list(lines)}}]
    return {"check": check, "impact": impact, "confidence": "Medium", "elements": elements,
            "description": description}


def test_parse_slither_keeps_bug_impacts_only(tmp_path):
    doc = {"success": True, "error": None, "results": {"detectors": [
        _slither_result("reentrancy-eth", "High", (98, 99)),
        _slither_result("divide-before-multiply", "Medium", (58,)),
        _slither_result("timestamp", "Low", (66,)),
        _slither_result("solc-version", "Informational", (2,)),
        _slither_result("immutable-states", "Optimization", (5,)),
    ]}}
    findings, errors = rb.parse_slither(doc, tmp_path)
    assert errors == 0
    assert [(f["rule"], f["line"], f["severity"]) for f in findings] == [
        ("reentrancy-eth", 98, "high"), ("divide-before-multiply", 58, "medium"), ("timestamp", 66, "low")]
    assert [f["cwe"] for f in findings] == [[841], [682], [829]]
    assert all(f["cwe_only"] for f in findings)
    assert findings[0]["file"] == "src/A.sol"


def test_parse_slither_failed_compile_is_one_error():
    assert rb.parse_slither({"success": False, "error": "solc failed", "results": {}}, Path("/x")) == ([], 1)
    assert rb.parse_slither({}, Path("/x")) == ([], 1)


def test_parse_slither_uses_first_element_with_lines(tmp_path):
    elements = [{"type": "pragma", "name": "x", "source_mapping": {"lines": []}},
                {"type": "function", "name": "bid",
                 "source_mapping": {"filename_absolute": str(tmp_path / "src" / "B.sol"), "lines": [66, 67]}}]
    doc = {"success": True, "results": {"detectors": [
        _slither_result("reentrancy-benign", "Low", elements=elements, description="Reentrancy in\n  bid()"),
        _slither_result("tx-origin", "Medium", elements=[{"type": "x"}]),
        _slither_result("weak-prng", "High", elements=[]),
    ]}}
    findings, _ = rb.parse_slither(doc, tmp_path)
    assert len(findings) == 1
    assert findings[0]["file"] == "src/B.sol" and findings[0]["line"] == 66
    assert findings[0]["message"] == "Reentrancy in bid()"


@pytest.mark.parametrize("check,cwes", [
    ("reentrancy-eth", [841]), ("reentrancy-no-eth", [841]), ("reentrancy-events", [841]),
    ("tx-origin", [346]), ("unchecked-lowlevel", [252]), ("unchecked-send", [252]),
    ("unchecked-transfer", [252]), ("weak-prng", [330]), ("timestamp", [829]),
    ("divide-before-multiply", [682]), ("arbitrary-send-eth", [284]), ("suicidal", [284]),
    ("calls-loop", [400]), ("missing-zero-check", []), ("shadowing-local", []),
])
def test_slither_cwes(check, cwes):
    assert rb.slither_cwes(check) == cwes


def test_slither_reentrancy_matches_a_reentrancy_defect():
    f = {"file": "src/A.sol", "line": 94, "function": "withdraw", "rule": "reentrancy-eth",
         "cwe": rb.slither_cwes("reentrancy-eth"), "message": "Reentrancy in A.withdraw()"}
    d = {"file": "src/A.sol", "line": 94, "function": "withdraw", "category": "reentrancy", "cwe": "CWE-841"}
    assert rb.located(f, d) and rb.category_evidence(f, d)


def _clippy_msg(code, level="warning", file="src/main.rs", line=7, primary=True, message="m"):
    return {"reason": "compiler-message", "message": {
        "code": {"code": code} if code else None, "level": level, "message": message,
        "spans": [{"file_name": "src/other.rs", "line_start": 1, "is_primary": False},
                  {"file_name": file, "line_start": line, "is_primary": primary}]}}


def test_parse_clippy(tmp_path):
    msgs = [
        {"reason": "compiler-artifact"},
        _clippy_msg("clippy::absurd_extreme_comparisons", message="this comparison\n is always false"),
        _clippy_msg("unused_variables"),
        _clippy_msg(None, level="error"),
        _clippy_msg("E0308", level="error"),
        _clippy_msg("clippy::suspicious_arithmetic_impl", primary=False),
        {"reason": "build-finished", "success": True},
    ]
    findings, errors = rb.parse_clippy(msgs, tmp_path)
    assert errors == 2
    assert findings == [{"file": "src/main.rs", "line": 7, "rule": "clippy::absurd_extreme_comparisons",
                         "severity": "warning", "cwe": [], "message": "this comparison is always false"}]


def test_parse_clippy_empty():
    assert rb.parse_clippy([], Path("/x")) == ([], 0)


def test_load_json_lines():
    text = 'Compiling x\n{"reason": "a"}\n\n{"reason": "b"}\n'
    assert rb.load_json_lines(text) == [{"reason": "a"}, {"reason": "b"}]
    assert rb.load_json_lines("") == []
    with pytest.raises(json.JSONDecodeError):
        rb.load_json_lines("{broken")


def test_new_tool_commands(tmp_path):
    g = rb.TOOLS["gosec"]
    assert rb._gosec_cmd(g, tmp_path, "go")[-1] == "./..." and "-fmt=json" in rb._gosec_cmd(g, tmp_path, "go")
    s = rb.TOOLS["slither"]
    s.solc = "/opt/solc"
    cmd = rb._slither_cmd(s, tmp_path, "solidity")
    assert cmd[1] == "src" and cmd[cmd.index("--solc") + 1] == "/opt/solc"
    assert cmd[cmd.index("--json") + 1] == "-"
    s.solc = None
    c = rb.TOOLS["clippy"]
    cmd = rb._clippy_cmd(c, tmp_path, "rust")
    assert cmd[1] == f"+{rb.RUST_TOOLCHAIN}" and cmd[2] == "clippy"
    tail = cmd[cmd.index("--") + 1:]
    assert tail == ["-A", "clippy::all", "-W", "clippy::correctness", "-W", "clippy::suspicious"]


def test_tool_languages_and_meta():
    assert rb.TOOLS["gosec"].languages == {"go"}
    assert rb.TOOLS["slither"].languages == {"solidity"}
    assert rb.TOOLS["clippy"].languages == {"rust"}
    assert rb.TOOLS["slither"].meta() == {"tool": "slither", "version": rb.SLITHER_VERSION,
                                          "solc_version": rb.SOLC_VERSION, "impacts": ["High", "Low", "Medium"]}
    assert rb.TOOLS["clippy"].meta() == {"tool": "clippy", "version": rb.RUST_TOOLCHAIN,
                                         "lint_groups": ["correctness", "suspicious"]}
    assert rb.TOOLS["gosec"].meta() == {"tool": "gosec", "version": rb.GOSEC_VERSION}
    assert rb.TOOLS["semgrep"].meta()["rules_commit"] == rb.SEMGREP_RULES_COMMIT
    assert rb.TOOLS["clippy"].exe == "cargo"
    assert rb.TOOLS["gosec"].cached() == rb.CACHE_DIR / "gobin" / "gosec"
    assert rb.TOOLS["slither"].cached() == rb.CACHE_DIR / "venv" / "bin" / "slither"


def test_default_tools_cover_every_language():
    covered = set().union(*(t.languages for t in rb.TOOLS.values()))
    assert covered == set(rb.SEMGREP_CONFIGS)
    assert list(rb.TOOLS) == ["semgrep", "bandit", "gosec", "slither", "clippy"]


@pytest.mark.parametrize("name", ["gosec", "slither", "clippy"])
def test_tool_run_uses_scratch_as_cwd(tmp_path, monkeypatch, name):
    seen = {}

    class P:
        returncode, stderr = 0, ""
        stdout = "" if name == "clippy" else json.dumps({"success": True, "results": {}})

    def fake_run(cmd, cwd=None, **kw):
        seen["cwd"] = cwd
        return P()
    monkeypatch.setattr(rb.subprocess, "run", fake_run)
    rb.TOOLS[name].run(tmp_path, next(iter(rb.TOOLS[name].languages)), 5)
    assert seen["cwd"] == tmp_path


@pytest.mark.parametrize("name,code,ok", [
    ("slither", 255, True), ("slither", 0, True), ("slither", 2, False),
    ("clippy", 101, True), ("clippy", 1, False), ("gosec", 1, True), ("gosec", 2, False),
])
def test_new_tools_exit_codes(tmp_path, monkeypatch, name, code, ok):
    class P:
        returncode, stderr = code, "err"
        stdout = "" if name == "clippy" else json.dumps({"success": True, "Issues": []})
    monkeypatch.setattr(rb.subprocess, "run", lambda *a, **k: P())
    tool = rb.TOOLS[name]
    lang = next(iter(tool.languages))
    if ok:
        tool.run(tmp_path, lang, 5)
    else:
        with pytest.raises(SystemExit, match=f"exit {code}"):
            tool.run(tmp_path, lang, 5)


class _Proc:
    def __init__(self, out, rc=0):
        self.stdout, self.returncode, self.stderr = out, rc, ""


@pytest.mark.parametrize("out,expected", [
    ("gosec: go1.27.1\n\tpath\tgithub.com/securego/gosec/v2/cmd/gosec\n"
     "\tmod\tgithub.com/securego/gosec/v2\tv2.29.0\th1:abc=\n", "2.29.0"),
    ("gosec: go1.27.1\n\tmod\tgithub.com/other/thing\tv1.0.0\n", ""),
    ("", ""),
])
def test_gosec_version(monkeypatch, out, expected):
    monkeypatch.setattr(rb.subprocess, "run", lambda *a, **k: _Proc(out))
    t = rb.Tool("gosec", {"go"}, "x", rb._gosec_cmd, rb.parse_gosec)
    t.binary = "/bin/gosec"
    assert rb.gosec_version(t) == expected


def test_gosec_version_needs_go(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("go")
    monkeypatch.setattr(rb.subprocess, "run", boom)
    t = rb.Tool("gosec", {"go"}, "x", rb._gosec_cmd, rb.parse_gosec)
    t.binary = "/bin/gosec"
    with pytest.raises(SystemExit, match="go` on PATH"):
        rb.gosec_version(t)


@pytest.mark.parametrize("out,rc,expected_pinned", [
    (f"clippy 0.1.{rb.RUST_TOOLCHAIN.split('.')[1]} (abc 2026-10-13)\n", 0, True),
    (f"clippy 0.1.{rb.RUST_TOOLCHAIN.split('.')[1]}0 (abc)\n", 0, False),
    ("clippy 0.1.1 (abc)\n", 0, False),
    ("", 1, False),
])
def test_clippy_version(monkeypatch, out, rc, expected_pinned):
    monkeypatch.setattr(rb.subprocess, "run", lambda *a, **k: _Proc(out, rc))
    t = rb.Tool("clippy", {"rust"}, "x", rb._clippy_cmd, rb.parse_clippy)
    t.binary = "/bin/cargo"
    assert rb.clippy_version(t) == (rb.RUST_TOOLCHAIN if expected_pinned else "")


def test_find_solc(monkeypatch, tmp_path):
    monkeypatch.setattr(rb.subprocess, "run",
                        lambda *a, **k: _Proc(f"solc, the solidity compiler\nVersion: {rb.SOLC_VERSION}+commit.x\n"))
    assert rb.find_solc("/opt/solc") == "/opt/solc"
    monkeypatch.setattr(rb, "CACHE_DIR", tmp_path)
    assert rb.find_solc(None).endswith(f"solc-{rb.SOLC_VERSION}/solc-{rb.SOLC_VERSION}")
    monkeypatch.setattr(rb.subprocess, "run", lambda *a, **k: _Proc("Version: 0.8.19+commit.x\n"))
    with pytest.raises(SystemExit, match="is not solc"):
        rb.find_solc("/opt/solc")

    def boom(*a, **k):
        raise FileNotFoundError("solc")
    monkeypatch.setattr(rb.subprocess, "run", boom)
    with pytest.raises(SystemExit, match="solc not found"):
        rb.find_solc(None)


def test_find_binary_uses_cached_path_and_exe(monkeypatch, tmp_path):
    cached = tmp_path / "gobin" / "gosec"
    cached.parent.mkdir()
    cached.write_text("")
    assert rb.find_binary("gosec", None, "gosec", cached) == str(cached)
    monkeypatch.setattr(rb.shutil, "which", lambda n: f"/usr/bin/{n}")
    assert rb.find_binary("clippy", None, "cargo", tmp_path / "missing") == "/usr/bin/cargo"
    monkeypatch.setattr(rb.shutil, "which", lambda n: None)
    with pytest.raises(SystemExit, match="--clippy-bin"):
        rb.find_binary("clippy", None, "cargo", tmp_path / "missing")


def test_main_sets_solc_for_slither(monkeypatch, tmp_path):
    root, _ = _tree(tmp_path)
    monkeypatch.setattr(rb, "SPECIMENS_ROOT", root)
    monkeypatch.setattr(rb, "find_binary", lambda name, override, *rest: "/bin/" + name)
    monkeypatch.setattr(rb.TOOLS["slither"], "version_of", lambda t: rb.SLITHER_VERSION)
    monkeypatch.setattr(rb, "find_solc", lambda override: override or "/cache/solc")
    rb.main(["--tools", "slither", "--solc-bin", "/opt/solc", "--summary", str(tmp_path / "s.md"),
             "--scoreboard-dir", str(tmp_path / "sb")])
    assert rb.TOOLS["slither"].solc == "/opt/solc"
    rb.TOOLS["slither"].solc = None


@pytest.mark.parametrize("name", ["gosec", "slither", "clippy"])
def test_main_refuses_new_tool_version_mismatch(monkeypatch, name):
    monkeypatch.setattr(rb, "load_reviews", lambda root, tools: [])
    monkeypatch.setattr(rb, "find_binary", lambda n, override, *rest: "/bin/" + n)
    monkeypatch.setattr(rb.TOOLS[name], "version_of", lambda t: "")
    with pytest.raises(SystemExit, match="pinned"):
        rb.main(["--tools", name])


def test_render_summary_tool_settings():
    recs = [_record("semgrep", fixed=False)]
    for name in ("slither", "clippy"):
        rec = rb.build_record(rb.TOOLS[name], DOC, [], 0, None, [], "h", "now")
        recs.append(rec)
    md = rb.render_summary(rb.aggregate(recs), [])
    assert f"slither settings: solc {rb.SOLC_VERSION}, impacts High, Low, Medium." in md
    assert f"clippy settings: Rust {rb.RUST_TOOLCHAIN}, lint groups correctness, suspicious." in md
    agg = {t["tool"]: t for t in rb.aggregate(recs)["tools"]}
    assert agg["slither"]["solc_version"] == rb.SOLC_VERSION and "lint_groups" not in agg["slither"]


def test_cwe_only_findings_ignore_keywords():
    d = {"file": "src/A.sol", "line": 77, "function": "rewardPerToken", "category": "division-by-zero",
         "cwe": "CWE-369"}
    f = {"file": "src/A.sol", "line": 72, "function": "rewardPerToken", "rule": "divide-before-multiply",
         "cwe": [682], "message": "performs a multiplication on the result of a division", "cwe_only": True}
    assert not rb.category_evidence(f, d)
    assert rb.category_evidence(dict(f, cwe_only=False), d)
    assert rb.category_evidence(dict(f, cwe=[369]), d)


@pytest.mark.parametrize("a,b,related", [
    (252, 703, True), (703, 754, True), (252, 754, True), (276, 732, True),
    (252, 276, False), (703, 732, False), (190, 191, False),
])
def test_cwe_equivalents_for_gosec(a, b, related):
    assert rb.cwe_related(a, b) is related


def test_main_partial_run_keeps_other_tools_in_summary(monkeypatch, tmp_path):
    root, _ = _tree(tmp_path)
    monkeypatch.setattr(rb, "SPECIMENS_ROOT", root)
    monkeypatch.setattr(rb, "find_binary", lambda name, override, *rest: "/bin/" + name)
    monkeypatch.setattr(rb, "installed_version", lambda b: rb.BANDIT_VERSION)
    monkeypatch.setattr(rb, "check_rules_dir", lambda d: None)
    other = root / "python" / "py-01-x" / "baselines" / "semgrep.json"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text(json.dumps(_record("semgrep", fixed=False)))
    monkeypatch.setattr(rb, "run_specimen", lambda d, tool, reviews, timeout, at: rb.build_record(
        tool, DOC, [], 0, None, reviews, "h", at))
    sb = tmp_path / "sb"
    rb.main(["--tools", "bandit", "--summary", str(tmp_path / "s.md"), "--scoreboard-dir", str(sb)])
    tools = [t["tool"] for t in json.loads((sb / "baselines.json").read_text())["tools"]]
    assert tools == ["bandit", "semgrep"]
    assert "| semgrep |" in (tmp_path / "s.md").read_text()


def test_committed_records(tmp_path):
    assert rb.committed_records(tmp_path) == []
    p = tmp_path / "go" / "g" / "baselines" / "gosec.json"
    p.parent.mkdir(parents=True)
    p.write_text('{"tool": "gosec"}')
    (tmp_path / "go" / "g" / "baselines" / "notes.txt").write_text("x")
    assert rb.committed_records(tmp_path) == [{"tool": "gosec"}]



def _cov(specimen="py-01-x", language="python", detected=(), total=2, llm=False, h="h",
         fixed_fa=1, findings=None):
    ids = [f"D{i}" for i in range(1, total + 1)]
    return {"specimen": specimen, "language": language, "source_hash": h,
            "meta": {"llm_configured": llm},
            "counts": {"total": total, "detected": len(detected)},
            "defects": [{"id": i, "status": "detected" if i in detected else "missed"} for i in ids],
            "finding_counts": findings or {"total": 2, "defect_evidence": 1, "real": 0,
                                           "false_positive": 1, "unreviewed": 0},
            "fixed": {"false_alarms": fixed_fa}}


def _brec(tool="semgrep", **kw):
    return dict(_cov(**kw), tool=tool)


def test_comparison_complement_and_totals():
    comp = rb.comparison(
        [_cov(detected=("D1", "D2"), total=3), _cov("go-01-x", "go", detected=(), total=2)],
        [_brec(detected=("D2", "D3"), total=3), _brec("bandit", detected=("D3",), total=3),
         _brec("gosec", specimen="go-01-x", language="go", detected=("D1",), total=2)])
    assert [r["language"] for r in comp["languages"]] == ["go", "python"]
    py = comp["languages"][1]
    assert py["complement"] == {"mumei_only": 1, "baselines_only": 1, "both": 1, "neither": 0}
    assert list(py["tools"]) == ["bandit", "semgrep"]
    t = comp["total"]
    assert t["defects"] == 5
    assert t["complement"] == {"mumei_only": 1, "baselines_only": 2, "both": 1, "neither": 1}
    assert t["mumei"]["counts"] == {"total": 5, "detected": 2}
    assert t["mumei"]["fixed"] == {"specimens": 2, "false_alarms": 2}
    assert t["tools"]["semgrep"]["counts"] == {"total": 3, "detected": 2}
    assert comp["stale_specimens"] == []
    assert comp["mumei"] == "Mumei (no LLM)"


def test_comparison_same_defect_id_in_two_specimens_is_not_merged():
    comp = rb.comparison([_cov("a", detected=("D1",), total=1), _cov("b", total=1)],
                         [_brec(specimen="b", detected=("D1",), total=1)])
    assert comp["total"]["complement"] == {"mumei_only": 1, "baselines_only": 1, "both": 0,
                                           "neither": 0}


def test_comparison_ignores_records_outside_the_audited_corpus():
    comp = rb.comparison([_cov()], [_brec("gosec", specimen="go-01-x", language="go"),
                                    _brec(specimen="py-99-other")])
    assert comp["total"]["tools"] == {}
    assert [r["language"] for r in comp["languages"]] == ["python"]


def test_comparison_flags_specimens_with_different_sources():
    comp = rb.comparison([_cov(h="a")], [_brec(h="b"), _brec("bandit", h="a")])
    assert comp["stale_specimens"] == ["py-01-x"]
    assert "different specimen sources for py-01-x" in rb.readme_block(comp)
    assert "different specimen sources" in "\n".join(rb.render_comparison(comp))


@pytest.mark.parametrize("modes,label", [
    ([False], "Mumei (no LLM)"), ([True, True], "Mumei (with LLM)"),
    ([False, True], "Mumei (mixed LLM runs)")])
def test_mumei_label(modes, label):
    assert rb.mumei_label([_cov(llm=m) for m in modes]) == label


def test_comparison_empty():
    comp = rb.comparison([], [_brec()])
    assert comp["languages"] == [] and comp["total"]["defects"] == 0
    assert "compared with the baselines" not in rb.render_summary(rb.aggregate([]), [], comp)


def test_render_comparison_rows():
    comp = rb.comparison([_cov(detected=("D1",))], [_brec(detected=("D2",))])
    text = "\n".join(rb.render_comparison(comp))
    assert "| python | Mumei (no LLM) | 1/2 (50%) | 50% | 1 / 1 specimens |" in text
    assert "| python | semgrep | 1/2 (50%) | 50% | 1 / 1 specimens |" in text
    assert "| python | 2 | 1 | 1 | 0 | 0 |" in text
    assert "| **Total** | 2 | 1 | 1 | 0 | 0 |" in text


def test_readme_block_totals():
    comp = rb.comparison([_cov(detected=("D1",))], [_brec(detected=("D1",))])
    block = rb.readme_block(comp)
    assert "| Mumei (no LLM) | 1/2 (50%) | 50% | 1 / 1 specimens |" in block
    assert "| semgrep | 1/2 (50%)" in block
    assert "Of 2 defects, 0 are detected only by Mumei (no LLM), 0 only by a baseline, 1 by both " \
           "and 1 by neither." in block


def test_update_readme_block(tmp_path):
    p = tmp_path / "README.md"
    rb.update_readme_block(p, "x")
    assert not p.exists()
    p.write_text(f"a\n{rb.BASELINES_START}\nold\n{rb.BASELINES_END}\nb\n")
    rb.update_readme_block(p, "new\n")
    assert p.read_text() == f"a\n{rb.BASELINES_START}\nnew\n{rb.BASELINES_END}\nb\n"
    p.write_text("no markers")
    with pytest.raises(SystemExit, match="missing"):
        rb.update_readme_block(p, "x")


def test_main_writes_comparison_and_readme(monkeypatch, tmp_path):
    root, d = _tree(tmp_path)
    (d / "audit").mkdir()
    (d / "audit" / "coverage.json").write_text(json.dumps(
        _cov(specimen="py-01-x", detected=("D1",), total=len(DOC["defects"]))))
    readme = tmp_path / "R.md"
    readme.write_text(f"{rb.BASELINES_START}\n{rb.BASELINES_END}\n")
    monkeypatch.setattr(rb, "SPECIMENS_ROOT", root)
    monkeypatch.setattr(rb, "find_binary", lambda name, override, *rest: "/bin/" + name)
    monkeypatch.setattr(rb, "installed_version", lambda b: rb.BANDIT_VERSION)
    monkeypatch.setattr(rb, "run_specimen", lambda d, tool, reviews, timeout, at: rb.build_record(
        tool, DOC, [], 0, None, reviews, "h", at))
    sb = tmp_path / "sb"
    rb.main(["--tools", "bandit", "--summary", str(tmp_path / "s.md"), "--scoreboard-dir", str(sb),
             "--specimens-readme", str(readme)])
    comp = json.loads((sb / "comparison.json").read_text())
    assert comp["total"]["complement"]["mumei_only"] == 1
    assert "| bandit |" in readme.read_text()
    assert "### Complementarity" in (tmp_path / "s.md").read_text()


def test_committed_comparison_matches_records():
    root = rb.SPECIMENS_ROOT
    comp = rb.comparison(rb.mumei_coverages(root), rb.committed_records(root))
    assert json.loads((root / "scoreboard" / "comparison.json").read_text()) == comp
    assert comp["stale_specimens"] == []
    readme = (root / "README.md").read_text()
    assert rb.readme_block(comp) in readme
