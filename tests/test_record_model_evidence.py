from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import record_model_evidence as collector


@pytest.fixture
def model_repo(tmp_path):
    repo, output = tmp_path / "repo", tmp_path / "out"
    for name in collector.INPUTS:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    (repo / collector.INPUTS[0]).write_text("theorem property : True := trivial\n")
    (repo / collector.INPUTS[1]).write_text("theorem example : True := trivial\n")
    return repo, output


def fake_gate(monkeypatch, repo, output, change=None, exit_code=0):
    audit = {"MumeiLean.AuthorizationModel.property": {"status": "passed", "axioms": [], "disallowed": []},
             "MumeiLean.AuthorizationExamples.example": {"status": "passed", "axioms": ["propext"], "disallowed": []}}

    def run(command, **kwargs):
        assert command[1] == str(repo / "scripts/check_authorization_model.py")
        assert kwargs["cwd"] == repo and kwargs["timeout"] == 900 and kwargs["check"] is False
        if change:
            change(audit)
        (output / "audit/axiom_audit.json").write_text(json.dumps(audit))
        return subprocess.CompletedProcess(command, exit_code, "gate result\n", "")

    monkeypatch.setattr(collector.subprocess, "run", run)


def test_fresh_complete_model_audit_is_required(model_repo, monkeypatch):
    repo, output = model_repo
    fake_gate(monkeypatch, repo, output)
    assert collector.collect(repo, output)
    report = json.loads((output / "model.json").read_text())
    assert report["status"] == "passed" and len(report["inputs"]) == len(collector.INPUTS)
    assert len(report["theorems"]) == 2
    assert (output / "source" / collector.INPUTS[0]).read_bytes() == (repo / collector.INPUTS[0]).read_bytes()


@pytest.mark.parametrize("failure", ["build", "missing", "extra", "axiom", "rejected", "changed_source", "bad_json", "timeout", "missing_tool"])
def test_failed_audit_never_reuses_a_previously_successful_report(model_repo, monkeypatch, failure):
    repo, output = model_repo
    fake_gate(monkeypatch, repo, output)
    assert collector.collect(repo, output)

    def corrupt(audit):
        name = next(iter(audit))
        if failure == "missing":
            audit.pop(name)
        elif failure == "extra":
            audit["unexpected"] = audit[name]
        elif failure == "axiom":
            audit[name]["axioms"] = ["sorryAx"]
        elif failure == "rejected":
            audit[name]["status"] = "rejected"
        elif failure == "changed_source":
            (repo / collector.INPUTS[0]).write_text("changed while auditing")

    fake_gate(monkeypatch, repo, output, change=corrupt, exit_code=int(failure == "build"))
    if failure in {"bad_json", "timeout", "missing_tool"}:
        def fail(*args, **kwargs):
            if failure == "timeout":
                raise subprocess.TimeoutExpired(args[0], 900)
            if failure == "missing_tool":
                raise OSError("missing")
            (output / "audit/axiom_audit.json").write_text("not JSON")
            return subprocess.CompletedProcess(args[0], 0, "", "")
        monkeypatch.setattr(collector.subprocess, "run", fail)
    assert not collector.collect(repo, output)
    assert json.loads((output / "model.json").read_text())["status"] == "error"


def test_missing_source_fails_closed_without_retaining_pass(tmp_path):
    output = tmp_path / "out"
    assert not collector.collect(tmp_path / "missing", output)
    assert json.loads((output / "model.json").read_text())["status"] == "error"
