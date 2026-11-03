import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compare_arms as ca  # noqa: E402
import run_llm_only as rlo  # noqa: E402
import run_specimen_audits as rsa  # noqa: E402

MODEL = "openai/test-model"
FC0 = {"total": 0, "defect_evidence": 0, "real": 0, "false_positive": 0, "unreviewed": 0}


def _fc(total=0, ev=0, real=0, fp=0, unrev=0):
    return {"total": total, "defect_evidence": ev, "real": real, "false_positive": fp, "unreviewed": unrev}


def _defects(statuses):
    return [{"id": f"D{i}", "status": s} for i, s in enumerate(statuses, 1)]


def _specimen(root, lang, name, n=3, fixed=True):
    d = root / lang / name
    d.mkdir(parents=True)
    (d / "DEFECTS.json").write_text(json.dumps(
        {"specimen": name, "language": lang, "defects": [{"id": f"D{i}"} for i in range(1, n + 1)]}))
    return d


def _coverage(d, statuses, llm=False, fc=None, fa=1, meta=None):
    doc = json.loads((d / "DEFECTS.json").read_text())
    out = rsa.audit_dir(d, llm)
    out.mkdir(parents=True, exist_ok=True)
    cov = {"specimen": doc["specimen"], "language": doc["language"], "defects": _defects(statuses),
           "finding_counts": fc or _fc(), "meta": meta or {"llm_configured": llm, "llm": llm},
           "fixed": {"false_alarms": fa}}
    (out / "coverage.json").write_text(json.dumps(cov))


def _llm_record(d, runs, fa=(0, 0, 0), cost=0.01, seconds=10.0, fc=None):
    doc = json.loads((d / "DEFECTS.json").read_text())
    rec = {"specimen": doc["specimen"], "language": doc["language"], **rlo.meta(MODEL),
           "runs": [{"run": i, "defects": _defects(st), "finding_counts": fc or _fc(),
                     "usage": {"seconds": seconds, "cost_usd": cost},
                     "fixed_usage": {"seconds": seconds, "cost_usd": cost},
                     "fixed": {"false_alarms": fa[i - 1]}}
                    for i, st in enumerate(runs, 1)]}
    path = rlo.record_path(d, MODEL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec))


@pytest.fixture
def tree(tmp_path, monkeypatch):
    root = tmp_path / "specimens"
    a = _specimen(root, "python", "py-01-a")
    b = _specimen(root, "go", "go-01-b", n=2)
    monkeypatch.setattr(rsa, "SPECIMENS_ROOT", root)
    monkeypatch.setattr(rsa, "REPO_ROOT", tmp_path)
    (tmp_path / "README.md").write_text(f"# x\n\n{ca.COMPARISON_START}\nold\n{ca.COMPARISON_END}\n\ntail\n")
    return root, a, b


def _full(tree):
    root, a, b = tree
    _coverage(a, ["detected", "missed", "function_flagged"], fc=_fc(4, 1, 1, 2), fa=2)
    _coverage(b, ["missed", "missed"], fa=0)
    _coverage(a, ["detected", "detected", "missed"], llm=True, fc=_fc(5, 2, 0, 3), fa=3,
              meta={"llm_configured": True, "llm": True, "llm_model": MODEL})
    _coverage(b, ["missed", "detected"], llm=True, fa=1,
              meta={"llm_configured": True, "llm": True, "llm_model": MODEL})
    _llm_record(a, [["missed", "detected", "missed"], ["detected", "detected", "missed"],
                    ["missed", "detected", "detected"]], fa=(1, 2, 4), fc=_fc(6, 2, 1, 3))
    _llm_record(b, [["detected", "missed"], ["detected", "missed"], ["missed", "missed"]], fa=(0, 0, 1))
    return root


# --- loading ------------------------------------------------------------------

def test_load_audit_arm_none_when_a_specimen_lacks_output(tree):
    root, a, b = tree
    _coverage(a, ["detected", "missed", "missed"])
    assert ca.load_audit_arm(rsa.discover(root), False) is None


