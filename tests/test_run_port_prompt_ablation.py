import copy
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
    with pytest.raises(SystemExit, match="invalid prompt input"):
        ablation.load_prompts(prompt_file(tmp_path, [
            {"label": "baseline"}, {"label": "candidate", "text": "x"}]))


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
    with pytest.raises(SystemExit, match="canonical proofs tree"):
        ablation.validate_output_dir(str(ablation.REPO_ROOT / "proofs" / "new-analysis"))


def test_harness_writes_only_output_dir_and_records_gate_projection(tmp_path, monkeypatch):
    candidate_text = "candidate prompt text"
    seen = []

    def fake_case(case, provider, arm, seed, mumei_bin, timeout, write_certificates=True):
        seen.append((case["id"], seed, cb.PORT_SYSTEM, case["dir"]))
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
    assert all(Path(entry[3]).is_absolute() and Path(entry[3]).is_relative_to(outdir) for entry in seen)
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
    assert "Certificates: not collected / screening only" in report
    assert "| PY02-D04 | buggy | proven | inconclusive | blocked | success_flag_rewrite |" in report
    assert json.loads((outdir / "results.json").read_text())["schema"] == ablation.SCHEMA


def test_real_case_runner_certificate_write_stays_in_redirected_sandbox(tmp_path, monkeypatch):
    case = copy.deepcopy(next(c for c in cb.load_cases()[0] if c["id"] == "PY02-D04"))
    target = tmp_path / "sandbox"
    target.mkdir()
    (target / "replay.json").write_bytes((ablation.REPO_ROOT / case["dir"] / "replay.json").read_bytes())
    original_dir = case["dir"]
    case["dir"] = str(target)

    monkeypatch.setattr(cb, "verify_text", lambda *a: {"outcome": "proven", "status": "success"})
    monkeypatch.setattr(cb, "apply_port_fidelity_gate", lambda case, body, result, mumei_bin, timeout, variant: result)
    monkeypatch.setattr(cb, "certify", lambda *a, **k: ({"status": "recorded"}, "certificate text"))

    class Provider:
        model = "openai/gpt-6-luna"

        def complete(self, prompt, seed):
            return '{"body": "0"}', {"prompt_tokens": 1, "completion_tokens": 1, "cost_usd": None, "seconds": 0, "attempts": 1}

    cert_rel = cb.llm_cert_file(Provider.model, 0)
    canonical_path = ablation.REPO_ROOT / original_dir / cert_rel
    canonical_before = canonical_path.read_bytes()

    result = cb.run_llm_case(case, Provider(), "mumei-llm", 0, "mumei", 5)

    assert result["fixed"]["outcome"] == "proven"
    assert (target / cert_rel).read_text() == "certificate text"
    assert canonical_path.read_bytes() == canonical_before


def test_harness_real_runner_does_not_unlink_or_write_repo_certificate(tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "verify_text", lambda *a: {"outcome": "proven", "status": "success"})
    monkeypatch.setattr(cb, "apply_port_fidelity_gate", lambda case, body, result, mumei_bin, timeout, variant: result)

    def certify_must_not_run(*args, **kwargs):
        pytest.fail("certificate generation must be disabled for screening")

    monkeypatch.setattr(cb, "certify", certify_must_not_run)

    class Provider:
        model = "openai/gpt-6-luna"

        def complete(self, prompt, seed):
            return '{"body": "0"}', {"prompt_tokens": 1, "completion_tokens": 1, "cost_usd": None, "seconds": 0, "attempts": 1}

    original_case = next(c for c in cb.load_cases()[0] if c["id"] == "PY02-D04")
    cert_rel = cb.llm_cert_file(Provider.model, 0)
    canonical_path = ablation.REPO_ROOT / original_case["dir"] / cert_rel
    canonical_before = canonical_path.read_bytes()
    status_before = subprocess.run(["git", "status", "--porcelain"], cwd=ablation.REPO_ROOT,
                                   capture_output=True, text=True, check=True).stdout
    prompts = prompt_file(tmp_path, [{"label": "baseline", "text": None}, {"label": "candidate", "text": "x"}])
    args = Namespace(prompts=prompts, output_dir=str(tmp_path / "out"), cases="PY02-D04", runs=1, jobs=1,
                     timeout=5, mumei_bin="mumei", model=Provider.model)

    doc = ablation.run(args, Provider())

    assert canonical_path.read_bytes() == canonical_before
    assert subprocess.run(["git", "status", "--porcelain"], cwd=ablation.REPO_ROOT,
                          capture_output=True, text=True, check=True).stdout == status_before
    assert doc["certificate_collection"] == "not collected / screening only"
    fixed = doc["prompts"][0]["runs"][0]["records"][0]["fixed"]
    assert fixed["raw_outcome"] == "proven"
    assert fixed["certificate_status"] == "not collected / screening only"


def test_unknown_case_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "run_llm_case", lambda *a: pytest.fail("must not run"))
    prompts = prompt_file(tmp_path, [{"label": "baseline", "text": None}, {"label": "candidate", "text": "x"}])
    args = Namespace(prompts=prompts, output_dir=str(tmp_path / "out"), cases="NO-SUCH", runs=1, jobs=1,
                     timeout=5, mumei_bin="mumei", model="gpt-4o")
    with pytest.raises(SystemExit, match="unknown case ids"):
        ablation.run(args, object())


def test_nonpositive_run_or_job_counts_fail_closed(tmp_path):
    prompts = prompt_file(tmp_path, [{"label": "baseline", "text": None}, {"label": "candidate", "text": "x"}])
    args = Namespace(prompts=prompts, output_dir=str(tmp_path / "out"), cases="PY02-D04", runs=0, jobs=1,
                     timeout=5, mumei_bin="mumei", model="gpt-4o")
    with pytest.raises(SystemExit, match="runs and jobs must be positive"):
        ablation.run(args, object())
