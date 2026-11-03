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
    assert "specimens/scoreboard/arms.svg" in block
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
    for p in (root / "scoreboard" / "arms.json", root / "scoreboard" / "arms.svg",
              root / "COMPARISON.md"):
        assert p.is_file()
    readme = (root.parent / "README.md").read_text()
    assert "old" not in readme and "tail" in readme and "arms.svg" in readme
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
    assert json.loads((root / "scoreboard" / "arms.json").read_text())["arms"]["llm"]["runs"] == 3


def test_main_other_model_has_no_llm_row(tree):
    root = _full(tree)
    assert ca.main(["--model", "other/model"]) == 0
    assert json.loads((root / "scoreboard" / "arms.json").read_text())["arms"]["llm"] is None


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


# --- findings by kind -----------------------------------------------------------


def _with_findings(d, llm, buggy, fixed_files=None):
    out = rsa.audit_dir(d, llm)
    cov = json.loads((out / "coverage.json").read_text())
    cov["findings"] = [{"kind": k, "text": t} for k, t in buggy]
    (out / "coverage.json").write_text(json.dumps(cov))
    if fixed_files is not None:
        (d / rsa.FIXED_PATCH).write_text("")
        label = str(d.relative_to(rsa.REPO_ROOT))
        audit = {"file_results": [dict({"source_file": f"{label}/{name}"}, **kinds)
                                  for name, kinds in fixed_files.items()]}
        (out / "fixed").mkdir(exist_ok=True)
        (out / "fixed" / "audit.json").write_text(json.dumps(audit))


def _kinds_tree(tree, fixed=True):
    root = _full(tree)
    _, a, b = tree
    _with_findings(a, False, [("verification_violations", "f can divide by x"),
                              ("verification_violations", "Z3 Counter-example: x=0")],
                   {"app.py": {"verification_violations": ["f can divide by x"]}} if fixed else None)
    _with_findings(b, False, [], {"main.go": {}} if fixed else None)
    _with_findings(a, True, [("verification_violations", "f can divide by x"),
                             ("cross_validation_gaps", "spec ambiguity (missing_requirement): g"),
                             ("spec_health_issues", "malformed-extraction: g")],
                   {"app.py": {"cross_validation_gaps": ["spec ambiguity: g", "spec ambiguity: h"],
                               "verification_violations": ["f can divide by x"],
                               "counterexample_values": [{"function_name": "f", "counterexample": {}}]}}
                   if fixed else None)
    _with_findings(b, True, [("spec_health_issues", "encoding-gap: k")],
                   {"main.go": {"spec_health_issues": ["encoding-gap: k"]}} if fixed else None)
    return root


def test_kind_counts_skip_supporting_entries():
    got = ca._kind_counts([{"kind": "verification_violations", "text": "a"},
                           {"kind": "verification_violations", "text": "Z3 Counter-example: x=0"},
                           {"kind": "counterexample_values", "text": "counterexample for `f`"},
                           {"kind": "spec_health_issues", "text": "b"}])
    assert got == {"spec_health_issues": 1, "verification_violations": 1}


def test_audit_kinds_buggy_and_fixed(tree):
    root = _kinds_tree(tree)
    specimens = rsa.discover(root)
    mumei = ca.load_audit_arm(specimens, llm=False)["kinds"]
    with_llm = ca.load_audit_arm(specimens, llm=True)["kinds"]
    assert mumei == {"buggy": {"verification_violations": 1}, "fixed": {"verification_violations": 1}}
    assert with_llm["buggy"] == {"cross_validation_gaps": 1, "spec_health_issues": 2,
                                 "verification_violations": 1}
    assert with_llm["fixed"] == {"cross_validation_gaps": 2, "spec_health_issues": 1,
                                 "verification_violations": 1}


def test_audit_kinds_fixed_none_when_any_fixed_audit_missing(tree):
    root = _kinds_tree(tree)
    _, a, _ = tree
    (rsa.audit_dir(a, True) / "fixed" / "audit.json").unlink()
    kinds = ca.load_audit_arm(rsa.discover(root), llm=True)["kinds"]
    assert kinds["fixed"] is None
    assert kinds["buggy"]["spec_health_issues"] == 2


def test_audit_kinds_without_findings_list(tree):
    root = _full(tree)
    assert ca.load_audit_arm(rsa.discover(root), llm=False)["kinds"] == {"buggy": {}, "fixed": None}


def _summary(root):
    return ca.build(root, MODEL)


def test_summary_carries_kinds_for_audit_rows_only(tree):
    s = _summary(_kinds_tree(tree))
    assert s["arms"]["mumei"]["findings_by_kind"]["fixed"] == {"verification_violations": 1}
    assert "findings_by_kind" not in s["arms"]["llm"]


