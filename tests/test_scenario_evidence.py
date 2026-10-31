from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from scenario_evidence import (  # noqa: E402
    aggregate_evidence, capture_identities, load_result, render_evidence,
)


def claim(name="clamp_dose", **changes):
    return {
        "atom": name, "effective_grade": "G4", "effective_grade_complete": True,
        "evidence_kind": "z3", "freshness": "fresh", "requires": "x >= 0",
        "ensures": "result <= x", "dependencies": [], "unresolved_dependencies": [],
        "assumed_clauses": [], "content_hash": "content", "proof_hash": "proof", **changes,
    }


@pytest.fixture
def evidence(tmp_path):
    (tmp_path / "correct.mm").write_text("fixture source")
    (tmp_path / "proof.json").write_text(json.dumps({"version": "1.1", "atoms": []}))
    for step in ("verify", "gate"):
        (tmp_path / f"{step}.log").write_text(f"fixture {step}")
    data = {
        "scenario": "fixture", "version": "1.0.0", "overall_status": "PASS",
        "evidence_requirements": {
            "claims": [{"step": "verify", "source": "correct.mm", "atom": "clamp_dose", "minimum_grade": "G4", "require_complete": True}],
            "steps": {"verify": "verify_model", "gate": "gate_model"},
            "charter_steps": ["gate"],
            "declared_assumptions": ["Solver and runner are trusted."],
            "unverified_connections": ["No runtime adapter is verified."],
            "out_of_scope": ["Production deployment."],
        },
        "layers": {"l1_z3": {"status": "PASS", "steps": [
            {"id": "verify", "status": "PASS", "harness_stage": "verify_model", "output_file": "verify.log"},
            {"id": "gate", "status": "PASS", "harness_stage": "gate_model", "output_file": "gate.log"},
        ]}},
        "claim_book": {"entries": [{"step": "verify", "source": str(tmp_path / "correct.mm"), "cert": "proof.json", "file": "book.json", "status": "ok"}]},
        "charter_gate": {"entries": [{"step": "gate", "status": "ok", "gate_status": "pass", "lock_status": "match", "atoms": [{"name": "clamp_dose", "status": "pass", "charter": "dosage"}]}]},
    }
    book = {
        "schema": "mumei.claimbook/v1", "input": str(tmp_path / "correct.mm"),
        "certificate": str(tmp_path / "proof.json"), "certificate_integrity": "match",
        "generator": {"mumei_version": "fixture", "z3_version": "fixture"},
        "trusted_base": {"trusted_atoms": [], "kernel_axioms": []}, "claims": [claim()],
    }

    def snapshot():
        book["summary"] = {
            "total": len(book["claims"]),
            "by_effective_grade": {g: sum(c["effective_grade"] == g for c in book["claims"]) for g in ("G0", "G1", "G2", "G3", "G4", "G5")},
            "by_freshness": {s: sum(c["freshness"] == s for c in book["claims"]) for s in ("fresh", "drifted", "uncertified")},
        }
        (tmp_path / "book.json").write_text(json.dumps(book))
        data["evidence_identities"] = capture_identities(data, tmp_path)
        (tmp_path / "result.json").write_text(json.dumps(data))

    snapshot()
    return data, book, snapshot, tmp_path


def test_report_separates_proof_observations_assumptions_and_connections(evidence):
    data, _, _, root = evidence
    summary = aggregate_evidence(data, root)
    assert summary["status"] == "satisfied"
    assert summary["claims"][0]["evidence_kind"] == "z3"
    assert summary["claims"][0]["observation"]["status"] == "unavailable"
    data["evidence_summary"] = summary
    rendered = render_evidence(data)
    for label in ("Execution observations (not formal proof)", "Declared assumptions (not checked facts)", "Unverified connections", "Out of scope", "Trusted base", "do not establish authenticity"):
        assert label in rendered
    assert str(root) not in rendered
    assert "not an application safety grade" in rendered
    assert "requires" not in summary["declared_assumptions"]


