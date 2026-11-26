from __future__ import annotations

import json

from scripts import recheck_lean_dual_checks as recheck


def test_refresh_results_replaces_dual_checks_and_preserves_z3(tmp_path, monkeypatch):
    case = {"id": "TS01-D04", "atom": "completionPercent", "dir": "proofs/ts/ts01/TS01-D04"}
    cert = tmp_path / "proofs" / "ts" / "ts01" / "TS01-D04" / recheck.cb.CERT_FILE
    cert.parent.mkdir(parents=True)
    cert.write_text('{"certificate": true}')
    results = tmp_path / "mumei.json"
    results.write_text(json.dumps({
        "runs": [[{"id": "TS01-D04", "fixed": {"outcome": "proven", "lean_dual_check": {"status": "failed"}}}]],
    }))
    monkeypatch.setattr(recheck.cb, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(recheck.cb, "lake_on_path", lambda: True)
    monkeypatch.setattr(recheck.cb, "load_cases", lambda: ([case], []))
    monkeypatch.setattr(recheck.cb, "lean_dual_check", lambda *args: {"status": "lean_verified"})
    monkeypatch.setattr(recheck.cb, "git_identity", lambda _: {"commit": "abcdef", "dirty": False})

    refreshed = recheck.refresh_results(tmp_path / "lean", 5, results)
    record = json.loads(results.read_text())["runs"][0][0]
    assert refreshed["checks"] == [{"id": "TS01-D04", "atom": "completionPercent", "status": "lean_verified"}]
    assert record["fixed"]["outcome"] == "proven"
    assert record["fixed"]["lean_dual_check"] == {"status": "lean_verified"}


def test_missing_certificate_is_unsupported_not_success(tmp_path, monkeypatch):
    case = {"id": "X", "atom": "target", "dir": "proofs/x/x/X"}
    results = tmp_path / "mumei.json"
    results.write_text(json.dumps({"runs": [[{"id": "X", "fixed": {"lean_dual_check": {"status": "lean_verified"}}}]]}))
    monkeypatch.setattr(recheck.cb, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(recheck.cb, "lake_on_path", lambda: True)
    monkeypatch.setattr(recheck.cb, "load_cases", lambda: ([case], []))
    monkeypatch.setattr(recheck.cb, "git_identity", lambda _: {"commit": "abcdef", "dirty": False})

    recheck.refresh_results(tmp_path / "lean", 5, results)
    record = json.loads(results.read_text())["runs"][0][0]
    assert record["fixed"]["lean_dual_check"]["status"] == "unsupported"
    assert json.loads(results.read_text())["lean_dual_recheck"]["counts"] == {"unsupported": 1}


def test_missing_lake_is_environment_failure_not_a_measurement(tmp_path, monkeypatch):
    monkeypatch.setattr(recheck.cb, "lake_on_path", lambda: False)
    try:
        recheck.refresh_results(tmp_path / "lean", 5, tmp_path / "mumei.json")
    except ValueError as exc:
        assert "environment_failure" in str(exc)
        assert "no dual-check result was measured" in str(exc)
    else:
        raise AssertionError("missing lake must fail before rewriting measurements")
