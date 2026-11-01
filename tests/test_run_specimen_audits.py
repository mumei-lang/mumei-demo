"""Unit tests for the pure functions in scripts/run_specimen_audits.py.

No subprocess or real audit calls: the module is imported by path and fed
hand-built defects docs / audit dicts.
"""

import importlib.util
import json
import subprocess
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


# --- finding-level precision -------------------------------------------------

LABEL = "specimens/python/py-01-demo"


def _review(contains, verdict="false_positive", specimen="py-01-demo", file="app.py",
            reason="r"):
    return {"specimen": specimen, "file": file, "finding_contains": contains,
            "verdict": verdict, "reason": reason}


def _doc(specimen="py-01-demo"):
    return {**_defects_doc(), "specimen": specimen}


def _statuses(scored):
    return {f["text"]: f["status"] for f in scored["findings"]}


def test_is_supporting():
    assert rsa.is_supporting({"kind": "counterexample_values", "text": "x"})
    assert rsa.is_supporting({"kind": "verification_violations",
                              "text": "check f: Z3 Counter-example: a=1"})
    assert not rsa.is_supporting({"kind": "verification_violations", "text": "f overflows"})


def test_score_findings_exclude_supporting_entries():
    scored = rsa.score(_doc(), _audit(), LABEL)
    texts = [f["text"] for f in scored["findings"]]
    assert len(texts) == 3
    assert not any("Counter-example" in t or "counterexample for" in t for t in texts)


def test_score_findings_unreviewed_by_default():
    scored = rsa.score(_doc(), _audit(), LABEL)
    st = _statuses(scored)
    assert st["Python function `transfer` can cause integer overflow"] == "defect_evidence"
    assert st["Python function `helper` returns early"] == "unreviewed"
    assert st["Python function `stray` has no caller"] == "unreviewed"
    assert scored["finding_counts"] == {"total": 3, "defect_evidence": 1, "real": 0,
                                        "false_positive": 0, "unreviewed": 2}
    assert scored["reviews_used"] == []


def test_score_findings_reviews_apply():
    reviews = [_review("`helper` returns early", "real", reason="early return skips audit"),
               _review("`stray` has no caller")]
    scored = rsa.score(_doc(), _audit(), LABEL, finding_reviews=reviews)
    st = _statuses(scored)
    assert st["Python function `helper` returns early"] == "real"
    assert st["Python function `stray` has no caller"] == "false_positive"
    helper = next(f for f in scored["findings"] if "helper" in f["text"])
    assert helper["reason"] == "early return skips audit"
    assert scored["finding_counts"]["unreviewed"] == 0
    assert sorted(map(tuple, scored["reviews_used"])) == sorted(rsa.review_key(r) for r in reviews)


def test_score_findings_review_never_overrides_category_evidence():
    reviews = [_review("integer overflow")]
    scored = rsa.score(_doc(), _audit(), LABEL, finding_reviews=reviews)
    assert _statuses(scored)["Python function `transfer` can cause integer overflow"] == \
        "defect_evidence"
    assert scored["reviews_used"] == []


@pytest.mark.parametrize("review", [
    _review("`stray` has no caller", specimen="py-02-other"),
    _review("`stray` has no caller", file="other.py"),
    _review("text that appears nowhere"),
])
def test_score_findings_review_scope(review):
    scored = rsa.score(_doc(), _audit(), LABEL, finding_reviews=[review])
    assert _statuses(scored)["Python function `stray` has no caller"] == "unreviewed"
    assert scored["reviews_used"] == []


def test_score_findings_same_verdict_overlap_marks_both_used():
    reviews = [_review("`stray`"), _review("has no caller")]
    scored = rsa.score(_doc(), _audit(), LABEL, finding_reviews=reviews)
    assert _statuses(scored)["Python function `stray` has no caller"] == "false_positive"
    assert len(scored["reviews_used"]) == 2


def test_score_findings_conflicting_verdicts_fail():
    reviews = [_review("`stray`", "real"), _review("has no caller", "false_positive")]
    with pytest.raises(SystemExit, match="conflicting finding reviews"):
        rsa.score(_doc(), _audit(), LABEL, finding_reviews=reviews)


def test_score_findings_one_review_can_cover_several_findings():
    scored = rsa.score(_doc(), _audit(), LABEL,
                       finding_reviews=[_review("Python function `")])
    assert scored["finding_counts"] == {"total": 3, "defect_evidence": 1, "real": 0,
                                        "false_positive": 2, "unreviewed": 0}


def test_score_findings_adjudicated_defect_hit_is_no_longer_evidence():
    adj = [{"defect": "PY01-D01", "verdict": "not_category_evidence",
            "finding_contains": "integer overflow", "reason": "r"}]
    scored = rsa.score(_doc(), _audit(), LABEL, adj)
    assert _statuses(scored)["Python function `transfer` can cause integer overflow"] == \
        "unreviewed"


def test_score_findings_counts_add_up():
    scored = rsa.score(_doc(), _audit(), LABEL,
                       finding_reviews=[_review("`stray`")])
    fc = scored["finding_counts"]
    assert fc["total"] == sum(fc[s] for s in rsa.FINDING_STATUSES) == len(scored["findings"])


