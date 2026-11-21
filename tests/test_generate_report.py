from __future__ import annotations

import json
import sys
import types
import importlib.util
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generate_report import (  # noqa: E402
    OPTIONAL_SCENARIOS,
    SCENARIO_ORDER,
    bug_detection_moment,
    charter_gate_label,
    claim_book_label,
    render_negative_controls_markdown,
    render_test_observations_markdown,
    render_scenario_markdown,
    scenario_code_paths,
    write_summary,
    write_highlights,
)

from dashboard.cli_report import (  # noqa: E402
    claim_book_label as cli_claim_book_label,
    render as render_cli_report,
)


def test_claim_book_section_is_rendered_with_counts_and_detail(tmp_path):
    data = {
        "scenario": "medical_device",
        "scenario_name": "Medical Device",
        "overall_status": "PASS",
        "proof_density": {"verified": 1, "total": 1, "percentage": 100},
        "layers": {},
        "claim_book": {
            "entries": [
                {
                    "step": "verify_correct",
                    "status": "ok",
                    "total": 3,
                    "by_effective_grade": {"G0": 0, "G1": 0, "G4": 2, "G5": 1},
                    "by_freshness": {"fresh": 3, "drifted": 0, "uncertified": 0},
                    "incomplete": 1,
                    "lowest_effective_grade": "G4",
                },
                {
                    "step": "verify_other",
                    "status": "unavailable",
                    "detail": "claims command is unavailable",
                },
            ],
            "totals": {},
        },
    }

    report = render_scenario_markdown(data, tmp_path)

    assert "## Claim Book" in report
    assert "| verify_correct | ok | 3 | 3 | 0 | 0 | 3 | 0 | 0 | 1 | G4 |" in report
    assert "unavailable: claims command is unavailable" in report
    assert "Informational: the Claim Book does not change the scenario status." in report


def test_old_result_does_not_render_claim_book_section(tmp_path):
    report = render_scenario_markdown(
        {
            "scenario": "legacy",
            "overall_status": "PASS",
            "proof_density": {},
            "layers": {},
        },
        tmp_path,
    )

    assert "## Claim Book" not in report


def test_cli_report_uses_scenario_specific_bounded_audit_summary():
    from dashboard.cli_report import render

    report = render(
        {
            "scenario": "evidence_acceptance_eval",
            "scenario_name": "Core Acceptance Descriptor Evaluation",
            "overall_status": "PASS",
            "layers": {"l1_z3": {}},
            "proof_density": {"verified": 3, "total": 3, "percentage": 100},
            "narrative": {
                "before": "Descriptor not evaluated",
                "after": "Closed-shape result only",
                "audit_status": "DESCRIPTOR-ONLY",
                "moment": "Closed descriptor boundary evaluated",
            },
        }
    )

    assert "Audit Status:  DESCRIPTOR-ONLY" in report
    assert "Moment:        Closed descriptor boundary evaluated" in report
    assert "TRUSTLESS" not in report
    assert "Proof failure → Bug found" not in report


def test_failed_native_report_ignores_bounded_narrative_overrides():
    report = render_cli_report(
        {
            "scenario": "native_check",
            "scenario_name": "Native Check",
            "overall_status": "FAIL",
            "layers": {"l1_z3": {}},
            "proof_density": {"verified": 0, "total": 1, "percentage": 0},
            "narrative": {
                "audit_status": "BOUNDED CHECK",
                "moment": "Bundle consistency only; wrong pin claims nothing.",
            },
        }
    )

    assert "Audit Status:  ATTENTION" in report
    assert "Audit Status:  BOUNDED CHECK" not in report
    assert "Moment:        Proof failure → Bug found" in report
    assert "Moment:        Bundle consistency only" not in report


