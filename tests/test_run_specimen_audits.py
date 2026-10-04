"""Unit tests for the pure functions in scripts/run_specimen_audits.py.

No subprocess or real audit calls: the module is imported by path and fed
hand-built defects docs / audit dicts.
"""

import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "run_specimen_audits.py"

spec = importlib.util.spec_from_file_location("run_specimen_audits", SCRIPT)
rsa = importlib.util.module_from_spec(spec)
sys.modules["run_specimen_audits"] = rsa
spec.loader.exec_module(rsa)


# --- names_function -------------------------------------------------------

def test_names_function_backticked():
    assert rsa.names_function("Python function `transfer` can be called twice", "transfer")


def test_names_function_word_boundaries():
    assert not rsa.names_function("transfer_all moves everything", "transfer")
    assert not rsa.names_function("do_transfer moves money", "transfer")


def test_names_function_qualified_names():
    assert rsa.names_function("withdraw lacks a balance check", "Vault.withdraw")
    assert rsa.names_function("apply_fee ignores zero", "bank::apply_fee")


# --- category_hit ----------------------------------------------------------

def test_category_hit_overflow():
    assert rsa.category_hit("possible arithmetic overflow in add", "integer-overflow")
    assert not rsa.category_hit("reentrant call", "integer-overflow")


def test_category_hit_logic_error_never_hits():
    assert not rsa.category_hit("overflow bounds index inject", "logic-error")


def test_category_hit_denial_of_service_not_todos():
    assert not rsa.category_hit("several todos left in the queue", "denial-of-service")
    assert rsa.category_hit("unbounded loop leads to denial of service",
                            "denial-of-service")


# --- rewrite_paths ---------------------------------------------------------

def test_rewrite_paths_nested():
    obj = {
        "source_file": "/tmp/x/py-01/app.py",
        "items": ["/tmp/x/py-01/a", {"deep": ["/tmp/x/py-01/b", 3, None]}],
        "n": 5,
    }
    out = rsa.rewrite_paths(obj, "/tmp/x/py-01", "specimens/python/py-01")
    assert out == {
        "source_file": "specimens/python/py-01/app.py",
        "items": [
            "specimens/python/py-01/a",
            {"deep": ["specimens/python/py-01/b", 3, None]},
        ],
        "n": 5,
    }


# --- score -----------------------------------------------------------------

def _defect(did, func, category, file="app.py"):
    return {
        "id": did,
        "file": file,
        "function": func,
        "line": 1,
        "anchor": "x",
        "class": "bug",
        "category": category,
        "cwe": None,
        "title": did,
        "description": did,
        "trigger": "t",
        "observed": "o",
        "repro": "r_" + did.lower().replace("-", "_"),
    }


def _audit():
    return {
        "file_results": [
            {
                "source_file": "specimens/python/py-01-demo/app.py",
                "verification_violations": [
                    "Python function `transfer` can cause integer overflow",
                    "Python function `helper` returns early",
                    "Python function `stray` has no caller",
                    "check transfer: Z3 Counter-example: a=1",
                    "model check: Z3 Counter-example: z=9",
                    "Z3 Counter-example: int32(len(locations))=0",
                ],
                "counterexample_values": [
                    {"function_name": "transfer", "counterexample": {"a": 1}}
                ],
            },
            {"source_file": "specimens/python/py-01-demo/other.py"},
        ],
    }


def _defects_doc():
    return {
        "defects": [
            _defect("PY01-D01", "transfer", "integer-overflow"),
            _defect("PY01-D02", "helper", "logic-error"),
            _defect("PY01-D03", "cleanup", "resource-leak"),
            _defect("PY01-D04", "untouched", "null-dereference", file="other.py"),
        ]
    }


def test_score_statuses():
    scored = rsa.score(_defects_doc(), _audit(), "specimens/python/py-01-demo")
    by_id = {r["id"]: r for r in scored["defects"]}
    assert by_id["PY01-D01"]["status"] == "detected"
    assert by_id["PY01-D02"]["status"] == "function_flagged"
    assert by_id["PY01-D03"]["status"] == "missed"
    assert by_id["PY01-D04"]["status"] == "missed"