def test_score_findings_no_file_results():
    scored = rsa.score(_doc(), {}, LABEL)
    assert scored["findings"] == []
    assert scored["finding_counts"]["total"] == 0


@pytest.mark.parametrize("fc, expected", [
    (None, None),
    ({}, None),
    ({"total": 0}, None),
    ({"total": 4, "defect_evidence": 1, "real": 1, "false_positive": 2, "unreviewed": 0},
     (0.5, 0.5)),
    ({"total": 4, "defect_evidence": 1, "real": 0, "false_positive": 1, "unreviewed": 2},
     (0.25, 0.75)),
    ({"total": 2, "defect_evidence": 0, "real": 0, "false_positive": 0, "unreviewed": 2},
     (0.0, 1.0)),
])
def test_precision_range(fc, expected):
    assert rsa.precision_range(fc) == expected


@pytest.mark.parametrize("fc, expected", [
    (None, "—"),
    ({"total": 0, "defect_evidence": 0, "real": 0, "false_positive": 0, "unreviewed": 0}, "n/a"),
    ({"total": 3, "defect_evidence": 1, "real": 0, "false_positive": 2, "unreviewed": 0}, "33%"),
    ({"total": 4, "defect_evidence": 1, "real": 0, "false_positive": 1, "unreviewed": 2},
     "25%–75%"),
    ({"total": 1, "defect_evidence": 1, "real": 0, "false_positive": 0, "unreviewed": 0}, "100%"),
])
def test_fmt_precision(fc, expected):
    assert rsa.fmt_precision(fc) == expected


def test_stale_reviews():
    used = _review("used")
    unused = _review("unused")
    other_specimen = _review("x", specimen="py-09-unscored")
    coverages = [{"specimen": "py-01-demo", "reviews_used": [list(rsa.review_key(used))]}]
    assert rsa.stale_reviews(coverages, [used, unused, other_specimen]) == [unused]
    assert rsa.stale_reviews([], [unused]) == []


def _fc(total, ev, real, fp, unrev):
    return {"total": total, "defect_evidence": ev, "real": real,
            "false_positive": fp, "unreviewed": unrev}


def test_aggregate_findings_sum_and_tolerate_old_coverages():
    a = {**_coverage("py-01-a", "python", []), "finding_counts": _fc(3, 1, 1, 1, 0)}
    b = {**_coverage("rs-01-b", "rust", []), "finding_counts": _fc(2, 0, 0, 1, 1)}
    old = _coverage("go-01-c", "go", [])
    assert rsa.aggregate([a, b, old])["findings"] == _fc(5, 1, 1, 2, 1)
    assert rsa.aggregate([])["findings"] == _fc(0, 0, 0, 0, 0)


def _summary_meta():
    return {"mumei_agent_commit": "aaa", "mumei_commit": "bbb", "mumei_version": "mumei 0.1",
            "llm_configured": False, "command": "cmd", "generated_at": "2025-01-01T00:00:00Z"}


def test_write_summary_precision_and_findings(tmp_path):
    cov = {**_coverage("py-01-a", "python", []), "finding_counts": _fc(3, 1, 1, 0, 1),
           "findings": [
               {"file": "app.py", "kind": "verification_violations", "text": "f overflows",
                "status": "defect_evidence"},
               {"file": "app.py", "kind": "verification_violations", "text": "g | leaks",
                "status": "real", "reason": "g leaks a handle"},
               {"file": "app.py", "kind": "verification_violations", "text": "h is odd",
                "status": "unreviewed"},
           ]}
    out = tmp_path / "AUDIT_SUMMARY.md"
    stale = [_review("vanished text", specimen="py-01-a")]
    rsa.write_summary([cov], _summary_meta(), out, stale)
    text = out.read_text()
    assert "Findings: 3 — defect evidence 1, real 1, false positive 0, unreviewed 1; " \
           "precision 67%–100%." in text
    assert "g leaks a handle" in text
    assert "h is odd" in text
    assert "g \\| leaks" in text
    assert "vanished text" in text
    assert "f overflows" not in text.split("## Findings that are not defect evidence")[1]


def test_write_summary_without_stale_has_no_stale_section(tmp_path):
    cov = {**_coverage("py-01-a", "python", []), "finding_counts": _fc(0, 0, 0, 0, 0),
           "findings": []}
    out = tmp_path / "AUDIT_SUMMARY.md"
    rsa.write_summary([cov], _summary_meta(), out)
    text = out.read_text()
    assert "Stale" not in text and "stale finding" not in text.lower()
    assert "precision n/a" in text


def test_history_entry_records_findings_and_rescore():
    cov = {**_coverage("py-01-a", "python", []), "finding_counts": _fc(2, 1, 0, 1, 0)}
    meta = {**_summary_meta(), "rescored_at": "2025-02-01T00:00:00Z"}
    entry = rsa.history_entry([cov], meta, {"specimens": 1, "defects": 0, "hash": "h"}, "s", 2)
    assert entry["findings"] == _fc(2, 1, 0, 1, 0)
    assert entry["stale_finding_reviews"] == 2
    assert entry["rescored_at"] == "2025-02-01T00:00:00Z"
    plain = rsa.history_entry([cov], _summary_meta(), {"specimens": 1, "defects": 0, "hash": "h"}, "s")
    assert "rescored_at" not in plain
    assert plain["stale_finding_reviews"] == 0


