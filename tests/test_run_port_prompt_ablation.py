import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_contract_bench as cb  # noqa: E402
import run_port_prompt_ablation as ablation  # noqa: E402


def prompt_file(tmp_path, rows):
    path = tmp_path / "prompts.json"
    path.write_text(json.dumps({"prompts": rows}))
    return str(path)


def test_prompt_input_rejects_malformed_shape(tmp_path):
    with pytest.raises(SystemExit, match="invalid prompt input"):
        ablation.load_prompts(prompt_file(tmp_path, [{"label": "baseline", "text": None}]))
    with pytest.raises(SystemExit, match="invalid prompt input"):
        ablation.load_prompts(prompt_file(tmp_path, [
            {"label": "baseline", "text": None}, {"label": "bad label", "text": "x"}]))
    with pytest.raises(SystemExit, match="invalid prompt input"):
        ablation.load_prompts(prompt_file(tmp_path, [
            {"label": "baseline", "text": None}, {"label": "empty", "text": "  "}]))


def test_prompt_input_requires_exactly_one_baseline_and_unique_labels(tmp_path):
    rows = [{"label": "one", "text": "a"}, {"label": "two", "text": "b"}]
    with pytest.raises(SystemExit, match="exactly one baseline"):
        ablation.load_prompts(prompt_file(tmp_path, rows))
    rows = [{"label": "same", "text": None}, {"label": "same", "text": "b"}]
    with pytest.raises(SystemExit, match="exactly one baseline"):
        ablation.load_prompts(prompt_file(tmp_path, rows))


def test_output_dir_rejects_canonical_results_tree(tmp_path):
    with pytest.raises(SystemExit, match="canonical benchmark results"):
        ablation.validate_output_dir(str(ablation.REPO_ROOT / "proofs" / "results" / "analysis"))


def test_harness_writes_only_output_dir_and_records_gate_projection(tmp_path, monkeypatch):
    candidate_text = "candidate prompt text"
    seen = []

    def fake_case(case, provider, arm, seed, mumei_bin, timeout):
        seen.append((case["id"], seed, cb.PORT_SYSTEM))
        raw = "proven" if cb.PORT_SYSTEM == candidate_text else "refuted"
        buggy = {"outcome": raw, "status": "success", "usage": {"prompt_tokens": 3, "completion_tokens": 2,
               "cost_usd": None, "seconds": 0.1, "attempts": 1}}
        if raw == "proven":
            buggy["fidelity_gate"] = {"decision": "blocked", "lint_findings": [{"kind": "success_flag_rewrite"}],
                                      "semantic_replay": {"outcome": "diverged"},
                                      "output_equivalence": {"outcome": "diverged", "status": "failed"}}
        fixed = {"outcome": "proven", "status": "success", "usage": {"prompt_tokens": 4, "completion_tokens": 2,
                 "cost_usd": None, "seconds": 0.1, "attempts": 1}}
        return {"id": case["id"], "buggy": buggy, "fixed": fixed}

    monkeypatch.setattr(cb, "run_llm_case", fake_case)
    prompts = prompt_file(tmp_path, [
        {"label": "baseline", "text": None}, {"label": "candidate", "text": candidate_text}])
    outdir = tmp_path / "out"
    args = Namespace(prompts=prompts, output_dir=str(outdir), cases="PY02-D04", runs=2, jobs=1,
                     timeout=5, mumei_bin="mumei", model="gpt-4o")
    before = cb.PORT_SYSTEM
    canonical_before = (ablation.REPO_ROOT / "proofs/results/mumei-llm-openai__gpt-6-luna.json").read_bytes()
    status_before = subprocess.run(["git", "status", "--porcelain"], cwd=ablation.REPO_ROOT,
                                   capture_output=True, text=True, check=True).stdout

    doc = ablation.run(args, object())

    assert cb.PORT_SYSTEM == before
    assert (ablation.REPO_ROOT / "proofs/results/mumei-llm-openai__gpt-6-luna.json").read_bytes() == canonical_before
    assert subprocess.run(["git", "status", "--porcelain"], cwd=ablation.REPO_ROOT,
                          capture_output=True, text=True, check=True).stdout == status_before
    assert sorted(p.name for p in outdir.iterdir()) == ["report.md", "results.json"]
    assert doc["schema"] == ablation.SCHEMA
    assert doc["model"] == "gpt-4o"
    assert len(seen) == 4
    baseline = next(p for p in doc["prompts"] if p["label"] == "baseline")
    assert baseline["benchmark_hash"] == cb.prompt_hash("mumei-llm")
    candidate = next(p for p in doc["prompts"] if p["label"] == "candidate")
    assert candidate["benchmark_hash"] is None
    record = candidate["runs"][0]["records"][0]
    assert record["buggy"]["raw_outcome"] == "proven"
    assert record["buggy"]["post_gate_outcome"] == "inconclusive"
    assert record["buggy"]["gate_decision"] == "blocked"
    assert record["buggy"]["lint_kinds"] == ["success_flag_rewrite"]
    assert record["buggy"]["semantic_replay"]["outcome"] == "diverged"
    assert record["buggy"]["usage"]["prompt_tokens"] == 3
    assert candidate["runs"][0]["score"]["false_acceptance"] == 0
    assert candidate["runs"][0]["score"]["fidelity_blocked"] == 1
    report = (outdir / "report.md").read_text()
    assert "Screening only" in report
    assert "| PY02-D04 | buggy | proven | inconclusive | blocked | success_flag_rewrite |" in report
    assert json.loads((outdir / "results.json").read_text())["schema"] == ablation.SCHEMA


def test_unknown_case_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "run_llm_case", lambda *a: pytest.fail("must not run"))
    prompts = prompt_file(tmp_path, [{"label": "baseline", "text": None}, {"label": "candidate", "text": "x"}])
    args = Namespace(prompts=prompts, output_dir=str(tmp_path / "out"), cases="NO-SUCH", runs=1, jobs=1,
                     timeout=5, mumei_bin="mumei", model="gpt-4o")
    with pytest.raises(SystemExit, match="unknown case ids"):
        ablation.run(args, object())