def test_score_unmatched_findings():
    scored = rsa.score(_defects_doc(), _audit(), "specimens/python/py-01-demo")
    texts = [f["text"] for f in scored["unmatched_findings"]]
    assert any("stray" in t for t in texts)
    assert not any("Z3 Counter-example" in t for t in texts)
    assert not any("counterexample for" in t for t in texts)


# --- counts / write_summary ------------------------------------------------

def test_counts():
    results = [
        {"status": "detected"},
        {"status": "detected"},
        {"status": "function_flagged"},
        {"status": "missed"},
        {"status": "missed"},
    ]
    assert rsa.counts(results) == {
        "total": 5, "detected": 2, "function_flagged": 1,
        "missed": 2,
    }


def _coverage(specimen, language, defects):
    return {
        "specimen": specimen,
        "language": language,
        "counts": rsa.counts(defects),
        "defects": defects,
        "unmatched_findings": [],
    }


def test_write_summary(tmp_path):
    meta = {
        "mumei_agent_commit": "aaa",
        "mumei_commit": "bbb",
        "mumei_version": "mumei 0.1",
        "llm_configured": False,
        "command": "cmd",
        "generated_at": "2025-01-01T00:00:00Z",
    }
    d = lambda status, cat: {"status": status, "category": cat,
                             "in_target_category": cat in rsa.TARGET_CATEGORIES}
    coverages = [
        _coverage("py-01-a", "python", [
            d("detected", "integer-overflow"),
            d("detected", "sql-injection"),
            d("missed", "path-traversal"),
        ]),
        _coverage("rs-01-b", "rust", [
            d("function_flagged", "division-by-zero"),
            d("missed", "error-handling"),
        ]),
    ]
    out = tmp_path / "AUDIT_SUMMARY.md"
    rsa.write_summary(coverages, meta, out)
    text = out.read_text()
    assert "| **Total** | **5** | **2** | **1** | **2** | **1/2** | **0** |" in text
    assert "| python | 3 | 2 (67%) | 2 (67%) | 1/1 (100%) |" in text
    assert "| rust | 2 | 0 (0%) | 1 (50%) | 0/1 (0%) |" in text
    assert "| [py-01-a](python/py-01-a/audit/audit.md) | 3 | 2 | 0 | 1 | 1/1 | 0 |" in text


# --- aggregate / history / scoreboard ---------------------------------------

def test_aggregate_numbers():
    d = lambda status, cat: {"status": status, "category": cat,
                             "in_target_category": cat in rsa.TARGET_CATEGORIES}
    coverages = [
        _coverage("py-01-a", "python", [
            d("detected", "integer-overflow"),
            d("detected", "sql-injection"),
            d("missed", "path-traversal"),
        ]),
        _coverage("rs-01-b", "rust", [
            d("function_flagged", "division-by-zero"),
            d("missed", "error-handling"),
        ]),
    ]
    agg = rsa.aggregate(coverages)
    assert agg["totals"] == {"total": 5, "detected": 2, "function_flagged": 1,
                            "missed": 2,
                            "target_total": 2, "target_detected": 1, "unmatched": 0}
    assert agg["by_language"]["python"] == {"total": 3, "detected": 2, "flagged": 2,
                                            "target_total": 1, "target_detected": 1}
    assert agg["by_language"]["rust"]["flagged"] == 1
    assert agg["by_category"]["integer-overflow"] == {
        "total": 1, "detected": 1, "function_flagged": 0,
        "missed": 0, "in_target": True}
    assert agg["by_category"]["sql-injection"]["in_target"] is False