def test_evidence_route_reports_and_result_messages_are_bounded():
    root = Path(__file__).resolve().parents[1]
    scenarios = {
        "evidence_accept_list": "BOUNDED LIST-ACCEPTANCE",
        "evidence_check_adapter": "REPRESENTATION-CHECK",
        "evidence_check_attempt_acceptance": "REPRESENTATION-CHECK",
        "evidence_acceptance_eval": "DESCRIPTOR-ONLY",
    }

    for name, audit_status in scenarios.items():
        scenario = json.loads(
            (root / "scenarios" / name / "scenario.json").read_text(encoding="utf-8")
        )
        narrative = scenario["narrative"]
        report = render_cli_report(
            {
                "scenario": name,
                "scenario_name": scenario["name"],
                "overall_status": "PASS",
                "layers": {"l1_z3": {}},
                "proof_density": {"verified": 3, "total": 3, "percentage": 100},
                "narrative": narrative,
            }
        )
        result_message = scenario["result_message"]
        narrative_text = " ".join(
            [narrative["after"], narrative["moment"], *narrative["intro"], result_message]
        )

        assert f"Audit Status:  {audit_status}" in report
        assert narrative["after"] in report
        assert "TRUSTLESS" not in report
        assert "Proof failure → Bug found" not in report
        assert result_message.startswith("Result:")
        assert len(f"  {result_message}") <= 62
        assert all(len(line) <= 60 for line in narrative["intro"])
        assert "Correct code proven" not in result_message
        assert "Evidence acceptance" in narrative_text
        assert "grade-promotion" in narrative_text
        assert "adapter execution" in narrative_text
        assert "code-correctness proof" in narrative_text or "proof of code correctness" in narrative_text


def test_lexical_binding_reports_are_bounded_and_failures_force_attention():
    root = Path(__file__).resolve().parents[1]
    scenarios = {
        "rust_bindings": "mumei.rust-lexical-bindings/v1",
        "sol_bindings": "mumei.sol-lexical-bindings/v1",
        "ts_bindings": "mumei.ts-lexical-bindings/v1",
    }
    nonclaims = (
        "type check",
        "compiler-backed resolution",
        "proof",
        "verdict",
        "trusted-safe evidence",
        "audit result",
        "Seal Grade",
    )

    for name, profile in scenarios.items():
        scenario = json.loads(
            (root / "scenarios" / name / "scenario.json").read_text(encoding="utf-8")
        )
        narrative = scenario["narrative"]
        result_message = scenario["result_message"]
        narrative_text = " ".join(
            [
                scenario["description"],
                narrative["after"],
                narrative["moment"],
                *narrative["intro"],
                result_message,
            ]
        )
        assert narrative["audit_status"] == "LEXICAL-METADATA"
        assert all(term.lower() in narrative_text.lower() for term in nonclaims)
        assert f"profile {profile}" in scenario["intent_fidelity"]["success_criteria"][0]
        assert result_message.startswith("Result:")
        assert len(f"  {result_message}") <= 62
        assert len(f"  Moment:        {narrative['moment']}") <= 116
        assert all(len(line) <= 60 for line in narrative["intro"])
        assert not any(
            phrase in result_message.lower()
            for phrase in ("trustless", "correct code proven", "proof")
        )

        passed = render_cli_report(
            {
                "scenario": name,
                "scenario_name": scenario["name"],
                "overall_status": "PASS",
                "layers": {"l1_z3": {}},
                "proof_density": {"verified": 1, "total": 1, "percentage": 100},
                "narrative": narrative,
            }
        )
        failed = render_cli_report(
            {
                "scenario": name,
                "scenario_name": scenario["name"],
                "overall_status": "FAIL",
                "layers": {"l1_z3": {}},
                "proof_density": {"verified": 0, "total": 1, "percentage": 0},
                "narrative": narrative,
            }
        )
        assert "Audit Status:  LEXICAL-METADATA" in passed
        assert "Audit Status:  ATTENTION" in failed
        assert "Audit Status:  LEXICAL-METADATA" not in failed
        assert "TRUSTLESS" not in passed + failed
        assert "Correct code proven" not in passed + failed


