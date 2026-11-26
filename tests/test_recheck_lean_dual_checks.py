from __future__ import annotations

import json

import pytest

from scripts import recheck_lean_dual_checks as recheck


def fixture(tmp_path, cert_text: str = '{"certificate": true}', fixed_source: str = "atom target() -> i64\n"):
    case = {
        "id": "TS01-D04",
        "atom": "completionPercent",
        "dir": "proofs/ts/ts01/TS01-D04",
        "ports": {"fixed": fixed_source},
    }
    cert = tmp_path / case["dir"] / recheck.cb.CERT_FILE
    cert.parent.mkdir(parents=True)
    cert.write_text(cert_text)
    certificate = {
        "file": recheck.cb.CERT_FILE,
        "sha256": recheck.cb.sha256(cert_text),
        "port_sha256": recheck.cb.sha256(fixed_source),
    }
    results = tmp_path / "mumei.json"
    results.write_text(json.dumps({
        "arm": "mumei",
        "runs": [[{
            "id": case["id"],
            "fixed": {"outcome": "proven", "certificate": certificate, "lean_dual_check": {"status": "failed"}},
        }]],
    }))
    lean_dir = tmp_path / "lean"
    (lean_dir / "scripts").mkdir(parents=True)
    (lean_dir / "scripts" / "bridge.py").write_text("# bridge\n")
    return case, results, lean_dir


def common(monkeypatch, tmp_path, case):
    monkeypatch.setattr(recheck.cb, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(recheck.cb, "lake_on_path", lambda: True)
    monkeypatch.setattr(recheck.cb, "load_cases", lambda: ([case], []))
    monkeypatch.setattr(recheck.cb, "git_identity", lambda _: {"commit": "abcdef", "dirty": False})


def test_refresh_results_replaces_dual_checks_and_preserves_z3(tmp_path, monkeypatch):
    case, results, lean_dir = fixture(tmp_path)
    common(monkeypatch, tmp_path, case)
    monkeypatch.setattr(recheck.cb, "lean_dual_check", lambda *args: {"status": "failed", "error": "型不一致"})

    refreshed = recheck.refresh_results(lean_dir, 5, results)
    record = json.loads(results.read_text())["runs"][0][0]
    assert refreshed["checks"] == [{
        "id": "TS01-D04", "atom": "completionPercent", "status": "failed", "error": "型不一致",
    }]
    assert record["fixed"]["outcome"] == "proven"
    assert record["fixed"]["lean_dual_check"]["status"] == "failed"
    assert "型不一致" in results.read_text()
    assert "\\u578b" not in results.read_text()


def test_missing_certificate_is_unsupported_not_success(tmp_path, monkeypatch):
    case, results, lean_dir = fixture(tmp_path)
    (tmp_path / case["dir"] / recheck.cb.CERT_FILE).unlink()
    common(monkeypatch, tmp_path, case)

    recheck.refresh_results(lean_dir, 5, results)
    record = json.loads(results.read_text())["runs"][0][0]
    assert record["fixed"]["lean_dual_check"]["status"] == "unsupported"
    assert json.loads(results.read_text())["lean_dual_recheck"]["counts"] == {"unsupported": 1}


def test_missing_lake_is_environment_failure_not_a_measurement(tmp_path, monkeypatch):
    monkeypatch.setattr(recheck.cb, "lake_on_path", lambda: False)
    with pytest.raises(ValueError, match="environment_failure: lake is not on PATH"):
        recheck.refresh_results(tmp_path / "lean", 5, tmp_path / "mumei.json")


def test_missing_bridge_is_environment_failure_before_rewriting(tmp_path, monkeypatch):
    case, results, _ = fixture(tmp_path)
    common(monkeypatch, tmp_path, case)
    original = results.read_text()

    with pytest.raises(ValueError, match="mumei-lean bridge is not available"):
        recheck.refresh_results(tmp_path / "not-a-lean-checkout", 5, results)
    assert results.read_text() == original


def test_non_reference_results_are_rejected_before_rewriting(tmp_path, monkeypatch):
    case, results, lean_dir = fixture(tmp_path)
    doc = json.loads(results.read_text())
    doc["arm"] = "mumei-llm"
    results.write_text(json.dumps(doc))
    common(monkeypatch, tmp_path, case)
    original = results.read_text()

    with pytest.raises(ValueError, match="reference-port mumei arm"):
        recheck.refresh_results(lean_dir, 5, results)
    assert results.read_text() == original


def test_stale_certificate_hash_is_not_rechecked(tmp_path, monkeypatch):
    case, results, lean_dir = fixture(tmp_path)
    doc = json.loads(results.read_text())
    doc["runs"][0][0]["fixed"]["certificate"]["sha256"] = "0" * 64
    results.write_text(json.dumps(doc))
    common(monkeypatch, tmp_path, case)

    def unexpected_call(*args):
        raise AssertionError("stale certificates must not be treated as the recorded proof")

    monkeypatch.setattr(recheck.cb, "lean_dual_check", unexpected_call)
    recheck.refresh_results(lean_dir, 5, results)
    outcome = json.loads(results.read_text())["runs"][0][0]["fixed"]["lean_dual_check"]
    assert outcome["status"] == "stale"
    assert "hash does not match" in outcome["reason"]


def test_results_file_is_written_as_utf8(tmp_path, monkeypatch):
    from pathlib import Path

    case, results, lean_dir = fixture(tmp_path)
    common(monkeypatch, tmp_path, case)
    monkeypatch.setattr(recheck.cb, "lean_dual_check", lambda *args: {"status": "failed", "error": "型不一致"})
    writes = []
    original_write_text = Path.write_text

    def recording_write_text(self, data, *args, **kwargs):
        if self == results:
            writes.append(kwargs.get("encoding"))
            return len(data)
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", recording_write_text)
    recheck.refresh_results(lean_dir, 5, results)
    assert writes == ["utf-8"]