def _run(agent="aaaaaaa1111", mumei="bbbbbbb2222", corpus_hash="h1",
         date="2025-01-02", detected=3, total=10, flagged_extra=1,
         tgt_total=5, tgt_det=2, llm=True):
    return {
        "generated_at": f"{date}T00:00:00Z",
        "mumei_agent_commit": agent,
        "mumei_commit": mumei,
        "mumei_version": "mumei 0.1",
        "llm_configured": llm,
        "llm": llm,
        "corpus": {"specimens": 2, "defects": total, "hash": corpus_hash},
        "totals": {"total": total, "detected": detected,
                   "function_flagged": flagged_extra,
                   "missed": total - detected - flagged_extra,
                   "target_total": tgt_total, "target_detected": tgt_det},
        "by_language": {
            "python": {"total": 6, "detected": 2, "flagged": 3,
                       "target_total": 3, "target_detected": 1},
            "rust": {"total": 4, "detected": 1, "flagged": 1,
                     "target_total": 2, "target_detected": 1},
        },
        "by_category": {"integer-overflow": {"total": 2, "detected": 1,
                                             "in_target": True}},
        "specimens": {"py-01-a": {"language": "python", "total": 6, "detected": 2,
                                  "function_flagged": 1}},
    }


def test_record_run_append_and_replace(tmp_path):
    hp = tmp_path / "history.json"
    rsa.record_run(hp, _run())
    # same (agent, mumei, corpus hash) -> replaces, not appends
    rsa.record_run(hp, _run(detected=4))
    hist = json.loads(hp.read_text())
    assert len(hist["runs"]) == 1
    assert hist["runs"][0]["totals"]["detected"] == 4
    # different corpus hash -> appends
    rsa.record_run(hp, _run(corpus_hash="h2", date="2025-01-03"))
    hist = json.loads(hp.read_text())
    assert len(hist["runs"]) == 2
    # different agent commit -> appends
    rsa.record_run(hp, _run(agent="ccccccc3333", corpus_hash="h2", date="2025-01-04"))
    assert len(json.loads(hp.read_text())["runs"]) == 3
    # file is written with sorted keys
    assert '"by_category"' in hp.read_text()





def _parse(svg):
    return ET.fromstring(svg)


def test_svg_by_language_parses_and_labels():
    svg = rsa.svg_by_language({False: None, True: None})
    root = _parse(svg)
    assert "No benchmark runs yet" in ET.tostring(root, encoding="unicode")
    run = _run(llm=False)
    svg = rsa.svg_by_language(rsa.latest_by_mode([run]))
    root = _parse(svg)
    text = ET.tostring(root, encoding="unicode")
    assert "Specimen benchmark — detection by language" in text
    assert "aaaaaaa" in text  # sha7 subtitle
    assert "python" in text and "rust" in text and "overall" in text
    assert "2/6 · 33%" in text  # detected bar label
    assert "With LLM (not run yet)" in text
    assert root.attrib["viewBox"].startswith("0 0 ")


def test_svg_history_zero_one_three_runs():
    # zero runs -> placeholder
    svg = rsa.svg_history([])
    assert "No benchmark runs yet" in ET.tostring(_parse(svg), encoding="unicode")

    ns = "{http://www.w3.org/2000/svg}"
    one = _run()
    svg = rsa.svg_history([one])
    root = _parse(svg)
    text = ET.tostring(root, encoding="unicode")
    assert "aaaaaaa" in text and "2025-01-02" in text
    # single run: points but no polyline
    assert not any(e.tag == f"{ns}polyline" for e in root.iter())
    assert any(e.tag == f"{ns}circle" for e in root.iter())

    three = [_run(date="2025-01-02"),
             _run(agent="ddddddd4444", corpus_hash="h2", date="2025-02-03"),
             _run(agent="eeeeeee5555", corpus_hash="h3", date="2025-03-04")]
    svg = rsa.svg_history(three)
    root = _parse(svg)
    assert sum(1 for e in root.iter() if e.tag == f"{ns}polyline") == 3
    text = ET.tostring(root, encoding="unicode")
    assert "detected or flagged" in text
    assert "eeeeeee" in text