def test_kind_lines_table(tree):
    lines = ca.kind_lines(_summary(_kinds_tree(tree)))
    assert lines[0] == ("| Kind | mumei only: buggy | mumei only: fixed | mumei + LLM: buggy | "
                        "mumei + LLM: fixed |")
    assert lines[2] == "| Verifier violations | 1 | 1 | 1 | 1 |"
    assert lines[3] == "| Spec vs code cross-check gaps | 0 | 0 | 1 | 2 |"
    assert lines[4] == "| Spec health issues | 0 | 0 | 2 | 1 |"
    assert len(lines) == 5


def test_kind_lines_dash_when_fixed_unknown(tree):
    root = _kinds_tree(tree, fixed=False)
    lines = ca.kind_lines(_summary(root))
    assert "| Verifier violations | 1 | — | 1 | — |" in lines


def test_kind_lines_unknown_kind_sorts_last(tree):
    root = _kinds_tree(tree)
    _, a, _ = tree
    _with_findings(a, True, [("zz_new_kind", "x"), ("verification_violations", "f")])
    lines = ca.kind_lines(_summary(root))
    assert lines[-1].startswith("| zz_new_kind |")


def test_kind_lines_empty_without_audit_rows():
    assert ca.kind_lines({"arms": {"mumei": None, "mumei+llm": None, "llm": None}}) == []


def test_spec_note_counts_non_verifier_findings(tree):
    note = ca._spec_note(_summary(_kinds_tree(tree)))
    assert note.startswith("Of the 4 mumei + LLM findings on fixed code, 3 are spec diagnostics")


def test_spec_note_none_when_only_verifier_findings(tree):
    root = _kinds_tree(tree)
    _, a, b = tree
    _with_findings(a, True, [], {"app.py": {"verification_violations": ["f"]}})
    _with_findings(b, True, [], {"main.go": {}})
    assert ca._spec_note(_summary(root)) is None


def test_spec_note_none_without_fixed_kinds(tree):
    assert ca._spec_note(_summary(_kinds_tree(tree, fixed=False))) is None


def test_report_and_readme_include_kinds(tree):
    s = _summary(_kinds_tree(tree))
    rep = ca.report(s)
    assert "## mumei findings by kind" in rep
    assert "3 are spec diagnostics" in rep
    block = ca.readme_block(s)
    assert "3 are spec diagnostics" in block
    assert "findings by kind" in block


def test_report_omits_kind_section_without_audits(tree):
    root, a, b = tree
    _llm_record(a, [["detected", "missed", "missed"]])
    _llm_record(b, [["detected", "missed"]])
    s = _summary(root)
    assert "findings by kind" not in ca.report(s)


# --- staleness and consistency checks ---------------------------------------------


def _set(path, **fields):
    doc = json.loads(path.read_text())
    doc.update(fields)
    path.write_text(json.dumps(doc))


@pytest.mark.parametrize("llm", [False, True])
def test_audit_arm_rejects_changed_specimen(tree, monkeypatch, llm):
    root = _full(tree)
    _, a, _ = tree
    monkeypatch.setattr(rsa, "specimen_hash", lambda d: "now")
    _set(rsa.audit_dir(a, llm) / "coverage.json", source_hash="then")
    with pytest.raises(SystemExit, match="py-01-a: specimen changed"):
        ca.load_audit_arm(rsa.discover(root), llm)


def test_audit_arm_accepts_matching_hash(tree, monkeypatch):
    root = _full(tree)
    _, a, b = tree
    monkeypatch.setattr(rsa, "specimen_hash", lambda d: "h-" + d.name)
    for d in (a, b):
        _set(rsa.audit_dir(d, False) / "coverage.json", source_hash="h-" + d.name)
    assert ca.load_audit_arm(rsa.discover(root), False) is not None


def test_llm_arm_rejects_changed_specimen(tree, monkeypatch):
    root = _full(tree)
    _, _, b = tree
    monkeypatch.setattr(rlo.rb, "baseline_hash", lambda d: "now")
    _set(rlo.record_path(b, MODEL), source_hash="then")
    with pytest.raises(SystemExit, match="go-01-b: specimen changed since the LLM-only review"):
        ca.load_llm_arm(rsa.discover(root), MODEL)


def test_llm_arm_accepts_matching_hash(tree, monkeypatch):
    root = _full(tree)
    _, a, b = tree
    monkeypatch.setattr(rlo.rb, "baseline_hash", lambda d: "same")
    for d in (a, b):
        _set(rlo.record_path(d, MODEL), source_hash="same")
    assert ca.load_llm_arm(rsa.discover(root), MODEL)["runs"]


def test_build_rejects_model_mismatch(tree):
    root = _full(tree)
    _, a, b = tree
    for d in (a, b):
        _set(rsa.audit_dir(d, True) / "coverage.json",
             meta={"llm_configured": True, "llm": True, "llm_model": "other/model"})
    with pytest.raises(SystemExit, match="used other/model but --model is openai/test-model"):
        ca.build(root, MODEL)