def test_native_and_evidence_reports_have_bounded_route_summaries():
    root = Path(__file__).resolve().parents[1]
    scenario_dirs = sorted(
        path
        for path in (root / "scenarios").iterdir()
        if path.is_dir()
        and (
            path.name.startswith(("native_", "evidence_"))
            or path.name == "verify_plan"
        )
        and (path / "scenario.json").exists()
    )

    for scenario_dir in scenario_dirs:
        name = scenario_dir.name
        scenario = json.loads(
            (scenario_dir / "scenario.json").read_text(encoding="utf-8")
        )
        if name.startswith("native_"):
            if name in {
                "native_machine_tv_recheck",
                "native_machine_tv_branch_call_recheck",
                "native_machine_tv_bounded_loop_recheck",
                "native_machine_tv_f64_recheck",
            }:
                audit_status = "BOUNDED MACHINE-TV"
            elif name == "native_object_accept":
                audit_status = "BOUNDED OBJECT-ACCEPT"
            elif name == "native_observations_recovery":
                audit_status = "BOUNDED RECOVERY"
            elif name in {
                "native_attempt",
                "native_composite_attempt",
                "native_refined_attempt",
                "native_refined_widened_attempt",
            }:
                audit_status = "BOUNDED NATIVE ATTEMPT"
            elif name == "native_check":
                audit_status = "BOUNDED CHECK"
            elif name.endswith("_accept"):
                audit_status = "BOUNDED ACCEPTANCE"
            else:
                audit_status = "BOUNDED RECHECK"
        elif name in {
            "evidence_accept_list",
            "evidence_acceptance_eval",
            "evidence_check_adapter",
            "evidence_check_attempt_acceptance",
            "verify_plan",
        }:
            audit_status = scenario["narrative"]["audit_status"]
        elif name in {"evidence_compare", "evidence_identity", "evidence_producer"}:
            audit_status = "DECLARED-EVIDENCE CHECK"
        else:
            audit_status = "REPRESENTATION-CHECK"

        narrative = scenario.get("narrative", {})
        moment = narrative.get("moment")
        result_message = scenario.get("result_message")
        intro = narrative.get("intro")
        assert narrative.get("audit_status") == audit_status, name
        assert isinstance(narrative.get("before"), str) and narrative["before"], name
        assert isinstance(narrative.get("after"), str) and narrative["after"], name
        assert isinstance(intro, list) and intro, name
        assert all(isinstance(line, str) and line for line in intro), name
        assert not any("ownership transfer" in line.lower() for line in intro), name
        assert isinstance(moment, str) and moment, name
        assert isinstance(result_message, str) and result_message.startswith("Result:"), name
        assert len(f"  Moment:        {moment}") <= 116, name
        assert len(f"  {result_message}") <= 62, name
        assert not any(
            phrase in result_message.lower()
            for phrase in ("trustless", "correct code proven", "bug caught", "proof")
        ), name

        report = render_cli_report(
            {
                "scenario": name,
                "scenario_name": scenario["name"],
                "overall_status": "PASS",
                "layers": {"l1_z3": {}},
                "proof_density": {"verified": 1, "total": 1, "percentage": 100},
                "narrative": narrative,
            }
        )
        assert f"Audit Status:  {audit_status}" in report, name
        assert f"Moment:        {moment}" in report, name
        assert "TRUSTLESS" not in report, name
        assert "Proof failure → Bug found" not in report, name

        if audit_status == "BOUNDED MACHINE-TV":
            assert "Register convention assumed" in moment, name
            assert "not verified ABI" in moment, name
            assert "object_translation_correspondence not performed" in moment, name
        if audit_status == "BOUNDED ACCEPTANCE":
            assert "One Core invocation" in moment, name
            assert "no universal ABI/runtime claim" in moment, name
        if audit_status == "BOUNDED OBJECT-ACCEPT":
            bounded_text = " ".join(
                [
                    scenario["description"],
                    narrative["after"],
                    narrative["moment"],
                    *intro,
                    scenario["harness_contract"]["intent"],
                    result_message,
                ]
            ).lower()
            for term in (
                "register convention",
                "assumed",
                "not validated",
                "abi",
                "runtime",
                "crt",
                "loader",
                "os exit-status",
                "universal object-tv",
                "no grade",
            ):
                assert term in bounded_text, (name, term)
            assert (
                "evidence reuse" in bounded_text
                or "evidence-reuse" in bounded_text
            ), name

        if name in {
            "native_machine_tv_bounded_loop_recheck",
            "native_machine_tv_f64_recheck",
            "native_object_accept",
        }:
            bounded_text = " ".join(
                [
                    scenario["description"],
                    narrative["after"],
                    narrative["moment"],
                    *intro,
                    scenario["harness_contract"]["intent"],
                    result_message,
                ]
            ).lower()
            assert "only bounded" in bounded_text or "only the bounded" in bounded_text
            assert all(
                phrase in bounded_text
                for phrase in (
                    "register convention",
                    "assumed",
                    "not validated",
                    "abi",
                    "runtime",
                    "crt",
                    "loader",
                    "os exit-status",
                    "universal object-tv",
                )
            ), name
            assert (
                "evidence reuse" in bounded_text
                or "evidence-reuse" in bounded_text
            ), name
            failed = render_cli_report(
                {
                    "scenario": name,
                    "scenario_name": scenario["name"],
                    "overall_status": "FAIL",
                    "layers": {"l1_z3": {}},
                    "proof_density": {"verified": 0, "total": 1, "percentage": 0},
                    "narrative": narrative,
                }
            )
            assert "Audit Status:  ATTENTION" in failed, name
            assert f"Audit Status:  {audit_status}" not in failed, name
            assert "TRUSTLESS" not in failed and "Correct code proven" not in failed