@pytest.mark.parametrize("name", ["correct.mm", "proof.json", "book.json", "verify.log", "gate.log"])
@pytest.mark.parametrize("operation", ["delete", "replace"])
def test_required_artifact_changes_reject_a_previously_successful_report(evidence, name, operation):
    data, _, _, root = evidence
    data["evidence_summary"] = {"status": "satisfied"}
    (root / "result.json").write_text(json.dumps(data))
    if operation == "delete":
        (root / name).unlink()
    else:
        (root / name).write_text("replacement")
    updated = load_result(root / "result.json")
    assert updated["overall_status"] == "FAIL"
    assert updated["evidence_summary"]["status"] == "incomplete"
    assert updated["evidence_summary"]["issues"]


@pytest.mark.parametrize("name", ["charter.lock", "charter.mm", "charter-report.json", "mumei.toml"])
def test_required_charter_inputs_and_reports_are_bound(evidence, name):
    data, _, snapshot, root = evidence
    data["evidence_requirements"]["artifacts"] = [name]
    (root / name).write_text("fixture artifact")
    snapshot()
    assert aggregate_evidence(data, root)["status"] == "satisfied"
    (root / name).unlink()
    assert aggregate_evidence(data, root)["status"] == "incomplete"


@pytest.mark.parametrize("field,value", [("schema", "mumei.claimbook/v99"), ("certificate_integrity", "mismatch"), ("input", "other.mm"), ("certificate", "other.json"), ("claims", []), ("trusted_base", None), ("generator", None)])
def test_invalid_or_mismatched_books_fail_closed(evidence, field, value):
    data, book, snapshot, root = evidence
    book[field] = value
    snapshot()
    assert aggregate_evidence(data, root)["status"] == "incomplete"


@pytest.mark.parametrize("field,value", [("effective_grade", "G3"), ("effective_grade_complete", False), ("freshness", "drifted"), ("freshness", "uncertified"), ("dependencies", "helper"), ("assumed_clauses", "assume true"), ("observation", {"status": "supported"}), ("discrimination", {"status": "discriminating"})])
def test_invalid_or_insufficient_claims_fail_closed(evidence, field, value):
    data, book, snapshot, root = evidence
    book["claims"][0][field] = value
    snapshot()
    assert aggregate_evidence(data, root)["status"] == "incomplete"


@pytest.mark.parametrize("name", ["clamp", "Point::clamp_dose", "clamp_dose "])
def test_claim_names_use_exact_not_fuzzy_matching(evidence, name):
    data, _, _, root = evidence
    data["evidence_requirements"]["claims"][0]["atom"] = name
    summary = aggregate_evidence(data, root)
    assert summary["status"] == "incomplete"
    assert "required fully qualified claim was not found" in summary["issues"]


def test_duplicate_claims_and_duplicate_json_keys_reject(evidence):
    data, book, snapshot, root = evidence
    book["claims"].append(copy.deepcopy(book["claims"][0]))
    snapshot()
    assert aggregate_evidence(data, root)["status"] == "incomplete"
    (root / "book.json").write_text('{"schema":"mumei.claimbook/v1","schema":"mumei.claimbook/v1"}')
    data["evidence_identities"] = capture_identities(data, root)
    assert aggregate_evidence(data, root)["status"] == "incomplete"


@pytest.mark.parametrize("case", ["direct", "transitive", "cycle", "cycle_missing", "self", "non_exact"])
def test_dependency_closure_terminates_and_distinguishes_incompleteness(evidence, case):
    data, book, snapshot, root = evidence
    top = book["claims"][0]
    if case == "direct":
        top.update(dependencies=["missing"], unresolved_dependencies=["missing"], effective_grade_complete=False)
    elif case == "self":
        top["dependencies"] = [top["atom"]]
    elif case == "non_exact":
        top.update(dependencies=["Point::helper"], effective_grade_complete=False)
        book["claims"].append(claim("Point::helper"))
    else:
        top["dependencies"] = ["helper"]
        helper = claim("helper", dependencies=[top["atom"]] if case.startswith("cycle") else [])
        if case != "cycle":
            helper.update(unresolved_dependencies=["missing"], effective_grade_complete=False)
        book["claims"].append(helper)
    snapshot()
    summary = aggregate_evidence(data, root)
    assert summary["status"] == ("satisfied" if case in {"cycle", "self"} else "incomplete")
    coverage = summary["claims"][0]["dependency_coverage"]
    if case == "direct":
        assert coverage["direct_unresolved_dependencies"] == ["missing"]
    if case in {"transitive", "cycle_missing"}:
        assert coverage["transitive_unresolved_dependencies"] == ["missing"]
        assert coverage["incomplete_dependencies"] == ["helper"]
    assert summary["claims"][0]["effective_grade"] == "G4"