def test_readme_blocks_show_precision_and_dash_for_old_runs():
    old = _run(date="2025-01-01", llm=False)
    new = {**_run(date="2025-01-02", llm=False), "findings": _fc(4, 1, 1, 1, 1),
           "rescored_at": "2025-01-05T00:00:00Z"}
    history = {"schema": 2, "runs": [old, new]}
    spec = rsa.readme_block_specimens(history)
    assert "| Precision |" in spec
    assert "2025-01-02 (rescored 2025-01-05)" in spec
    assert "50%–75%" in spec
    assert "| — |" in spec
    assert "Findings — no LLM: 4" in spec
    top = rsa.readme_block_top(history)
    assert "precision 50%–75% of 4 findings" in top


def test_readme_block_top_omits_precision_for_old_runs():
    top = rsa.readme_block_top({"schema": 1, "runs": [_run(llm=False)]})
    assert "precision" not in top


def _write_finding_reviews(root, reviews):
    (root / "scoreboard").mkdir(exist_ok=True)
    (root / "scoreboard" / "adjudications.json").write_text(
        json.dumps({"adjudications": [], "finding_reviews": reviews}))


def test_load_finding_reviews_absent_file(tmp_path):
    assert rsa.load_finding_reviews(tmp_path) == []


def test_load_finding_reviews_valid(tmp_path):
    _mini_specimen(tmp_path)
    reviews = [_review("x", specimen="py-01-x"), _review("y", "real", specimen="py-01-x")]
    _write_finding_reviews(tmp_path, reviews)
    assert rsa.load_finding_reviews(tmp_path) == reviews


@pytest.mark.parametrize("bad, message", [
    ({"verdict": "maybe"}, "unsupported verdict"),
    ({"verdict": "not_category_evidence"}, "unsupported verdict"),
    ({"specimen": "py-99-nope"}, "unknown specimen"),
    ({"file": "missing.py"}, "unknown file"),
    ({"reason": ""}, "missing or empty 'reason'"),
    ({"reason": "   "}, "missing or empty 'reason'"),
    ({"finding_contains": None}, "missing or empty 'finding_contains'"),
    ({"verdict": 1}, "missing or empty 'verdict'"),
])
def test_load_finding_reviews_rejects(tmp_path, bad, message):
    _mini_specimen(tmp_path)
    _write_finding_reviews(tmp_path, [{**_review("x", specimen="py-01-x"), **bad}])
    with pytest.raises(SystemExit, match=message):
        rsa.load_finding_reviews(tmp_path)


def test_load_finding_reviews_rejects_missing_field(tmp_path):
    _mini_specimen(tmp_path)
    r = _review("x", specimen="py-01-x")
    del r["file"]
    _write_finding_reviews(tmp_path, [r])
    with pytest.raises(SystemExit, match="missing or empty 'file'"):
        rsa.load_finding_reviews(tmp_path)


def test_load_finding_reviews_rejects_duplicates(tmp_path):
    _mini_specimen(tmp_path)
    _write_finding_reviews(tmp_path, [_review("x", specimen="py-01-x"),
                                      _review("x", "real", specimen="py-01-x")])
    with pytest.raises(SystemExit, match="duplicate finding review"):
        rsa.load_finding_reviews(tmp_path)


def test_scoring_hash_changes_with_finding_reviews(tmp_path):
    _mini_specimen(tmp_path)
    _write_finding_reviews(tmp_path, [])
    before = rsa.scoring_hash(tmp_path)
    _write_finding_reviews(tmp_path, [_review("x", specimen="py-01-x")])
    assert rsa.scoring_hash(tmp_path) != before


# --- --rescore ------------------------------------------------------------------

RESCORE_META = {"mumei_agent_commit": "aaaaaaa1111", "mumei_commit": "bbbbbbb2222",
                "mumei_version": "mumei 0.1", "llm_configured": False, "command": "cmd",
                "generated_at": "2025-01-01T00:00:00Z"}


def _rescore_tree(tmp_path, monkeypatch, meta=RESCORE_META, rc=0):
    specimens = tmp_path / "specimens"
    d = _mini_specimen(specimens)
    audit_dir = d / "audit"
    audit_dir.mkdir()
    (audit_dir / "audit.json").write_text(json.dumps({"file_results": [{
        "source_file": "specimens/python/py-01-x/app.py",
        "verification_violations": ["Python function `f` returns a constant",
                                    "Python function `g` overflows"],
    }]}))
    (audit_dir / "coverage.json").write_text(json.dumps(
        {"meta": meta, "audit_exit_code": rc, "audit_markdown_exit_code": rc}))
    monkeypatch.setattr(rsa, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rsa, "SPECIMENS_ROOT", specimens)
    _git_track(tmp_path)
    return specimens, d


def _git_track(root):
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)


