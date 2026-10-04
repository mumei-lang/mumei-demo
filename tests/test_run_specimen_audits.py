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
         tgt_total=5, tgt_det=2):
    return {
        "generated_at": f"{date}T00:00:00Z",
        "mumei_agent_commit": agent,
        "mumei_commit": mumei,
        "mumei_version": "mumei 0.1",
        "llm_configured": True,
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
    svg = rsa.svg_by_language(None)
    root = _parse(svg)
    assert "No benchmark runs yet" in ET.tostring(root, encoding="unicode")
    run = _run()
    svg = rsa.svg_by_language(run)
    root = _parse(svg)
    text = ET.tostring(root, encoding="unicode")
    assert "Specimen benchmark — detection by language" in text
    assert "aaaaaaa" in text  # sha7 subtitle
    assert "python" in text and "rust" in text and "overall" in text
    assert "2/6 · 33%" in text  # detected bar label
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
    assert "3/10 defects detected" in top_text