def test_load_audit_arm_counts(tree):
    root = _full(tree)
    arm = ca.load_audit_arm(rsa.discover(root), False)
    (run,) = arm["runs"]
    assert run["detected"] == {("py-01-a", "D1")}
    assert run["flagged"] == {("py-01-a", "D1"), ("py-01-a", "D3")}
    assert run["fixed_false_alarms"] == 2
    assert run["findings"] == _fc(4, 1, 1, 2)
    assert arm["fixed_specimens"] == 2


def test_load_audit_arm_reads_with_llm_dir(tree):
    root = _full(tree)
    arm = ca.load_audit_arm(rsa.discover(root), True)
    assert arm["runs"][0]["detected"] == {("py-01-a", "D1"), ("py-01-a", "D2"), ("go-01-b", "D2")}
    assert arm["meta"]["llm_model"] == MODEL


def test_load_audit_arm_rejects_mixed_runs(tree):
    root, a, b = tree
    _coverage(a, ["missed"] * 3, meta={"llm_configured": False, "mumei_agent_commit": "a"})
    _coverage(b, ["missed"] * 2, meta={"llm_configured": False, "mumei_agent_commit": "b"})
    with pytest.raises(SystemExit, match="different runs"):
        ca.load_audit_arm(rsa.discover(root), False)


def test_load_llm_arm_none_when_a_record_is_missing(tree):
    root, a, b = tree
    _llm_record(a, [["missed"] * 3])
    assert ca.load_llm_arm(rsa.discover(root), MODEL) is None


def test_load_llm_arm_rejects_uneven_runs(tree):
    root, a, b = tree
    _llm_record(a, [["missed"] * 3, ["missed"] * 3])
    _llm_record(b, [["missed"] * 2])
    with pytest.raises(SystemExit, match="run 2 is missing"):
        ca.load_llm_arm(rsa.discover(root), MODEL)


def test_load_llm_arm_runs_and_usage(tree):
    root = _full(tree)
    arm = ca.load_llm_arm(rsa.discover(root), MODEL)
    assert [len(r["detected"]) for r in arm["runs"]] == [2, 3, 2]
    assert [r["fixed_false_alarms"] for r in arm["runs"]] == [1, 2, 5]
    # two specimens x (buggy + fixed) calls per run
    assert arm["usage"][0] == {"seconds": 40.0, "cost_usd": 0.04, "cost_unknown_calls": 0}
    assert arm["meta"]["model"] == MODEL


def test_load_llm_arm_counts_unknown_cost(tree):
    root, a, b = tree
    _llm_record(a, [["missed"] * 3], cost=None)
    _llm_record(b, [["missed"] * 2])
    arm = ca.load_llm_arm(rsa.discover(root), MODEL)
    assert arm["usage"][0]["cost_unknown_calls"] == 2
    assert arm["usage"][0]["cost_usd"] == 0.02


def test_load_llm_arm_specimen_without_fixed(tree):
    root, a, b = tree
    _llm_record(a, [["missed"] * 3])
    doc = json.loads((b / "DEFECTS.json").read_text())
    path = rlo.record_path(b, MODEL)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"specimen": doc["specimen"], "language": "go", **rlo.meta(MODEL),
                                "runs": [{"run": 1, "defects": _defects(["missed"] * 2),
                                          "finding_counts": _fc(), "usage": {"seconds": 1, "cost_usd": 0}}]}))
    arm = ca.load_llm_arm(rsa.discover(root), MODEL)
    assert arm["fixed_specimens"] == 1
    assert arm["runs"][0]["fixed_false_alarms"] == 0


# --- summary ------------------------------------------------------------------

def test_build_summary_numbers(tree):
    s = ca.build(_full(tree), MODEL)
    assert s["defects"] == 5
    assert s["by_language_totals"] == {"go": 2, "python": 3}
    llm = s["arms"]["llm"]
    assert llm["runs"] == 3
    assert llm["detected"] == {"min": 2, "median": 2, "max": 3}
    assert llm["detected_in_any_run"] == 4 and llm["detected_in_every_run"] == 1
    assert llm["fixed_false_alarms"] == {"min": 1, "median": 2, "max": 5}
    assert llm["cost_usd"] == 0.04 and llm["seconds"] == 40.0
    assert llm["by_language"]["go"] == {"min": 0, "median": 1, "max": 1}
    m = s["arms"]["mumei"]
    assert m["detected"] == {"min": 1, "median": 1, "max": 1}
    assert m["detected_or_flagged"]["median"] == 2
    assert m["cost_usd"] == 0.0 and m["seconds"] is None
    assert s["arms"]["mumei+llm"]["cost_usd"] is None