def test_cli_report_defaults_remain_unchanged_for_other_scenarios():
    report = render_cli_report(
        {
            "scenario": "ownership_transfer",
            "scenario_name": "Ownership Transfer",
            "overall_status": "PASS",
            "layers": {"l1_z3": {}},
            "proof_density": {"verified": 1, "total": 1, "percentage": 100},
        }
    )

    assert "Audit Status:  TRUSTLESS" in report
    assert "Moment:        Proof failure → Bug found" in report


def test_charter_gate_section_renders_statuses_and_highlights(tmp_path):
    report = render_scenario_markdown(
        {
            "scenario": "charter_gate_demo",
            "scenario_name": "Charter Gate Demo",
            "overall_status": "PASS",
            "proof_density": {},
            "layers": {},
            "charter_gate": {
                "entries": [
                    {
                        "step": "charter_pass",
                        "status": "ok",
                        "gate_status": "pass",
                        "lock_status": "ok",
                        "atoms": [
                            {
                                "name": "clamp_dose",
                                "charter": "specs/dosage.charter.mm",
                                "status": "ok",
                                "effective_grade": "G4",
                            }
                        ],
                    },
                    {
                        "step": "detect_edit",
                        "status": "ok",
                        "gate_status": "fail",
                        "lock_status": "mismatch",
                        "atoms": [
                            {
                                "name": "clamp_dose",
                                "charter": "specs/dosage.charter.mm",
                                "status": "unpinned",
                            }
                        ],
                    },
                ],
                "totals": {
                    "checks": 2,
                    "passed": 1,
                    "failed": 1,
                    "by_atom_status": {"ok": 1, "unpinned": 1},
                },
            },
        },
        tmp_path,
    )

    assert "## Charter Gate" in report
    assert "| Step | Entry status | Gate status | Lock status | Atom statuses |" in report
    assert "| charter_pass | ok | pass | ok | clamp_dose (`specs/dosage.charter.mm`): ok (G4) |" in report
    assert "| detect_edit | ok | fail | mismatch | clamp_dose (`specs/dosage.charter.mm`): unpinned |" in report
    assert "- Highlights: 1/2 checks passed · 1 failed · ok: 1 · unpinned: 1" in report


def test_old_result_does_not_render_charter_gate_section(tmp_path):
    report = render_scenario_markdown(
        {
            "scenario": "legacy",
            "overall_status": "PASS",
            "proof_density": {},
            "layers": {},
        },
        tmp_path,
    )

    assert "## Charter Gate" not in report