def test_transitive_staleness_and_assumptions_are_not_hidden(evidence):
    data, book, snapshot, root = evidence
    book["claims"][0]["dependencies"] = ["helper"]
    book["claims"].append(claim("helper", freshness="drifted", assumed_clauses=["x >= 0"]))
    snapshot()
    summary = aggregate_evidence(data, root)
    assert summary["status"] == "incomplete"
    assert summary["claims"][0]["assumed_clauses"] == {"helper": ["x >= 0"]}


@pytest.mark.parametrize("status", ["weak", "inconclusive", "not_checked", "no_mutants", "discriminating"])
def test_controls_are_not_inferred_from_passing_execution(evidence, status):
    data, book, snapshot, root = evidence
    book["claims"][0]["discrimination"] = {
        "status": status, "tested": 1, "killed": 0 if status == "weak" else 1,
        "survived": 1 if status == "weak" else 0, "unanalyzable": 0,
        "surviving": ["mutant"] if status == "weak" else [],
    }
    snapshot()
    optional = aggregate_evidence(data, root)
    assert optional["status"] == "satisfied"
    assert optional["claims"][0]["discrimination"]["status"] == status
    data["evidence_requirements"]["claims"][0]["require_discriminating"] = True
    assert aggregate_evidence(data, root)["status"] == ("satisfied" if status == "discriminating" else "incomplete")


def test_contradicting_observations_are_not_replaced_by_proof_or_pass(evidence):
    data, book, snapshot, root = evidence
    book["claims"][0]["observation"] = {"status": "contradicted", "supporting": 2, "contradicting": 1, "neutral": 0}
    snapshot()
    summary = aggregate_evidence(data, root)
    assert summary["status"] == "incomplete"
    assert summary["claims"][0]["observation"]["contradicting"] == 1
    assert summary["claims"][0]["effective_grade"] == "G4"


@pytest.mark.parametrize("mutation", ["missing_step", "missing_stage", "skip", "fail", "missing_gate", "unknown_gate", "gate_fail", "empty_atoms", "duplicate_step", "duplicate_gate", "duplicate_book", "duplicate_requirement", "optional_claim", "empty_requirements", "unknown_config", "bad_identities"])
def test_required_stages_and_gates_cannot_be_waived(evidence, mutation):
    data, _, _, root = evidence
    steps = data["layers"]["l1_z3"]["steps"]
    gate = data["charter_gate"]["entries"][0]
    config = data["evidence_requirements"]
    if mutation == "missing_step":
        steps.pop()
    elif mutation == "missing_stage":
        steps[0].pop("harness_stage")
    elif mutation in {"skip", "fail"}:
        steps[1]["status"] = "SKIPPED" if mutation == "skip" else "FAIL"
    elif mutation == "missing_gate":
        data.pop("charter_gate")
    elif mutation == "unknown_gate":
        gate["status"] = "unavailable"
    elif mutation == "gate_fail":
        gate["gate_status"] = "fail"
    elif mutation == "empty_atoms":
        gate["atoms"] = []
    elif mutation == "duplicate_step":
        steps.append(copy.deepcopy(steps[0]))
    elif mutation == "duplicate_gate":
        data["charter_gate"]["entries"].append(copy.deepcopy(gate))
    elif mutation == "duplicate_book":
        data["claim_book"]["entries"].append(copy.deepcopy(data["claim_book"]["entries"][0]))
    elif mutation == "duplicate_requirement":
        config["claims"].append(copy.deepcopy(config["claims"][0]))
    elif mutation == "optional_claim":
        config["claims"][0]["optional"] = True
    elif mutation == "empty_requirements":
        config["claims"] = []
    elif mutation == "unknown_config":
        config["ignore_missing"] = True
    else:
        data["evidence_identities"] = []
    config["out_of_scope"].append("Ignore missing required evidence.")
    assert aggregate_evidence(data, root)["status"] == "incomplete"


@pytest.mark.parametrize("path", ["../external.mm", "/external.mm", ""])
def test_source_and_artifact_paths_cannot_escape_the_report(evidence, path):
    data, _, _, root = evidence
    data["evidence_requirements"]["artifacts"] = [path]
    assert aggregate_evidence(data, root)["status"] == "incomplete"