def test_rescore_specimen_keeps_meta_and_exit_codes(tmp_path, monkeypatch):
    _, d = _rescore_tree(tmp_path, monkeypatch, rc=3)
    cov = rsa.rescore_specimen(d, [], [_review("`g` overflows", "real", specimen="py-01-x")])
    assert cov["meta"] == RESCORE_META
    assert cov["audit_exit_code"] == 3 and cov["audit_markdown_exit_code"] == 3
    assert cov["counts"]["function_flagged"] == 1
    assert cov["finding_counts"] == _fc(2, 0, 1, 0, 1)
    assert cov["source_hash"] == rsa.specimen_hash(d)
    written = json.loads((d / "audit" / "coverage.json").read_text())
    assert "finding_counts" not in written  # rescore_specimen never writes


def test_rescore_specimen_warns_on_legacy_coverage_without_hash(tmp_path, monkeypatch, capsys):
    _, d = _rescore_tree(tmp_path, monkeypatch)
    rsa.rescore_specimen(d, [], [])
    assert "predates source hashes" in capsys.readouterr().err


def test_rescore_specimen_accepts_matching_hash(tmp_path, monkeypatch, capsys):
    _, d = _rescore_tree(tmp_path, monkeypatch)
    cov_path = d / "audit" / "coverage.json"
    cov_path.write_text(json.dumps({**json.loads(cov_path.read_text()),
                                    "source_hash": rsa.specimen_hash(d)}))
    cov = rsa.rescore_specimen(d, [], [])
    assert cov["source_hash"] == rsa.specimen_hash(d)
    assert "predates" not in capsys.readouterr().err


@pytest.mark.parametrize("edit", ["source", "defects", "new_tracked_file", "removed_file"])
def test_rescore_specimen_refuses_changed_specimen(tmp_path, monkeypatch, edit):
    _, d = _rescore_tree(tmp_path, monkeypatch)
    cov_path = d / "audit" / "coverage.json"
    cov_path.write_text(json.dumps({**json.loads(cov_path.read_text()),
                                    "source_hash": rsa.specimen_hash(d)}))
    if edit == "source":
        (d / "app.py").write_text((d / "app.py").read_text() + "# edited\n")
    elif edit == "defects":
        (d / "DEFECTS.json").write_text((d / "DEFECTS.json").read_text() + "\n")
    elif edit == "new_tracked_file":
        (d / "extra.py").write_text("x = 1\n")
        _git_track(tmp_path)
    else:
        (d / "app.py").unlink()
    with pytest.raises(SystemExit, match="changed since the audit"):
        rsa.rescore_specimen(d, [], [])


def test_specimen_hash_ignores_untracked_and_audit_files(tmp_path, monkeypatch):
    monkeypatch.setattr(rsa, "REPO_ROOT", tmp_path)
    d = _mini_specimen(tmp_path / "specimens")
    _git_track(tmp_path)
    before = rsa.specimen_hash(d)
    (d / "Cargo.lock").write_text("lock")
    (d / "bin").mkdir()
    (d / "bin" / "app").write_text("binary")
    assert rsa.specimen_hash(d) == before
    (d / "audit").mkdir()
    (d / "audit" / "audit.json").write_text("{}")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(d / "audit")], check=True)
    assert rsa.specimen_hash(d) == before
    (d / "app.py").write_text("def f():\n    return 2\n")
    assert rsa.specimen_hash(d) != before