def test_negative_controls_section_renders_counts_and_surviving_ids(tmp_path):
    report = render_scenario_markdown(
        {
            "scenario": "negative_controls_demo",
            "scenario_name": "Negative Controls",
            "overall_status": "PASS",
            "proof_density": {},
            "layers": {},
            "negative_controls": {
                "entries": [
                    {
                        "step": "controls_weak",
                        "status": "weak",
                        "atoms": [
                            {
                                "name": "next_dose",
                                "status": "weak",
                                "tested": 2,
                                "killed": 1,
                                "survived": 1,
                                "unanalyzable": 0,
                                "surviving": ["constant:1->0@1"],
                            }
                        ],
                    },
                    {
                        "step": "controls_strong",
                        "status": "discriminating",
                        "atoms": [
                            {
                                "name": "next_dose",
                                "status": "discriminating",
                                "tested": 2,
                                "killed": 2,
                                "survived": 0,
                                "unanalyzable": 0,
                                "surviving": [],
                            }
                        ],
                    },
                ],
                "totals": {
                    "steps": 2,
                    "by_step_status": {"discriminating": 1, "weak": 1},
                    "atoms": 2,
                    "by_atom_status": {"discriminating": 1, "weak": 1},
                    "surviving_mutants": 1,
                },
            },
        },
        tmp_path,
    )

    assert "## Negative Controls" in report
    assert (
        "| Step | Step status | Atom | Atom status | Tested | Killed | "
        "Survived | Unanalyzable | Surviving mutants |" in report
    )
    assert (
        "| controls_weak | weak | next_dose | weak | 2 | 1 | 1 | 0 | "
        "`constant:1->0@1` |" in report
    )
    assert (
        "- Totals: 2 steps (discriminating: 1, weak: 1); 2 atoms "
        "(discriminating: 1, weak: 1); 1 surviving mutant." in report
    )


def test_absent_negative_controls_section_does_not_change_old_report(tmp_path):
    data = {
        "scenario": "legacy",
        "overall_status": "PASS",
        "proof_density": {},
        "layers": {},
    }
    assert render_negative_controls_markdown(data) == ""
    report = render_scenario_markdown(data, tmp_path)
    assert "## Negative Controls" not in report


def test_empty_negative_controls_section_is_rendered_when_present():
    section = render_negative_controls_markdown({
        "negative_controls": {
            "entries": [],
            "totals": {
                "steps": 0,
                "by_step_status": {},
                "atoms": 0,
                "by_atom_status": {},
                "surviving_mutants": 0,
            },
        }
    })
    assert "## Negative Controls" in section
    assert "No negative-control checks were recorded." in section


def test_charter_gate_demo_has_a_nonempty_before_after_diff():
    root = Path(__file__).resolve().parents[1]
    before_path, after_path = scenario_code_paths(root, "charter_gate_demo")

    assert before_path.relative_to(root).as_posix() == (
        "scenarios/charter_gate_demo/project/weakened_ensures.mm"
    )
    assert after_path.relative_to(root).as_posix() == (
        "scenarios/charter_gate_demo/project/correct.mm"
    )
    report = bug_detection_moment(
        {
            "scenario": "charter_gate_demo",
            "layers": {
                "l1_z3": {
                    "steps": [
                        {
                            "id": "detect_weakened_ensures",
                            "status": "REJECTED",
                            "expect_failure": True,
                            "command": "mumei charter --json",
                            "stdout": "post_weakened",
                        }
                    ]
                }
            },
        },
        root,
        "### Evidence",
        "####",
    )

    assert "#### BEFORE → AFTER diff" in report
    assert "#### mumei charter → CHARTER REJECTED" in report


def test_negative_controls_demo_diff_uses_weak_and_strong_specs():
    root = Path(__file__).resolve().parents[1]
    before_path, after_path = scenario_code_paths(root, "negative_controls_demo")

    assert before_path.relative_to(root).as_posix() == (
        "scenarios/negative_controls_demo/project/weak_spec.mm"
    )
    assert after_path.relative_to(root).as_posix() == (
        "scenarios/negative_controls_demo/project/strong_spec.mm"
    )
    report = bug_detection_moment(
        {
            "scenario": "negative_controls_demo",
            "layers": {
                "l1_z3": {
                    "steps": [
                        {
                            "id": "controls_weak",
                            "status": "REJECTED",
                            "expect_failure": True,
                            "command": "mumei controls weak_spec.mm --json",
                            "stdout": "constant:1->0@1",
                        }
                    ]
                }
            },
        },
        root,
        "### Evidence",
        "####",
    )
    assert "#### BEFORE → AFTER diff" in report
    assert "#### mumei controls → WEAK SPEC DETECTED" in report