def test_symlink_escape_is_rejected(evidence):
    data, _, _, root = evidence
    outside = root.parent / "outside-evidence"
    outside.write_text("outside")
    (root / "escape").symlink_to(outside)
    data["evidence_requirements"]["artifacts"] = ["escape"]
    assert aggregate_evidence(data, root)["status"] == "incomplete"


def test_output_is_stable_and_existing_failure_is_preserved(evidence):
    data, _, snapshot, root = evidence
    first = aggregate_evidence(data, root)
    data["evidence_identities"] = dict(reversed(list(data["evidence_identities"].items())))
    assert json.dumps(first) == json.dumps(aggregate_evidence(data, root))
    data["overall_status"] = "FAIL"
    snapshot()
    assert load_result(root / "result.json")["overall_status"] == "FAIL"
    data["evidence_requirements"]["claims"][0]["minimum_grade"] = "G1"
    assert aggregate_evidence(data, root)["requirements_sha256"] != first["requirements_sha256"]


def test_legacy_result_remains_unchanged(tmp_path):
    data = {"scenario": "legacy", "overall_status": "PASS", "layers": {}}
    (tmp_path / "result.json").write_text(json.dumps(data))
    assert load_result(tmp_path / "result.json") == data
    assert render_evidence(data) == ""


def test_markdown_cli_summary_and_highlights_share_revalidation(evidence, tmp_path):
    from generate_report import render_scenario_markdown, write_summary, write_highlights
    from dashboard.cli_report import render

    data, _, _, root = evidence
    report = load_result(root / "result.json")
    assert "Required evidence: **satisfied**" in render_scenario_markdown(report, root)
    assert "Unverified connections" in render(report)
    assert "TRUSTLESS" not in render(report)
    assert "LIMITED MODEL EVIDENCE" in render(report)
    reports = root / "reports" / "fixture" / "latest"
    reports.parent.mkdir(parents=True)
    reports.symlink_to(root, target_is_directory=True)
    (root / "proof.json").unlink()
    updated = load_result(root / "result.json")
    assert "Required evidence: **incomplete**" in render(updated)
    assert write_summary(root / "reports", root / "summary.md", ["fixture"], True) == 0
    assert write_highlights(root, root / "reports", root / "highlights.md", ["fixture"], True) == 0
    assert "| `fixture` | FAIL |" in (root / "summary.md").read_text()
    assert "required evidence **incomplete**" in (root / "summary.md").read_text()
    assert "Required scenario evidence: incomplete" in (root / "highlights.md").read_text()


def test_unknown_certificate_version_and_malformed_bytes_are_rejected(evidence):
    data, _, _, root = evidence
    (root / "proof.json").write_text('{"version":"future"}')
    data["evidence_identities"] = capture_identities(data, root)
    assert aggregate_evidence(data, root)["status"] == "incomplete"
    (root / "book.json").write_bytes(b"\xff")
    data["evidence_identities"] = capture_identities(data, root)
    assert aggregate_evidence(data, root)["status"] == "incomplete"


def test_dependency_grade_cannot_be_hidden_by_a_higher_claim_grade(evidence):
    data, book, snapshot, root = evidence
    book["claims"][0]["dependencies"] = ["helper"]
    book["claims"].append(claim("helper", effective_grade="G1", evidence_kind="trusted"))
    snapshot()
    summary = aggregate_evidence(data, root)
    assert summary["status"] == "incomplete"
    assert summary["claims"][0]["effective_grade"] == "G4"


def test_same_named_claims_from_other_sources_do_not_satisfy_a_selector(evidence):
    data, _, _, root = evidence
    data["claim_book"]["entries"][0]["source"] = str(root / "another.mm")
    assert aggregate_evidence(data, root)["status"] == "incomplete"


def test_unsupported_summary_cannot_override_artifact_evidence(evidence):
    data, _, snapshot, root = evidence
    data["evidence_summary"] = {"schema": "future/v99", "status": "satisfied"}
    data["evidence_requirements"]["claims"][0]["atom"] = "missing"
    snapshot()
    assert load_result(root / "result.json")["evidence_summary"]["status"] == "incomplete"
