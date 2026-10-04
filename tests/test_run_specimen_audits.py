"""Unit tests for the pure functions in scripts/run_specimen_audits.py.

No subprocess or real audit calls: the module is imported by path and fed
hand-built defects docs / audit dicts.
"""

import importlib.util
import sys
from pathlib import Path

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


# --- advisory_functions ----------------------------------------------------

def test_advisory_functions_extracts_name():
    audit = {
        "next_steps": [
            {"action": "underspecified な意図を明文化（推測で補完しない）: withdraw.requires"},
            {"action": "plain advisory without a dotted name"},
            {"action": "another: Vault.deposit.ensures"},
        ]
    }
    assert rsa.advisory_functions(audit) == ["withdraw", "Vault.deposit"]


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
                ],
                "counterexample_values": [
                    {"function_name": "transfer", "counterexample": {"a": 1}}
                ],
            },
            {"source_file": "specimens/python/py-01-demo/other.py"},
        ],
        "next_steps": [
            {"action": "underspecified intent: cleanup.requires"},
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
    assert by_id["PY01-D03"]["status"] == "advisory_only"
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
        {"status": "advisory_only"},
        {"status": "missed"},
    ]
    assert rsa.counts(results) == {
        "total": 5, "detected": 2, "function_flagged": 1,
        "advisory_only": 1, "missed": 1,
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
            d("advisory_only", "error-handling"),
        ]),
    ]
    out = tmp_path / "AUDIT_SUMMARY.md"
    rsa.write_summary(coverages, meta, out)
    text = out.read_text()
    assert "| **Total** | **5** | **2** | **1** | **1** | **1** | **1/2** | **0** |" in text
    assert "| python | 3 | 2 (67%) | 2 (67%) | 1/1 (100%) |" in text
    assert "| rust | 2 | 0 (0%) | 1 (50%) | 0/1 (0%) |" in text
    assert "| [py-01-a](python/py-01-a/audit/audit.md) | 3 | 2 | 0 | 0 | 1 | 1/1 | 0 |" in text