@pytest.mark.parametrize(
    ("command", "label"),
    [
        ("mumei verify weak_spec.mm", "mumei verify → BUG DETECTED"),
        ("mumei controls weak_spec.mm --json", "mumei controls → WEAK SPEC DETECTED"),
        ("mumei claims weak_spec.mm --controls", "mumei claims → GATE REJECTED"),
        ("mumei charter weak_spec.mm --json", "mumei charter → CHARTER REJECTED"),
        (
            "python -m agent observe-tests --spec wrong.json",
            "observe-tests → TEST OBSERVATIONS REJECTED",
        ),
        (
            "mumei observe aligned.mm harvest.json --json",
            "mumei observe → TEST OBSERVATIONS REJECTED",
        ),
        (
            "mumei verify weak_spec.mm && mumei charter check weak_spec.mm",
            "mumei charter → CHARTER REJECTED",
        ),
    ],
)
def test_rejected_step_labels_follow_the_mumei_subcommand(tmp_path, command, label):
    root = Path(__file__).resolve().parents[1]
    report = bug_detection_moment(
        {
            "scenario": "legacy",
            "layers": {
                "l1_z3": {
                    "steps": [
                        {
                            "id": "rejected_step",
                            "status": "REJECTED",
                            "expect_failure": True,
                            "command": command,
                            "stdout": "expected rejection",
                        }
                    ]
                }
            },
        },
        root,
        "### Evidence",
        "####",
    )

    assert f"#### {label}" in report


def test_rejected_step_label_reads_the_executed_command_from_its_log(tmp_path):
    run_dir = tmp_path / "reports" / "legacy" / "run"
    run_dir.mkdir(parents=True)
    state_file = run_dir / "harness_state.json"
    state_file.write_text("{}", encoding="utf-8")
    (run_dir / "rejected_step.log").write_text(
        "$ /opt/mumei/target/release/mumei claims weak_spec.mm --controls\n",
        encoding="utf-8",
    )

    report = bug_detection_moment(
        {
            "scenario": "legacy",
            "harness_state_file": str(state_file),
            "layers": {
                "l1_z3": {
                    "steps": [
                        {
                            "id": "rejected_step",
                            "status": "REJECTED",
                            "expect_failure": True,
                            "output_file": "rejected_step.log",
                            "command": "mumei verify weak_spec.mm",
                            "stdout": "expected rejection",
                        }
                    ]
                }
            },
        },
        Path(__file__).resolve().parents[1],
        "### Evidence",
        "####",
    )

    assert "#### mumei claims → GATE REJECTED" in report


def test_verify_rejection_report_matches_the_legacy_label():
    root = Path(__file__).resolve().parents[1]

    def render(command=None):
        step = {
            "id": "detect_bug",
            "status": "REJECTED",
            "expect_failure": True,
            "stdout": "Verification failed",
        }
        if command is not None:
            step["command"] = command
        return bug_detection_moment(
            {
                "scenario": "legacy",
                "layers": {"l1_z3": {"steps": [step]}},
            },
            root,
            "### Evidence",
            "####",
        )

    legacy_report = render()
    assert legacy_report == render("mumei verify weak_spec.mm")
    assert "#### mumei verify → BUG DETECTED" in legacy_report


def test_write_highlights_adds_one_charter_gate_line(tmp_path):
    reports = tmp_path / "reports"
    result_dir = reports / "charter_gate_demo" / "20260101T000000Z"
    result_dir.mkdir(parents=True)
    (result_dir / "result.json").write_text(
        json.dumps({
            "scenario": "charter_gate_demo",
            "scenario_name": "Charter Gate Demo",
            "overall_status": "PASS",
            "proof_density": {},
            "layers": {},
            "charter_gate": {
                "entries": [],
                "totals": {
                    "checks": 1,
                    "passed": 1,
                    "failed": 0,
                    "by_atom_status": {"ok": 1},
                },
            },
        }),
        encoding="utf-8",
    )
    output = tmp_path / "highlights.md"

    assert charter_gate_label({
        "charter_gate": {
            "totals": {
                "checks": 1,
                "passed": 1,
                "failed": 0,
                "by_atom_status": {"ok": 1},
            }
        }
    }) == "1/1 checks passed · 0 failed · ok: 1"
    assert write_highlights(
        tmp_path,
        reports,
        output,
        ["charter_gate_demo"],
        False,
    ) == 0
    assert output.read_text(encoding="utf-8").count("- Charter Gate:") == 1