def test_specimen_hash_covers_file_names(tmp_path, monkeypatch):
    monkeypatch.setattr(rsa, "REPO_ROOT", tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    for d, name in ((a, "one.py"), (b, "two.py")):
        d.mkdir()
        (d / name).write_text("x = 1\n")
    _git_track(tmp_path)
    assert rsa.specimen_hash(a) != rsa.specimen_hash(b)


def _rescore_args(tmp_path):
    for name in ("specimens_README.md", "README.md"):
        (tmp_path / name).write_text("# x\n<!-- scoreboard:start -->\nx\n<!-- scoreboard:end -->\n")
    return ["--rescore",
            "--summary", str(tmp_path / "AUDIT_SUMMARY.md"),
            "--scoreboard-dir", str(tmp_path / "specimens" / "scoreboard"),
            "--specimens-readme", str(tmp_path / "specimens_README.md"),
            "--top-readme", str(tmp_path / "README.md")]


def test_main_rescore_end_to_end(tmp_path, monkeypatch, capsys):
    specimens, _ = _rescore_tree(tmp_path, monkeypatch)
    _write_finding_reviews(specimens, [
        _review("`g` overflows", "real", specimen="py-01-x"),
        _review("`f` returns a constant", specimen="py-01-x"),
        _review("wording that changed", specimen="py-01-x"),
    ])
    assert rsa.main(_rescore_args(tmp_path)) == 0
    err = capsys.readouterr().err
    assert "stale finding review" in err and "wording that changed" in err
    history = json.loads((specimens / "scoreboard" / "history.json").read_text())
    run = history["runs"][-1]
    assert history["schema"] == rsa.HISTORY_SCHEMA
    assert run["generated_at"] == RESCORE_META["generated_at"]
    assert run["rescored_at"]
    assert run["findings"] == _fc(2, 0, 1, 1, 0)
    assert run["stale_finding_reviews"] == 1
    assert "precision 50% of 2 findings" in (tmp_path / "README.md").read_text()
    assert "wording that changed" in (tmp_path / "AUDIT_SUMMARY.md").read_text()


def test_main_rescore_twice_replaces_run(tmp_path, monkeypatch):
    specimens, _ = _rescore_tree(tmp_path, monkeypatch)
    args = _rescore_args(tmp_path)
    assert rsa.main(args) == 0
    assert rsa.main(args) == 0
    history = json.loads((specimens / "scoreboard" / "history.json").read_text())
    assert len(history["runs"]) == 1
    _write_finding_reviews(specimens, [_review("`g` overflows", specimen="py-01-x")])
    assert rsa.main(args) == 0
    history = json.loads((specimens / "scoreboard" / "history.json").read_text())
    assert len(history["runs"]) == 2
    assert history["runs"][-1]["findings"]["false_positive"] == 1


def test_main_rescore_rejects_specimen_args(tmp_path, monkeypatch):
    _, d = _rescore_tree(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as exc:
        rsa.main(_rescore_args(tmp_path) + [str(d)])
    assert exc.value.code == 2


def test_main_rescore_and_render_only_are_exclusive(tmp_path, monkeypatch):
    _rescore_tree(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as exc:
        rsa.main(_rescore_args(tmp_path) + ["--render-only"])
    assert exc.value.code == 2


def test_main_rescore_rejects_mixed_runs(tmp_path, monkeypatch):
    specimens, _ = _rescore_tree(tmp_path, monkeypatch)
    d2 = specimens / "python" / "py-02-y"
    d2.mkdir()
    (d2 / "DEFECTS.json").write_text(json.dumps({
        "specimen": "py-02-y", "language": "python", "kind": "cli", "summary": "y",
        "defects": [_defect("PY02-D01", "f", "logic-error")]}))
    (d2 / "app.py").write_text("def f():\n    return 1\n")
    (d2 / "audit").mkdir()
    (d2 / "audit" / "audit.json").write_text(json.dumps({"file_results": []}))
    (d2 / "audit" / "coverage.json").write_text(json.dumps(
        {"meta": {**RESCORE_META, "generated_at": "2025-03-01T00:00:00Z"}}))
    before = {p: p.read_text() for p in specimens.glob("*/*/audit/coverage.json")}
    with pytest.raises(SystemExit, match="different runs"):
        rsa.main(_rescore_args(tmp_path))
    assert {p: p.read_text() for p in before} == before
    assert not (specimens / "scoreboard" / "history.json").exists()


def test_main_rescore_failure_on_later_specimen_writes_nothing(tmp_path, monkeypatch):
    specimens, _ = _rescore_tree(tmp_path, monkeypatch)
    d2 = specimens / "python" / "py-02-y"
    d2.mkdir()
    (d2 / "DEFECTS.json").write_text(json.dumps({
        "specimen": "py-02-y", "language": "python", "kind": "cli", "summary": "y",
        "defects": [_defect("PY02-D01", "f", "logic-error")]}))
    (d2 / "app.py").write_text("def f():\n    return 1\n")
    before = {p: p.read_text() for p in specimens.glob("*/*/audit/coverage.json")}
    with pytest.raises(SystemExit, match="nothing to rescore"):
        rsa.main(_rescore_args(tmp_path))
    assert {p: p.read_text() for p in before} == before


def test_main_rescore_writes_coverage_with_source_hash(tmp_path, monkeypatch):
    specimens, d = _rescore_tree(tmp_path, monkeypatch)
    assert rsa.main(_rescore_args(tmp_path)) == 0
    written = json.loads((d / "audit" / "coverage.json").read_text())
    assert written["source_hash"] == rsa.specimen_hash(d)
    assert written["meta"] == RESCORE_META
    (d / "app.py").write_text("def f():\n    return 3\n")
    with pytest.raises(SystemExit, match="changed since the audit"):
        rsa.main(_rescore_args(tmp_path))


def test_committed_finding_reviews_load_and_are_not_stale():
    reviews = rsa.load_finding_reviews(rsa.SPECIMENS_ROOT)
    coverages = [json.loads(p.read_text())
                 for p in sorted(rsa.SPECIMENS_ROOT.glob("*/*/audit/coverage.json"))]
    assert rsa.stale_reviews(coverages, reviews) == []
    for cov in coverages:
        fc = cov["finding_counts"]
        assert fc["total"] == sum(fc[s] for s in rsa.FINDING_STATUSES)


# --- fixed variants ----------------------------------------------------------

def test_score_fixed_reports_still_reported_and_false_alarms():
    fx = rsa.score_fixed(_doc(), _audit(), LABEL)
    assert fx["defects"] == 4
    assert fx["still_reported"] == ["PY01-D01"]
    assert fx["still_function_flagged"] == ["PY01-D02"]
    assert fx["finding_counts"] == _fc(3, 0, 0, 0, 3)
    assert fx["false_alarms"] == 3


def test_score_fixed_never_counts_category_evidence():
    fx = rsa.score_fixed(_doc(), _audit(), LABEL)
    assert "defect_evidence" not in {f["status"] for f in fx["findings"]}


def test_score_fixed_real_review_is_not_a_false_alarm():
    fx = rsa.score_fixed(_doc(), _audit(), LABEL, [], [_review("`stray` has no caller", "real")])
    assert fx["finding_counts"] == _fc(3, 0, 1, 0, 2)
    assert fx["false_alarms"] == 2
    assert fx["reviews_used"] == [["py-01-demo", "app.py", "`stray` has no caller"]]


def test_score_fixed_false_positive_review_still_a_false_alarm():
    fx = rsa.score_fixed(_doc(), _audit(), LABEL, [], [_review("`stray` has no caller")])
    assert fx["finding_counts"]["false_positive"] == 1
    assert fx["false_alarms"] == 3


def test_score_fixed_review_can_mark_still_reported_finding_real():
    fx = rsa.score_fixed(_doc(), _audit(), LABEL, [],
                         [_review("`transfer` can cause integer overflow", "real")])
    assert fx["still_reported"] == ["PY01-D01"]
    assert fx["false_alarms"] == 2


def test_score_fixed_honours_not_category_evidence():
    adj = [{"defect": "PY01-D01", "verdict": "not_category_evidence",
            "finding_contains": "integer overflow", "reason": "x"}]
    fx = rsa.score_fixed(_doc(), _audit(), LABEL, adj)
    assert fx["still_reported"] == []
    assert "PY01-D01" in fx["still_function_flagged"]


def test_score_fixed_clean_audit():
    fx = rsa.score_fixed(_doc(), {"file_results": [{"source_file": f"{LABEL}/app.py"}]}, LABEL)
    assert fx["still_reported"] == [] and fx["still_function_flagged"] == []
    assert fx["finding_counts"] == _fc(0, 0, 0, 0, 0)
    assert fx["false_alarms"] == 0


def test_score_fixed_reviews_scoped_to_specimen():
    fx = rsa.score_fixed(_doc(), _audit(), LABEL, [],
                         [_review("`stray` has no caller", "real", specimen="py-02-other")])
    assert fx["finding_counts"]["real"] == 0


def _fixed(defects=4, still=("PY01-D01",), fc=None, false_alarms=None):
    fc = fc or _fc(3, 0, 1, 0, 2)
    return {"defects": defects, "still_reported": list(still), "still_function_flagged": [],
            "finding_counts": fc, "findings": [], "reviews_used": [],
            "false_alarms": fc["total"] - fc["real"] if false_alarms is None else false_alarms}


def test_aggregate_fixed_totals():
    a = {**_coverage("py-01-a", "python", []), "fixed": _fixed()}
    b = {**_coverage("ts-01-b", "typescript", []),
         "fixed": _fixed(defects=2, still=(), fc=_fc(1, 0, 0, 0, 1))}
    plain = _coverage("go-01-c", "go", [])
    fx = rsa.aggregate([a, b, plain])["fixed"]
    assert fx == {"specimens": 2, "defects": 6, "still_reported": 1, "findings": 4,
                  "real": 1, "false_alarms": 3}


def test_aggregate_fixed_empty():
    fx = rsa.aggregate([_coverage("go-01-c", "go", [])])["fixed"]
    assert fx["specimens"] == 0 and fx["false_alarms"] == 0


def test_write_summary_fixed_section(tmp_path):
    cov = {**_coverage("py-01-a", "python", []), "finding_counts": _fc(0, 0, 0, 0, 0),
           "findings": [], "fixed": _fixed()}
    plain = {**_coverage("go-01-c", "go", []), "finding_counts": _fc(0, 0, 0, 0, 0), "findings": []}
    out = tmp_path / "AUDIT_SUMMARY.md"
    rsa.write_summary([cov, plain], _summary_meta(), out)
    text = out.read_text()
    assert "## Fixed variants" in text
    assert "(python/py-01-a/audit/fixed/audit.md) | 4 | 3 | 1 | 2 | PY01-D01 |" in text
    assert "Fixed variants: 1 of 2 specimens; 2 false alarms on fixed code." in text
    assert "go-01-c" not in text.split("## Fixed variants")[1].split("## Per language")[0]


def test_write_summary_without_fixed_has_no_fixed_table(tmp_path):
    cov = {**_coverage("py-01-a", "python", []), "finding_counts": _fc(0, 0, 0, 0, 0), "findings": []}
    out = tmp_path / "AUDIT_SUMMARY.md"
    rsa.write_summary([cov], _summary_meta(), out)
    assert "## Fixed variants" not in out.read_text()


def test_history_entry_fixed_only_when_present():
    corpus = {"specimens": 1, "defects": 0, "hash": "h"}
    cov = {**_coverage("py-01-a", "python", []), "fixed": _fixed()}
    entry = rsa.history_entry([cov], _summary_meta(), corpus, "s")
    assert entry["fixed"]["specimens"] == 1 and entry["fixed"]["false_alarms"] == 2
    plain = rsa.history_entry([_coverage("py-01-a", "python", [])], _summary_meta(), corpus, "s")
    assert "fixed" not in plain


def test_stale_reviews_counts_fixed_variant_usage():
    key = ["py-01-a", "app.py", "only on fixed"]
    cov = {**_coverage("py-01-a", "python", []), "reviews_used": [],
           "fixed": {**_fixed(), "reviews_used": [key]}}
    review = _review("only on fixed", specimen="py-01-a")
    assert rsa.stale_reviews([cov], [review]) == []
    assert rsa.stale_reviews([_coverage("py-01-a", "python", [])], [review]) == [review]


def test_fmt_fixed():
    assert rsa.fmt_fixed(None) == "—"
    assert rsa.fmt_fixed({"false_alarms": 5, "specimens": 7}) == "5 / 7 specimens"


def test_readme_blocks_show_fixed_variants():
    old = _run(date="2025-01-01", llm=False)
    new = {**_run(date="2025-01-02", llm=False),
           "fixed": {"specimens": 7, "defects": 70, "still_reported": 2, "findings": 9,
                     "real": 1, "false_alarms": 8}}
    spec = rsa.readme_block_specimens({"schema": 2, "runs": [old, new]})
    assert "| False alarms on fixed code |" in spec
    assert "| 8 / 7 specimens |" in spec
    assert "Fixed variants — no LLM: 7 specimens (70 defects fixed)" in spec
    assert "8 false alarms in 9 findings on fixed code" in spec
    old_row = [ln for ln in spec.splitlines() if ln.startswith("| 2025-01-01")][0]
    assert old_row.endswith("| — |")
    top = rsa.readme_block_top({"schema": 2, "runs": [old, new]})
    assert "8 false alarms on fixed code (7 specimens)" in top


def test_readme_block_top_omits_fixed_for_runs_without_it():
    assert "fixed code" not in rsa.readme_block_top({"schema": 2, "runs": [_run(llm=False)]})


def _write_fixed_audit(d, violations):
    (d / "fixed.patch").write_text("x")
    (d / "audit" / "fixed").mkdir(parents=True, exist_ok=True)
    (d / "audit" / "fixed" / "audit.json").write_text(json.dumps({"file_results": [{
        "source_file": "specimens/python/py-01-x/app.py",
        "verification_violations": violations,
    }]}))


def test_rescore_specimen_scores_fixed_audit(tmp_path, monkeypatch):
    _, d = _rescore_tree(tmp_path, monkeypatch)
    _write_fixed_audit(d, ["Python function `f` returns a constant"])
    cov = rsa.rescore_specimen(d, [], [])
    assert cov["fixed"]["finding_counts"]["total"] == 1
    assert cov["fixed"]["false_alarms"] == 1
    written = json.loads((d / "audit" / "coverage.json").read_text())
    assert "fixed" not in written  # rescore_specimen never writes


def test_rescore_specimen_requires_fixed_audit_when_patch_exists(tmp_path, monkeypatch):
    _, d = _rescore_tree(tmp_path, monkeypatch)
    (d / "fixed.patch").write_text("x")
    with pytest.raises(SystemExit, match="no audit/fixed/audit.json"):
        rsa.rescore_specimen(d, [], [])


def test_rescore_specimen_without_patch_has_no_fixed(tmp_path, monkeypatch):
    _, d = _rescore_tree(tmp_path, monkeypatch)
    assert "fixed" not in rsa.rescore_specimen(d, [], [])


def test_main_rescore_records_fixed_and_review_used_only_on_fixed(tmp_path, monkeypatch, capsys):
    specimens, d = _rescore_tree(tmp_path, monkeypatch)
    _write_fixed_audit(d, ["Python function `h` is reported only after the patch"])
    _write_finding_reviews(specimens, [
        _review("only after the patch", "real", specimen="py-01-x"),
    ])
    assert rsa.main(_rescore_args(tmp_path)) == 0
    assert "stale finding review" not in capsys.readouterr().err
    run = json.loads((specimens / "scoreboard" / "history.json").read_text())["runs"][-1]
    assert run["fixed"] == {"specimens": 1, "defects": 1, "still_reported": 0, "findings": 1,
                            "real": 1, "false_alarms": 0}
    assert "## Fixed variants" in (tmp_path / "AUDIT_SUMMARY.md").read_text()
    assert "0 false alarms on fixed code (1 specimens)" in (tmp_path / "README.md").read_text()


# --- fixed variant audit plumbing -------------------------------------------

def _git_specimen(tmp_path, monkeypatch, patch: str | None):
    import subprocess as sp
    specimens = tmp_path / "specimens"
    d = _mini_specimen(specimens)
    if patch is not None:
        (d / "fixed.patch").write_text(patch)
    sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    sp.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    monkeypatch.setattr(rsa, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rsa, "SPECIMENS_ROOT", specimens)
    return d


MINI_FIX = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def f():
-    return 1
+    return 2
"""


def test_audit_files_excludes_fixed_patch(tmp_path, monkeypatch):
    d = _git_specimen(tmp_path, monkeypatch, MINI_FIX)
    names = {f.relative_to(d).as_posix() for f in rsa.audit_files(d)}
    assert names == {"DEFECTS.json", "app.py"}
    assert "fixed.patch" in {f.name for f in rsa.tracked_files(d)}


def test_apply_fixed_patch(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    (work / "app.py").write_text("def f():\n    return 1\n")
    patch = tmp_path / "fixed.patch"
    patch.write_text(MINI_FIX)
    rsa.apply_fixed_patch(patch, work)
    assert "return 2" in (work / "app.py").read_text()


def test_apply_fixed_patch_failure(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    (work / "app.py").write_text("def f():\n    return 9\n")
    patch = tmp_path / "fixed.patch"
    patch.write_text(MINI_FIX)
    with pytest.raises(SystemExit, match="does not apply"):
        rsa.apply_fixed_patch(patch, work)


def _fake_run_audit(seen):
    def fake(agent_repo, mumei_bin, target, fmt, timeout):
        src = (target / "app.py").read_text()
        seen.append((fmt, "return 2" in src, (target / "fixed.patch").exists()))
        text = ("Python function `f` returns a constant" if "return 1" in src
                else "Python function `f` is reported after the patch")
        if fmt == "markdown":
            return 0, f"# report for {target}\n{text}\n", ""
        return 0, json.dumps({"file_results": [{"source_file": f"{target}/app.py",
                                                "verification_violations": [text]}]}), ""
    return fake


def test_audit_specimen_audits_original_and_fixed(tmp_path, monkeypatch):
    d = _git_specimen(tmp_path, monkeypatch, MINI_FIX)
    seen = []
    monkeypatch.setattr(rsa, "run_audit", _fake_run_audit(seen))
    cov = rsa.audit_specimen(d, tmp_path, "mumei", 5, RESCORE_META)
    assert seen == [("json", False, False), ("markdown", False, False),
                    ("json", True, False), ("markdown", True, False)]
    assert cov["finding_counts"]["total"] == 1
    assert cov["fixed"]["finding_counts"]["total"] == 1
    assert cov["fixed"]["false_alarms"] == 1
    fixed_json = json.loads((d / "audit" / "fixed" / "audit.json").read_text())
    assert fixed_json["file_results"][0]["source_file"] == "specimens/python/py-01-x/app.py"
    md = (d / "audit" / "fixed" / "audit.md").read_text()
    assert "specimens/python/py-01-x" in md and str(tmp_path / "w") not in md
    assert "return 1" in (d / "app.py").read_text()


def test_audit_specimen_without_patch_skips_fixed(tmp_path, monkeypatch):
    d = _git_specimen(tmp_path, monkeypatch, None)
    seen = []
    monkeypatch.setattr(rsa, "run_audit", _fake_run_audit(seen))
    cov = rsa.audit_specimen(d, tmp_path, "mumei", 5, RESCORE_META)
    assert len(seen) == 2 and "fixed" not in cov
    assert not (d / "audit" / "fixed").exists()


def test_audit_specimen_fixed_audit_failure_is_fatal(tmp_path, monkeypatch):
    d = _git_specimen(tmp_path, monkeypatch, MINI_FIX)
    good = _fake_run_audit([])

    def flaky(agent_repo, mumei_bin, target, fmt, timeout):
        if "return 2" in (target / "app.py").read_text():
            return 2, "", "boom"
        return good(agent_repo, mumei_bin, target, fmt, timeout)
    monkeypatch.setattr(rsa, "run_audit", flaky)
    with pytest.raises(SystemExit, match=r"\(fixed\)"):
        rsa.audit_specimen(d, tmp_path, "mumei", 5, RESCORE_META)


def test_write_summary_lists_findings_on_fixed_code(tmp_path):
    fx = {**_fixed(), "findings": [
        {"file": "app.py", "kind": "verification_violations", "text": "g | still flagged",
         "status": "unreviewed"},
        {"file": "app.py", "kind": "verification_violations", "text": "h race", "status": "real"},
        {"file": "app.py", "kind": "verification_violations", "text": "k odd",
         "status": "false_positive"},
    ]}
    cov = {**_coverage("py-01-a", "python", []), "finding_counts": _fc(0, 0, 0, 0, 0),
           "findings": [], "fixed": fx}
    out = tmp_path / "AUDIT_SUMMARY.md"
    rsa.write_summary([cov], _summary_meta(), out)
    text = out.read_text()
    assert "| py-01-a | `app.py` | false alarm | g \\| still flagged |" in text
    assert "| py-01-a | `app.py` | real | h race |" in text
    assert "| py-01-a | `app.py` | false alarm | k odd |" in text


def test_write_summary_fixed_without_findings_has_no_finding_table(tmp_path):
    cov = {**_coverage("py-01-a", "python", []), "finding_counts": _fc(0, 0, 0, 0, 0),
           "findings": [], "fixed": _fixed(fc=_fc(0, 0, 0, 0, 0))}
    out = tmp_path / "AUDIT_SUMMARY.md"
    rsa.write_summary([cov], _summary_meta(), out)
    assert "Finding on fixed code" not in out.read_text()


def test_rescore_refuses_after_fixed_patch_changes(tmp_path, monkeypatch):
    _, d = _rescore_tree(tmp_path, monkeypatch)
    (d / "fixed.patch").write_text(MINI_FIX)
    _git_track(tmp_path)
    (d / "audit" / "fixed").mkdir()
    (d / "audit" / "fixed" / "audit.json").write_text(json.dumps({"file_results": []}))
    cov_path = d / "audit" / "coverage.json"
    cov_path.write_text(json.dumps({**json.loads(cov_path.read_text()),
                                    "source_hash": rsa.specimen_hash(d)}))
    rsa.rescore_specimen(d, [], [])
    (d / "fixed.patch").write_text(MINI_FIX.replace("return 2", "return 3"))
    with pytest.raises(SystemExit, match="changed since the audit"):
        rsa.rescore_specimen(d, [], [])