def test_update_scoreboard_block_idempotent_and_missing(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# head\n\n<!-- scoreboard:start -->\nold\n<!-- scoreboard:end -->\n\n# tail\n")
    rsa.update_scoreboard_block(readme, "BLOCK")
    first = readme.read_text()
    assert "# head" in first and "# tail" in first and "BLOCK" in first
    rsa.update_scoreboard_block(readme, "BLOCK2")
    second = readme.read_text()
    assert "\nBLOCK\n" not in second and "BLOCK2" in second
    # re-render same content is idempotent
    rsa.update_scoreboard_block(readme, "BLOCK2")
    assert readme.read_text() == second

    readme.write_text("no markers here\n")
    with pytest.raises(SystemExit):
        rsa.update_scoreboard_block(readme, "X")


def test_render_only_end_to_end(tmp_path):
    scoreboard = tmp_path / "scoreboard"
    scoreboard.mkdir()
    (scoreboard / "history.json").write_text(
        json.dumps({"schema": 1, "runs": [_run()]}))
    spec_readme = tmp_path / "specimens_README.md"
    spec_readme.write_text("# s\n<!-- scoreboard:start -->\nx\n<!-- scoreboard:end -->\n")
    top_readme = tmp_path / "README.md"
    top_readme.write_text("# t\n<!-- scoreboard:start -->\nx\n<!-- scoreboard:end -->\n")

    rc = rsa.main([
        "--render-only",
        "--scoreboard-dir", str(scoreboard),
        "--specimens-readme", str(spec_readme),
        "--top-readme", str(top_readme),
    ])
    assert rc == 0
    _parse((scoreboard / "by_language.svg").read_text())
    _parse((scoreboard / "history.svg").read_text())
    spec_text = spec_readme.read_text()
    assert "## Scoreboard" in spec_text
    assert "python" in spec_text and "**Total**" in spec_text
    assert "Recent runs" in spec_text and "aaaaaaa" in spec_text
    top_text = top_readme.read_text()
    assert "## Specimen benchmark" in top_text
    assert "3/10 detected" in top_text


def test_category_hit_ignores_generic_audit_wording():
    access = ("Solidity function `finalize` is an externally callable state-mutating function "
              "with no access-control guard")
    reentrancy = ("Solidity function `bid` may be vulnerable to reentrancy: verified "
                  "guard-state-machine trace shows an external call reachable in the Unlocked state")
    lowering = "encoding-gap: f: spec_lowering_failed: Verification Error: Expected bool for =="
    assert not rsa.category_hit(access, "invalid-state-transition")
    assert not rsa.category_hit(reentrancy, "invalid-state-transition")
    assert not rsa.category_hit(reentrancy, "race-condition")
    assert not rsa.category_hit(lowering, "error-handling")
    assert rsa.category_hit(access, "access-control")
    assert rsa.category_hit(reentrancy, "reentrancy")


# --- corpus_info / audit_failure ---------------------------------------------

def _mini_specimen(root):
    d = root / "python" / "py-01-x"
    d.mkdir(parents=True)
    (d / "DEFECTS.json").write_text(json.dumps({
        "specimen": "py-01-x", "language": "python", "kind": "cli",
        "summary": "x", "defects": [_defect("PY01-D01", "f", "logic-error")],
    }))
    (d / "app.py").write_text("def f():\n    return 1\n")
    return d


def test_corpus_info_tracks_source_changes(tmp_path):
    d = _mini_specimen(tmp_path)
    c1 = rsa.corpus_info(tmp_path)
    assert c1["specimens"] == 1 and c1["defects"] == 1
    # editing a source file changes the hash even with DEFECTS.json unchanged
    (d / "app.py").write_text("def f():\n    return 2\n")
    c2 = rsa.corpus_info(tmp_path)
    assert c2["hash"] != c1["hash"]
    assert c2["defects"] == c1["defects"]
    # editing audit/ output does not change the hash
    (d / "audit").mkdir()
    (d / "audit" / "coverage.json").write_text("{}")
    c3 = rsa.corpus_info(tmp_path)
    assert c3["hash"] == c2["hash"]



def test_audit_failure():
    good = {"success": False, "errors": [], "skipped_rate_limited_files": []}
    # audit["success"]=False is normal (issues found), not a failure
    assert rsa.audit_failure(0, 0, good) is None
    assert "exited 3" in rsa.audit_failure(3, 0, good)
    assert "markdown" in rsa.audit_failure(0, 1, good)
    assert "boom" in rsa.audit_failure(0, 0, {"errors": ["boom"]})
    assert "rate-limited" in rsa.audit_failure(
        0, 0, {"skipped_rate_limited_files": ["a.py"]})


# --- adjudications -----------------------------------------------------------

ADJ = [{
    "defect": "PY01-D01",
    "finding_contains": "integer overflow",
    "verdict": "not_category_evidence",
    "reason": "the cast warning is not evidence of the missing precondition",
}]


def test_score_adjudication_downgrades():
    scored = rsa.score(_defects_doc(), _audit(), "specimens/python/py-01-demo",
                       adjudications=ADJ)
    by_id = {r["id"]: r for r in scored["defects"]}
    assert by_id["PY01-D01"]["status"] == "function_flagged"
    assert by_id["PY01-D01"]["adjudicated"] == [
        "the cast warning is not evidence of the missing precondition"]
    # the finding is still reported on the defect
    assert any("overflow" in f for f in by_id["PY01-D01"]["findings"])
    # unaffected defects carry no key
    assert "adjudicated" not in by_id["PY01-D02"]


def test_score_nonmatching_adjudication_noop():
    adj = [dict(ADJ[0], finding_contains="no such text")]
    scored = rsa.score(_defects_doc(), _audit(), "specimens/python/py-01-demo",
                       adjudications=adj)
    by_id = {r["id"]: r for r in scored["defects"]}
    assert by_id["PY01-D01"]["status"] == "detected"
    assert "adjudicated" not in by_id["PY01-D01"]


def test_load_adjudications_unknown_id(tmp_path):
    d = _mini_specimen(tmp_path)
    (tmp_path / "scoreboard").mkdir()
    (tmp_path / "scoreboard" / "adjudications.json").write_text(json.dumps({
        "adjudications": [{"defect": "ZZ99-D01",
                           "finding_contains": "x",
                           "verdict": "not_category_evidence",
                           "reason": "y"}]}))
    with pytest.raises(SystemExit, match="unknown defect"):
        rsa.load_adjudications(tmp_path)
    # a valid file for the known defect loads fine
    (tmp_path / "scoreboard" / "adjudications.json").write_text(json.dumps({
        "adjudications": [{"defect": "PY01-D01",
                           "finding_contains": "x",
                           "verdict": "not_category_evidence",
                           "reason": "y"}]}))
    assert len(rsa.load_adjudications(tmp_path)) == 1


def test_record_run_scoring_hash_in_key(tmp_path):
    hp = tmp_path / "history.json"
    rsa.record_run(hp, _run())
    # unchanged scoring -> replaces
    rsa.record_run(hp, _run(detected=4))
    assert len(json.loads(hp.read_text())["runs"]) == 1
    # changed adjudications content -> new scoring_hash -> appends
    rsa.record_run(hp, _run(date="2025-01-05", detected=4))
    hist = json.loads(hp.read_text())
    entry = dict(hist["runs"][-1], scoring_hash="deadbeef")
    rsa.record_run(hp, entry)
    assert len(json.loads(hp.read_text())["runs"]) == 2
    # older entry without scoring_hash is treated as the empty-file hash:
    # an entry hashing b"" still replaces it
    import hashlib
    last = dict(entry, scoring_hash=hashlib.sha256(b"").hexdigest(),
                generated_at="2025-01-06T00:00:00Z")
    # does NOT match 'deadbeef' -> appends
    rsa.record_run(hp, last)
    assert len(json.loads(hp.read_text())["runs"]) == 3
    # a fresh no-hash entry does NOT replace a deadbeef-scored run... but
    # matches the last (empty-hash) entry, so it replaces that one
    rsa.record_run(hp, dict(last))
    hist = json.loads(hp.read_text())
    assert len(hist["runs"]) == 3


def test_scoring_hash_missing_and_present(tmp_path):
    import hashlib
    assert rsa.scoring_hash(tmp_path) == hashlib.sha256(b"").hexdigest()
    (tmp_path / "scoreboard").mkdir()
    (tmp_path / "scoreboard" / "adjudications.json").write_text('{"adjudications":[]}')
    assert rsa.scoring_hash(tmp_path) == hashlib.sha256(
        b'{"adjudications":[]}').hexdigest()


def test_record_run_llm_modes_stay_separate(tmp_path):
    hp = tmp_path / "history.json"
    rsa.record_run(hp, _run(llm=False))
    # a with-LLM run on the same key appends instead of replacing
    rsa.record_run(hp, _run(llm=True, date="2025-01-03", detected=5))
    hist = json.loads(hp.read_text())
    assert len(hist["runs"]) == 2
    assert [rsa.entry_llm(r) for r in hist["runs"]] == [False, True]
    # a rerun in one mode replaces only that mode's entry
    rsa.record_run(hp, _run(llm=True, date="2025-01-04", detected=7))
    hist = json.loads(hp.read_text())
    assert len(hist["runs"]) == 2
    assert hist["runs"][1]["totals"]["detected"] == 7
    assert hist["runs"][0]["totals"]["detected"] == 3
    # older entries without an `llm` key infer the mode from llm_configured
    legacy = _run(llm=False, detected=9)
    del legacy["llm"]
    assert rsa.entry_llm(legacy) is False
    rsa.record_run(hp, legacy)
    hist = json.loads(hp.read_text())
    # the legacy run keys as no-LLM, so it replaces that mode's entry — which is
    # not the last one, so it appends instead of clobbering the with-LLM run
    assert len(hist["runs"]) == 3
    assert [rsa.entry_llm(r) for r in hist["runs"]] == [False, True, False]


def test_latest_by_mode_picks_newest_per_mode():
    runs = [_run(llm=False, date="2025-01-02"),
            _run(llm=False, date="2025-02-01", detected=8),
            _run(llm=True, date="2025-01-05", detected=1)]
    modes = rsa.latest_by_mode(runs)
    assert modes[False]["totals"]["detected"] == 8
    assert modes[True]["totals"]["detected"] == 1


def test_readme_blocks_no_llm_run_shows_llm_placeholder():
    block = rsa.readme_block_specimens({"runs": [_run(llm=False)]})
    assert "With LLM detected" in block
    assert "not run yet" in block
    assert "—" in block
    assert "| LLM |" in block
    top = rsa.readme_block_top({"runs": [_run(llm=False)]})
    assert "no LLM: 3/10 detected" in top
    assert "with LLM: not run yet" in top


def test_readme_blocks_llm_run_fills_columns():
    block = rsa.readme_block_specimens(
        {"runs": [_run(llm=False), _run(llm=True, date="2025-01-03", detected=5)]})
    assert "5/10 (50%)" in block
    assert "not run yet" not in block
    top = rsa.readme_block_top(
        {"runs": [_run(llm=False), _run(llm=True, detected=5)]})
    assert "with LLM: 5/10 detected" in top


def test_svg_modes_parse():
    ns = "{http://www.w3.org/2000/svg}"
    both = [_run(llm=False), _run(llm=True, date="2025-01-03", corpus_hash="h2")]
    for runs in ([_run(llm=False)], both):
        root = _parse(rsa.svg_by_language(rsa.latest_by_mode(runs)))
        text = ET.tostring(root, encoding="unicode")
        assert "detected" in text
        hist = _parse(rsa.svg_history(runs))
        htext = ET.tostring(hist, encoding="unicode")
        assert "(not run yet)" in htext or "with LLM" in htext
    # two runs in different modes: each mode's series gets its own points
    root = _parse(rsa.svg_history(both))
    assert any(e.tag == f"{ns}circle" for e in root.iter())


def test_svg_history_shared_x_axis_per_mode():
    # two no-LLM runs with one with-LLM run in between: all three land on
    # distinct global-index x positions and each series marks only its own runs
    ns = "{http://www.w3.org/2000/svg}"
    runs = [_run(llm=False, date="2025-01-02"),
            _run(llm=True, date="2025-01-03", corpus_hash="h2", agent="ddddddd4444"),
            _run(llm=False, date="2025-01-04", corpus_hash="h3", agent="eeeeeee5555")]
    root = _parse(rsa.svg_history(runs))
    label_xs = sorted({
        float(e.attrib["x"]) for e in root.iter(f"{ns}text")
        if e.attrib.get("text-anchor") == "middle" and "y" in e.attrib
    })
    assert len(label_xs) == 3
    # the with-LLM run is the middle one on the shared axis
    middle_x = label_xs[1]
    llm_circles = [e for e in root.iter(f"{ns}circle")]
    assert any(float(c.attrib["cx"]) == middle_x for c in llm_circles)
    text = ET.tostring(root, encoding="unicode")
    assert "2025-01-03 · With LLM" in text
    assert "2025-01-02 · No LLM" in text


# --- llm_configured ---------------------------------------------------------

def test_llm_configured_env_parsing(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    repo = tmp_path / "agent"
    repo.mkdir()
    # no .env at all
    assert rsa.llm_configured(repo) is False
    # empty .env
    (repo / ".env").write_text("")
    assert rsa.llm_configured(repo) is False
    # unrelated key only
    (repo / ".env").write_text("LLM_MODEL=x\n")
    assert rsa.llm_configured(repo) is False
    # explicitly empty key
    (repo / ".env").write_text('LLM_API_KEY=""\n')
    assert rsa.llm_configured(repo) is False
    # OPENAI_API_KEY in .env
    (repo / ".env").write_text("OPENAI_API_KEY=sk-test\n")
    assert rsa.llm_configured(repo) is True
    # export prefix + quotes + comments
    (repo / ".env").write_text('# c\nexport LLM_API_KEY="sk-q"\n')
    assert rsa.llm_configured(repo) is True
    # env var wins without .env
    (repo / ".env").unlink()
    monkeypatch.setenv("LLM_API_KEY", "sk-env")
    assert rsa.llm_configured(repo) is True


# --- defects cell with mixed corpora ----------------------------------------

def test_readme_defects_cell_mixed_modes():
    nollm = _run(llm=False)
    llm = _run(llm=True, date="2025-01-03")
    # drop `rust` from the no-LLM run's language table and shrink its totals
    nollm["by_language"] = {"python": {"total": 6, "detected": 2, "flagged": 3,
                                     "target_total": 3, "target_detected": 1}}
    llm["by_language"]["rust"]["total"] = 5
    llm["totals"]["total"] = 175
    block = rsa.readme_block_specimens({"runs": [nollm, llm]})
    rust_row = next(l for l in block.splitlines() if l.startswith("| rust"))
    # the with-LLM run's total shows for a language the no-LLM run lacks
    assert "| rust | 5 |" in rust_row
    total_row = next(l for l in block.splitlines() if l.startswith("| **Total**"))
    # 10 vs 175: both modes' totals are shown, each labelled
    assert "10 (No LLM) / 175 (With LLM)" in total_row
    python_row = next(l for l in block.splitlines() if l.startswith("| python"))
    assert "| python | 6 |" in python_row


# --- legend bounds ----------------------------------------------------------

def _legend_elements(svg):
    root = _parse(svg)
    ns = "{http://www.w3.org/2000/svg}"
    items = []
    for e in root.iter():
        if e.tag not in (f"{ns}rect", f"{ns}text"):
            continue
        y = float(e.attrib.get("y", -1))
        items.append((float(e.attrib.get("x", 0)), y,
                      float(e.attrib.get("width", 0)),
                      e.attrib.get("font-size", ""), e.attrib.get("fill", "")))
    return items, root


def test_svg_legends_fit_viewbox_both_modes():
    import re
    runs = [_run(llm=False), _run(llm=True, date="2025-01-03", corpus_hash="h2")]
    for svg in (rsa.svg_by_language(rsa.latest_by_mode(runs)),
                rsa.svg_history(runs)):
        m = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
        W, H = int(m.group(1)), int(m.group(2))
        # legend zone = bottom ~120px of the canvas
        for x, y, w, fs, fill in _legend_elements(svg)[0]:
            if y < H - 130:
                continue
            est_w = w if w else 6.5 * 40  # text width is approximated anyway
            assert x <= W, f"element at x={x} exceeds W={W}: {svg[:80]}"
            assert y + 12 <= H, f"element at y={y} exceeds H={H}"