def test_claim_book_summary_labels():
    assert claim_book_label({}) == "N/A"
    assert claim_book_label({
        "claim_book": {"entries": [{"status": "unavailable"}], "totals": {}},
    }) == "unavailable"
    assert claim_book_label({
        "claim_book": {"entries": [{"status": "skipped"}], "totals": {}},
    }) == "skipped"
    assert claim_book_label({
        "claim_book": {
            "entries": [{"status": "ok"}],
            "totals": {
                "total": 4,
                "by_effective_grade": {"G4": 2, "G5": 1},
                "by_freshness": {"drifted": 1, "uncertified": 2},
            },
        },
    }) == "3/4 machine-sealed · 1 drifted · 2 uncertified"


def test_dashboard_claim_book_labels_match(tmp_path, monkeypatch):
    streamlit = types.ModuleType("streamlit")
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    app_path = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    spec = importlib.util.spec_from_file_location("claim_book_dashboard_app", app_path)
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    charter_index = app.SCENARIO_ORDER.index("charter_gate_demo")
    assert app.SCENARIO_ORDER[charter_index - 1 : charter_index + 4] == [
        "arklib_style_audit",
        "charter_gate_demo",
        "negative_controls_demo",
        "test_observation_demo",
        "self_correction_demo",
    ]
    makefile = Path(__file__).resolve().parents[1] / "Makefile"
    scenario_line = next(
        line for line in makefile.read_text(encoding="utf-8").splitlines()
        if line.startswith("SCENARIOS :=")
    )
    makefile_order = scenario_line.split(":=", 1)[1].split()
    assert SCENARIO_ORDER == makefile_order
    assert app.SCENARIO_ORDER == makefile_order
    optional_line = next(line for line in makefile.read_text(encoding="utf-8").splitlines()
                         if line.startswith("OPTIONAL_SCENARIOS :="))
    assert OPTIONAL_SCENARIOS == app.OPTIONAL_SCENARIOS == optional_line.split(":=", 1)[1].split()
    assert {"rust_bindings", "sol_bindings", "ts_bindings"} <= set(OPTIONAL_SCENARIOS)
    assert {
        "native_machine_tv_bounded_loop_recheck",
        "native_machine_tv_f64_recheck",
        "native_object_accept",
        "summaries_reuse_attempt",
        "verify_plan",
    } <= set(OPTIONAL_SCENARIOS)
    assert app.scenario_names().index("record_execution_demo") == len(SCENARIO_ORDER)
    assert app.scenario_names().count("record_execution_demo") == 1
    assert len(app.scenario_names()) == len(set(app.scenario_names()))
    data = {
        "claim_book": {
            "entries": [{"status": "ok"}],
            "totals": {
                "total": 3,
                "by_effective_grade": {"G4": 2, "G5": 1},
                "by_freshness": {"drifted": 1, "uncertified": 0},
            },
        },
    }
    expected = "3/3 machine-sealed · 1 drifted · 0 uncertified"

    assert cli_claim_book_label(data) == expected
    assert app.claim_book_label(data) == expected


def test_record_operation_before_after_uses_its_local_contracts():
    root = Path(__file__).resolve().parents[1]
    before, after = scenario_code_paths(root, "record_execution_demo")
    assert before.name == "broken_contract.mm" and after.name == "local_contract.mm"
    assert "body: { version };" in before.read_text()
    assert "body: { version + 1 };" in after.read_text()


@pytest.mark.parametrize("step", ["missing_organization", "missing_ownership", "changed_identity", "direct_write"])
def test_record_host_highlights_do_not_reuse_the_local_arithmetic_proof(step):
    root = Path(__file__).resolve().parents[1]
    data = {"scenario": "record_execution_demo", "layers": {"l2_agent": {"steps": [
        {"id": f"detect_{step}", "status": "REJECTED", "expect_failure": True},
    ]}}}
    report = bug_detection_moment(data, root, "## Highlights", "###")
    assert "Finite Python host-variant observation (not formal proof)" in report
    assert f"detect_{step}" in report
    assert "broken_contract.mm" not in report and "local_contract.mm" not in report
    assert "BEFORE → AFTER diff" not in report and "LLM" not in report


