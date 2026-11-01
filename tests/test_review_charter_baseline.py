from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from review_charter_baseline import PATHS, review


@pytest.fixture
def baseline_repo(tmp_path):
    root = tmp_path / "repo"
    source = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["git", "clone", "--shared", "--no-checkout", "--quiet", str(source), str(root)],
        check=True, capture_output=True,
    )
    subprocess.run(["git", "read-tree", "HEAD"], cwd=root, check=True, capture_output=True)
    for name in PATHS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, path)
    return root


@pytest.mark.parametrize("name", PATHS)
def test_review_diff_exposes_each_reviewed_input_change(baseline_repo, tmp_path, name):
    path = baseline_repo / name
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        data["evidence_requirements"]["claims"][0]["minimum_grade"] = "G0"
        path.write_text(json.dumps(data, indent=2))
    else:
        path.write_text(path.read_text() + "\n# deliberate baseline edit\n")
    output = tmp_path / "review"
    snapshot = review(baseline_repo, "HEAD", output)
    assert snapshot["comparison"] == "changed"
    assert snapshot["review_required"] is True
    diff = (output / "baseline.diff").read_text()
    assert name in diff
    assert "+" in diff
    assert str(tmp_path) not in (output / "baseline.json").read_text()


def test_unchanged_comparison_is_not_an_approval(baseline_repo, tmp_path):
    output = tmp_path / "review"
    snapshot = review(baseline_repo, "HEAD", output)
    assert snapshot["comparison"] == "unchanged"
    assert snapshot["review_required"] is True
    assert (output / "baseline.diff").read_text() == ""
    assert "not approval" in (output / "review.md").read_text()


def test_snapshot_without_base_does_not_claim_unchanged(baseline_repo, tmp_path):
    output = tmp_path / "review"
    snapshot = review(baseline_repo, None, output)
    assert snapshot["comparison"] == "not_requested"
    assert "not a change comparison" in (output / "baseline.diff").read_text()


@pytest.mark.parametrize("base", ["nonexistent-ref", "--output=/tmp/not-a-ref"])
def test_bad_base_fails_instead_of_hiding_a_diff(baseline_repo, tmp_path, base):
    with pytest.raises(subprocess.CalledProcessError):
        review(baseline_repo, base, tmp_path / "review")
    assert not (tmp_path / "review" / "baseline.json").exists()


def test_review_is_stable_and_does_not_write_the_reviewed_inputs(baseline_repo, tmp_path):
    before = {name: (baseline_repo / name).read_bytes() for name in PATHS}
    first, second = tmp_path / "first", tmp_path / "second"
    review(baseline_repo, "HEAD", first)
    review(baseline_repo, "HEAD", second)
    for name in ("baseline.json", "baseline.diff", "review.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert before == {name: (baseline_repo / name).read_bytes() for name in PATHS}


def test_missing_reviewed_input_fails(baseline_repo, tmp_path):
    (baseline_repo / PATHS[0]).unlink()
    with pytest.raises(OSError):
        review(baseline_repo, "HEAD", tmp_path / "review")