def test_build_model_mismatch_ignored_without_llm_records(tree):
    root, a, b = tree
    _coverage(a, ["missed"] * 3)
    _coverage(b, ["missed"] * 2)
    for d in (a, b):
        _coverage(d, ["missed"] * (3 if d is a else 2), llm=True,
                  meta={"llm_configured": True, "llm": True, "llm_model": "other/model"})
    assert ca.build(root, MODEL)["arms"]["llm"] is None


def _history(root, runs):
    (root / "scoreboard").mkdir(exist_ok=True)
    (root / "scoreboard" / "history.json").write_text(json.dumps({"runs": runs}))


def _stamp(tree, llm, stamp):
    _, a, b = tree
    meta = {"llm_configured": llm, "llm": llm, "generated_at": stamp}
    if llm:
        meta["llm_model"] = MODEL
    for d in (a, b):
        _set(rsa.audit_dir(d, llm) / "coverage.json", meta=meta)


def test_history_run_matched_by_timestamp(tree):
    root = _full(tree)
    _stamp(tree, True, "T1")
    _history(root, [{"llm": True, "generated_at": "T1", "audit_seconds": 900.0, "llm_cost_usd": 0.25},
                    {"llm": True, "generated_at": "T2", "audit_seconds": 50.0, "llm_cost_usd": 9.0}])
    m = ca.build(root, MODEL)["arms"]["mumei+llm"]
    assert (m["seconds"], m["cost_usd"]) == (900.0, 0.25)


def test_history_run_missing_gives_unknown_cost_and_time(tree):
    root = _full(tree)
    _stamp(tree, True, "T0")
    _stamp(tree, False, "N0")
    _history(root, [{"llm": False, "generated_at": "N9", "audit_seconds": 80.0},
                    {"llm": True, "generated_at": "T9", "audit_seconds": 900.0, "llm_cost_usd": 0.25}])
    s = ca.build(root, MODEL)
    assert s["arms"]["mumei+llm"]["seconds"] is None and s["arms"]["mumei+llm"]["cost_usd"] is None
    assert s["arms"]["mumei"]["seconds"] is None and s["arms"]["mumei"]["cost_usd"] == 0.0


def test_history_run_ignores_other_mode_with_same_timestamp(tree):
    root = _full(tree)
    _stamp(tree, True, "T1")
    _history(root, [{"llm": False, "generated_at": "T1", "audit_seconds": 80.0}])
    assert ca.build(root, MODEL)["arms"]["mumei+llm"]["seconds"] is None


@pytest.mark.parametrize("entry,text", [
    ({"cost_usd": 0.0}, "$0.00"),
    ({"cost_usd": 0.0612}, "$0.06"),
    ({"cost_usd": 0.0012}, "$0.0012"),
    ({"cost_usd": None}, "unknown"),
    ({"cost_usd": 0.06, "cost_unknown_calls": 2}, "≥ $0.06"),
    ({"cost_usd": 0.0, "cost_unknown_calls": 3}, "unknown"),
    ({"cost_usd": 0.06, "cost_unknown_calls": 0}, "$0.06"),
])
def test_fmt_cost(entry, text):
    assert ca._fmt_cost(entry) == text


def test_llm_arm_with_unknown_cost_shows_lower_bound(tree):
    root = _full(tree)
    _, a, _ = tree
    rec = json.loads(rlo.record_path(a, MODEL).read_text())
    rec["runs"][0]["usage"]["cost_usd"] = None
    rlo.record_path(a, MODEL).write_text(json.dumps(rec))
    s = ca.build(root, MODEL)
    assert s["arms"]["llm"]["cost_unknown_calls"] == 1
    assert "≥ $" in ca.report(s)


def test_audit_kinds_skip_specimens_without_fixed_patch(tree):
    root = _kinds_tree(tree)
    _, _, b = tree
    (b / rsa.FIXED_PATCH).unlink()
    (rsa.audit_dir(b, True) / "fixed" / "audit.json").unlink()
    kinds = ca.load_audit_arm(rsa.discover(root), llm=True)["kinds"]
    assert kinds["fixed"] == {"cross_validation_gaps": 2, "verification_violations": 1}


@pytest.mark.parametrize("false_alarms,expected", [
    (None, "Of the 4 mumei + LLM findings on fixed code, 3 are"),
    (4, "Of the 4 mumei + LLM findings on fixed code, 3 are"),
    (3, "Of the 4 mumei + LLM findings on fixed code (3 false alarms, 1 reviewed as real), 3 are"),
    (0, "Of the 4 mumei + LLM findings on fixed code (0 false alarms, 4 reviewed as real), 3 are"),
])
def test_spec_note_separates_findings_reviewed_as_real(tree, false_alarms, expected):
    summary = _summary(_kinds_tree(tree))
    arm = summary["arms"]["mumei+llm"]
    if false_alarms is None:
        arm.pop("fixed_false_alarms", None)
    else:
        arm["fixed_false_alarms"] = {"min": false_alarms, "median": false_alarms, "max": false_alarms}
    assert ca._spec_note(summary).startswith(expected)