def test_summary_takes_time_and_cost_from_history(tree):
    root = _full(tree)
    hist = {"runs": [{"llm": False, "audit_seconds": 80.0},
                     {"llm": True, "audit_seconds": 900.0, "llm_cost_usd": 0.25}]}
    (root / "scoreboard").mkdir()
    (root / "scoreboard" / "history.json").write_text(json.dumps(hist))
    s = ca.build(root, MODEL)
    assert s["arms"]["mumei"]["seconds"] == 80.0
    assert s["arms"]["mumei+llm"]["seconds"] == 900.0
    assert s["arms"]["mumei+llm"]["cost_usd"] == 0.25


def test_overlap(tree):
    s = ca.build(_full(tree), MODEL)
    rows = {(o["a"], o["b"]): o for o in s["overlap"]}
    # mumei {a1}; llm any-run {a1,a2,a3,b1}
    assert rows[("mumei", "llm")] == {"a": "mumei", "b": "llm", "both": 1, "only_a": 0, "only_b": 3, "union": 4}
    # mumei+llm {a1,a2,b2}
    assert rows[("mumei+llm", "llm")]["only_a"] == 1 and rows[("mumei+llm", "llm")]["union"] == 5
    assert rows[("mumei", "mumei+llm")]["only_b"] == 2


def test_overlap_skips_missing_arms():
    assert ca.overlap({"mumei": {1}, "mumei+llm": None, "llm": None}) == []


def test_build_without_any_arm(tree):
    root, _, _ = tree
    s = ca.build(root, MODEL)
    assert s["arms"] == {"mumei": None, "mumei+llm": None, "llm": None}
    assert "not run yet" in "\n".join(ca.table_lines(s))
    assert "No comparison yet" in ca.svg(s)
    assert "No comparison yet" in ca.readme_block(s)


def test_build_requires_specimens(tmp_path):
    with pytest.raises(SystemExit, match="no specimens"):
        ca.build(tmp_path, MODEL)


# --- formatting ---------------------------------------------------------------

@pytest.mark.parametrize("spread,runs,total,expected", [
    ({"min": 3, "median": 3, "max": 3}, 1, 10, "3 (30%)"),
    ({"min": 2, "median": 3, "max": 5}, 3, 10, "3 (30%), range 2–5"),
    ({"min": 2, "median": 2.5, "max": 3}, 2, None, "2.5, range 2–3"),
    ({"min": 4, "median": 4, "max": 4}, 3, None, "4"),
    (None, 1, None, "—"),
])
def test_fmt_spread(spread, runs, total, expected):
    assert ca._fmt_spread(spread, runs, total) == expected


@pytest.mark.parametrize("ranges,expected", [
    ([[0.5, 0.5]], "50%"),
    ([[0.2, 0.4], [0.3, 0.3], [0.1, 0.5]], "20%–40%"),
    ([None, None], "—"),
    ([], "—"),
])
def test_fmt_precision_runs(ranges, expected):
    assert ca._fmt_precision_runs(ranges) == expected


@pytest.mark.parametrize("cost,expected", [(None, "unknown"), (0.0, "$0.00"), (0.004, "$0.0040"), (1.234, "$1.23")])
def test_fmt_cost(cost, expected):
    assert ca._fmt_cost({"cost_usd": cost}) == expected


@pytest.mark.parametrize("secs,model_time,expected", [
    (None, False, "—"), (None, True, "—"), (45.2, False, "45 s wall"), (600, False, "10 min wall"),
    (1800, True, "30 min model time"),
])
def test_fmt_seconds(secs, model_time, expected):
    assert ca._fmt_seconds({"seconds": secs}, model_time) == expected