def test_record_local_rejection_highlight_keeps_only_the_local_contract_diff():
    root = Path(__file__).resolve().parents[1]
    data = {"scenario": "record_execution_demo", "layers": {"l1_z3": {"steps": [
        {"id": "reject_broken_local", "status": "REJECTED", "expect_failure": True},
    ]}}}
    report = bug_detection_moment(data, root, "## Highlights", "###")
    assert "broken_contract.mm" in report and "local_contract.mm" in report
    assert "BEFORE → AFTER diff" in report
    assert "Finite Python host-variant observation" not in report


def test_write_summary_includes_claim_book_label(tmp_path):
    reports = tmp_path / "reports"
    result_dir = reports / "medical_device" / "20260101T000000Z"
    result_dir.mkdir(parents=True)
    (result_dir / "result.json").write_text(
        json.dumps({
            "scenario": "medical_device",
            "overall_status": "PASS",
            "proof_density": {"verified": 3, "total": 3, "percentage": 100},
            "layers": {},
            "claim_book": {
                "entries": [{"status": "ok"}],
                "totals": {
                    "total": 3,
                    "by_effective_grade": {"G4": 3},
                    "by_freshness": {"drifted": 0, "uncertified": 0},
                },
            },
        }),
        encoding="utf-8",
    )
    output = tmp_path / "summary.md"

    assert write_summary(reports, output, ["medical_device"], False) == 0

    summary = output.read_text(encoding="utf-8")
    assert "| Claim Book |" in summary
    assert "3/3 machine-sealed · 0 drifted · 0 uncertified" in summary


def test_test_observations_section_renders_contradictions_and_totals():
    section = render_test_observations_markdown({
        "test_observations": {
            "entries": [{
                "step": "observe_wrong",
                "status": "ok",
                "verdict_totals": {
                    "consistent": 2,
                    "contradicts_ensures": 1,
                    "requires_admits_rejected": 1,
                },
                "contradictions": [{
                    "target": "late_fee",
                    "test": "test_late_fee_example",
                    "file": "test_late_fee.py",
                    "line": 6,
                    "verdict": "contradicts_ensures",
                }],
            }, {
                "step": "observe_aligned",
                "status": "ok",
                "verdict_totals": {"consistent": 4, "rejection_explained": 2},
                "contradictions": [],
            }],
            "totals": {
                "steps": 1,
                "verdicts": {
                    "consistent": 2,
                    "contradicts_ensures": 1,
                    "requires_admits_rejected": 1,
                },
                "contradictions": 1,
            },
        }
    })

    assert "## Test Observations" in section
    table_lines = section.splitlines()
    header_index = table_lines.index("| Step | Status | Verdict totals | Contradictions |")
    table_row_indices = [
        index for index, line in enumerate(table_lines)
        if line.startswith("|")
    ]
    assert table_row_indices == list(
        range(header_index, table_row_indices[-1] + 1)
    )
    assert "| observe_wrong | ok | consistent: 2, contradicts_ensures: 1, requires_admits_rejected: 1 | 1 |" in section
    assert "| observe_aligned | ok | consistent: 4, rejection_explained: 2 | 0 |" in section
    assert "### Contradictions in observe_wrong" in section
    assert "- `late_fee` / `test_late_fee_example` (`test_late_fee.py:6`): `contradicts_ensures`" in section
    assert table_row_indices[-1] < table_lines.index("### Contradictions in observe_wrong")
    assert "1 contradicting results." in section


def test_test_observations_section_renders_all_consistent_data():
    section = render_test_observations_markdown({
        "test_observations": {
            "entries": [{
                "step": "observe_aligned",
                "status": "ok",
                "verdict_totals": {"consistent": 4, "rejection_explained": 2},
                "contradictions": [],
            }],
            "totals": {
                "steps": 1,
                "verdicts": {"consistent": 4, "rejection_explained": 2},
                "contradictions": 0,
            },
        }
    })

    assert "| observe_aligned | ok | consistent: 4, rejection_explained: 2 | 0 |" in section
    assert "No contradictions or admitted rejections were recorded." in section


def test_missing_test_observations_section_is_not_rendered(tmp_path):
    data = {
        "scenario": "legacy",
        "overall_status": "PASS",
        "proof_density": {},
        "layers": {},
    }

    assert render_test_observations_markdown(data) == ""
    assert "## Test Observations" not in render_scenario_markdown(data, tmp_path)