def test_readme_block_notes_unreviewed(tree):
    root = _full(tree)
    s = ca.build(root, MODEL)
    assert "Precision is a range" not in ca.readme_block(s)
    s["arms"]["llm"]["unreviewed"] = {"min": 3, "median": 4, "max": 5}
    assert "median unreviewed per run: LLM only 4" in ca.readme_block(s)


def test_table_and_report(tree):
    s = ca.build(_full(tree), MODEL)
    table = "\n".join(ca.table_lines(s))
    assert "| LLM only (3 runs, median) | 2 (40%), range 2–3 |" in table
    assert "| mumei only | 1 (20%) | 2 (40%) |" in table
    report = ca.report(s)
    assert "## Complementarity" in report and "## Detected by language" in report
    assert f"`{MODEL}`" in report
    assert "| go | 2 |" in report


def test_readme_block_mentions_model_and_chart(tree):
    s = ca.build(_full(tree), MODEL)
    block = ca.readme_block(s)
    assert "specimens/scoreboard/comparison.svg" in block
    assert f"`{MODEL}`" in block
    assert "specimens/COMPARISON.md" in block


def test_svg_has_whiskers_only_for_spread(tree):
    s = ca.build(_full(tree), MODEL)
    out = ca.svg(s)
    assert out.startswith("<svg") and out.rstrip().endswith("</svg>")
    assert "[2–3]" in out and "[1–5]" in out
    assert "mumei + LLM" in out and "LLM only" in out


def test_svg_escapes_model(tree):
    root = _full(tree)
    s = ca.build(root, MODEL)
    s["arms"]["llm"]["meta"]["model"] = "a<b>&c"
    assert "a&lt;b&gt;&amp;c" in ca.svg(s)


# --- main ---------------------------------------------------------------------

def test_main_writes_and_check(tree, capsys):
    root = _full(tree)
    assert ca.main(["--model", MODEL]) == 0
    for p in (root / "scoreboard" / "comparison.json", root / "scoreboard" / "comparison.svg",
              root / "COMPARISON.md"):
        assert p.is_file()
    readme = (root.parent / "README.md").read_text()
    assert "old" not in readme and "tail" in readme and "comparison.svg" in readme
    assert ca.main(["--model", MODEL, "--check"]) == 0
    (root / "COMPARISON.md").write_text("stale")
    assert ca.main(["--model", MODEL, "--check"]) == 1
    assert "COMPARISON.md is out of date" in capsys.readouterr().err


def test_main_check_flags_stale_readme(tree, capsys):
    root = _full(tree)
    assert ca.main(["--model", MODEL]) == 0
    readme = root.parent / "README.md"
    readme.write_text(readme.read_text().replace("mumei only vs", "x vs", 1))
    assert ca.main(["--model", MODEL, "--check"]) == 1
    assert "README.md is out of date" in capsys.readouterr().err


def test_main_missing_markers(tree):
    root = _full(tree)
    (root.parent / "README.md").write_text("# no markers\n")
    with pytest.raises(SystemExit, match="markers"):
        ca.main(["--model", MODEL])


def test_main_model_from_env(tree, monkeypatch):
    root = _full(tree)
    monkeypatch.setenv("LLM_MODEL", MODEL)
    assert ca.main([]) == 0
    assert json.loads((root / "scoreboard" / "comparison.json").read_text())["arms"]["llm"]["runs"] == 3


def test_main_other_model_has_no_llm_row(tree):
    root = _full(tree)
    assert ca.main(["--model", "other/model"]) == 0
    assert json.loads((root / "scoreboard" / "comparison.json").read_text())["arms"]["llm"] is None


def test_main_makes_no_network_calls(tree, monkeypatch):
    import urllib.request
    _full(tree)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("network call"))
    monkeypatch.setenv("LLM_API_KEY", "sk-SENTINEL-not-a-real-key")
    assert ca.main(["--model", MODEL]) == 0
    root = tree[0]
    for p in root.rglob("*"):
        if p.is_file():
            assert "SENTINEL" not in p.read_text()
