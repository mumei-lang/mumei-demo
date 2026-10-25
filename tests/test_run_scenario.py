"""Tests for the Python heredoc embedded in scripts/run_scenario.sh."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_scenario.sh"


def _load_runner() -> dict:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("<<'PY'") + len("<<'PY'")
    end = text.index("\nPY\n", start)
    namespace: dict = {"__name__": "test_run_scenario"}
    exec(compile(text[start:end], str(SCRIPT), "exec"), namespace)
    return namespace


def _book(
    claims: list[dict],
    *,
    by_effective_grade: dict[str, int] | None = None,
    by_freshness: dict[str, int] | None = None,
) -> dict:
    grades = {grade: 0 for grade in ("G0", "G1", "G2", "G3", "G4", "G5")}
    freshness = {"fresh": 0, "drifted": 0, "uncertified": 0}
    grades.update(by_effective_grade or {})
    freshness.update(by_freshness or {})
    return {
        "summary": {
            "by_effective_grade": grades,
            "by_freshness": freshness,
            "total": len(claims),
        },
        "certificate_integrity": "match",
        "claims": claims,
    }


def _make_mumei_stub(root: Path) -> Path:
    stub = root / "mumei-bin"
    stub.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
if args and args[0] == "verify":
    cert = Path(args[args.index("--output") + 1])
    cert.parent.mkdir(parents=True, exist_ok=True)
    cert.write_text(json.dumps({"fixture": True}), encoding="utf-8")
    print("Verification passed")
    raise SystemExit(int(os.environ.get("MUMEI_STUB_VERIFY_EXIT", "0")))
if args and args[0] == "charter":
    print(os.environ.get("MUMEI_STUB_CHARTER_STDOUT", ""))
    raise SystemExit(int(os.environ.get("MUMEI_STUB_CHARTER_EXIT", "0")))
if args and args[0] == "controls":
    print(os.environ.get("MUMEI_STUB_CONTROLS_STDOUT", ""))
    raise SystemExit(int(os.environ.get("MUMEI_STUB_CONTROLS_EXIT", "0")))
if args and args[0] == "observe":
    print(os.environ.get("MUMEI_STUB_OBSERVE_REPORT", "{}"))
    raise SystemExit(int(os.environ.get("MUMEI_STUB_OBSERVE_EXIT", "0")))
if args and args[0] == "observe-tests":
    report_path = Path(args[args.index("--output") + 1])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        os.environ.get("MUMEI_STUB_OBSERVE_REPORT", "{}"),
        encoding="utf-8",
    )
    raise SystemExit(int(os.environ.get("MUMEI_STUB_OBSERVE_EXIT", "0")))
if not args or args[0] != "claims":
    print("unsupported command", file=sys.stderr)
    raise SystemExit(2)

marker = os.environ.get("MUMEI_STUB_CLAIMS_MARKER")
if marker:
    with Path(marker).open("a", encoding="utf-8") as handle:
        handle.write("claims\\\\n")
exit_code = int(os.environ.get("MUMEI_STUB_CLAIMS_EXIT", "0"))
if exit_code:
    print(os.environ.get("MUMEI_STUB_CLAIMS_STDERR", "fixture claims failed"), file=sys.stderr)
    print("second diagnostic", file=sys.stderr)
    raise SystemExit(exit_code)

output_dir = Path(args[args.index("--out-dir") + 1])
output_dir.mkdir(parents=True, exist_ok=True)
claim_file = output_dir / "claimbook.json"
mode = os.environ.get("MUMEI_STUB_CLAIMS_MODE", "fixture")
if mode == "missing":
    raise SystemExit(0)
if mode == "invalid":
    claim_file.write_text("not json", encoding="utf-8")
    raise SystemExit(0)

source = Path(args[1])
fixture_dir = Path(os.environ["MUMEI_STUB_FIXTURE_DIR"])
fixture = fixture_dir / f"{source.stem}.json"
claim_file.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
""",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def _run_scenario(
    tmp_path: Path,
    monkeypatch,
    claim_books: list[dict | None],
    *,
    verify_exit: int = 0,
    claims_exit: int = 0,
    claims_mode: str = "fixture",
    fixtures: dict[str, dict] | None = None,
    preseed_stale_claimbook: bool = False,
    scenario_steps: list[dict] | None = None,
    charter_stdout: str = "",
    charter_exit: int = 0,
    controls_stdout: str = "",
    controls_exit: int = 0,
    claims_stderr: str = "fixture claims failed",
    narrative: dict | None = None,
) -> tuple[int, dict, Path]:
    root = tmp_path / "root"
    scenario_name = "claim_book_test"
    scenario_dir = root / "scenarios" / scenario_name
    scenario_dir.mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "scripts" / "generate_report.py").write_text("", encoding="utf-8")
    fixture_dir = root / "fixtures"
    fixture_dir.mkdir()
    for name, payload in (fixtures or {}).items():
        (fixture_dir / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")

    steps = list(scenario_steps or [])
    if scenario_steps is None:
        for index, claim_book in enumerate(claim_books):
            step = {
                "id": f"verify_{index}",
                "name": f"Verify {index}",
                "command": (
                    f"{{mumei_bin}} verify {{root_dir}}/source_{index}.mm "
                    f"--proof-cert --output {{output_dir}}/certificate_{index}.json"
                ),
                "expected_exit": 0,
                "expected_patterns": ["Verification passed"],
                "artifacts": [f"certificate_{index}.json"],
            }
            if claim_book is not None:
                step["claim_book"] = claim_book
            steps.append(step)
    scenario = {
        "name": "Claim Book Test",
        "layers": ["l1_z3"],
        "l1_z3": {"steps": steps},
    }
    if narrative is not None:
        scenario["narrative"] = narrative
    (scenario_dir / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")

    stub = _make_mumei_stub(root)
    marker = tmp_path / "claims-invoked.txt"
    monkeypatch.setenv("MUMEI_STUB_CLAIMS_MARKER", str(marker))
    monkeypatch.setenv("MUMEI_STUB_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("MUMEI_STUB_VERIFY_EXIT", str(verify_exit))
    monkeypatch.setenv("MUMEI_STUB_CHARTER_STDOUT", charter_stdout)
    monkeypatch.setenv("MUMEI_STUB_CHARTER_EXIT", str(charter_exit))
    monkeypatch.setenv("MUMEI_STUB_CONTROLS_STDOUT", controls_stdout)
    monkeypatch.setenv("MUMEI_STUB_CONTROLS_EXIT", str(controls_exit))
    monkeypatch.setenv("MUMEI_STUB_CLAIMS_EXIT", str(claims_exit))
    monkeypatch.setenv("MUMEI_STUB_CLAIMS_MODE", claims_mode)
    monkeypatch.setenv("MUMEI_STUB_CLAIMS_STDERR", claims_stderr)

    runner = _load_runner()
    if preseed_stale_claimbook:
        fixed_now = runner["datetime"](
            2026,
            1,
            1,
            tzinfo=runner["timezone"].utc,
        )

        class FixedDateTime:
            @staticmethod
            def now(tz):
                return fixed_now.astimezone(tz)

        runner["datetime"] = FixedDateTime
        timestamp = fixed_now.strftime("%Y%m%dT%H%M%SZ")
        stale_file = (
            root
            / "reports"
            / scenario_name
            / timestamp
            / "claimbook"
            / "verify_0"
            / "claimbook.json"
        )
        stale_file.parent.mkdir(parents=True, exist_ok=True)
        stale_file.write_text(
            json.dumps(_book([{"effective_grade": "G5", "effective_grade_complete": True}])),
            encoding="utf-8",
        )
    exit_code = runner["main"]([
        str(root),
        scenario_name,
        "--mumei-bin",
        str(stub),
    ])
    result_path = root / "reports" / scenario_name / "latest" / "result.json"
    return exit_code, json.loads(result_path.read_text(encoding="utf-8")), marker


def test_generated_code_from_spec_has_no_return_statement():
    ns = _load_runner()
    spec = {
        "name": "safe_transfer",
        "inputs": [
            {"name": "sender_balance", "type": "i64"},
            {"name": "amount", "type": "i64"},
        ],
        "requires": "sender_balance >= amount",
        "ensures": "result == sender_balance - amount",
        "return_type": "i64",
    }
    code = ns["generated_code_from_spec"](spec)
    assert "return" not in code
    assert "sender_balance - amount" in code


def test_claim_book_ok_entry_has_counts_and_lowest_grade(tmp_path, monkeypatch):
    book = _book(
        [
            {"effective_grade": "G0", "effective_grade_complete": False},
            {"effective_grade": "G4", "effective_grade_complete": True},
            {"effective_grade": "G5", "effective_grade_complete": True},
        ],
        by_effective_grade={"G0": 1, "G4": 1, "G5": 1},
        by_freshness={"fresh": 3},
    )
    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [{"source": "{root_dir}/source_0.mm", "cert": "certificate_0.json"}],
        fixtures={"source_0": book},
    )

    assert exit_code == 0
    assert result["overall_status"] == "PASS"
    entry = result["claim_book"]["entries"][0]
    assert entry == {
        "step": "verify_0",
        "status": "ok",
        "source": str(tmp_path / "root" / "source_0.mm"),
        "cert": "certificate_0.json",
        "file": "claimbook/verify_0/claimbook.json",
        "exit_code": 0,
        "total": 3,
        "by_effective_grade": {
            "G0": 1,
            "G1": 0,
            "G2": 0,
            "G3": 0,
            "G4": 1,
            "G5": 1,
        },
        "by_freshness": {"fresh": 3, "drifted": 0, "uncertified": 0},
        "certificate_integrity": "match",
        "incomplete": 1,
        "lowest_effective_grade": "G0",
    }
    assert result["claim_book"]["totals"]["lowest_effective_grade"] == "G0"
    assert "claim_book" in json.loads(
        (Path(result["harness_state_file"])).read_text(encoding="utf-8")
    )
    assert not any(
        path.startswith("claimbook/")
        for path in result["artifact_payloads"]
    )


def _charter_report(
    status: str = "fail",
    atom_status: str = "post_weakened",
    lock_status: str = "ok",
) -> dict:
    return {
        "schema": "mumei.charter-report/v1",
        "status": status,
        "lock": {"status": lock_status},
        "atoms": [
            {
                "name": "clamp_dose",
                "charter": "specs/dosage.charter.mm",
                "status": atom_status,
                "effective_grade": "G1",
            }
        ],
    }


def _controls_report(
    atom_status: str = "weak",
    *,
    report_status: str | None = None,
) -> dict:
    weak = atom_status == "weak"
    return {
        "schema": "mumei.controls-report/v1",
        "status": report_status or ("fail" if weak else "pass"),
        "input": "dosage.mm",
        "atoms": [
            {
                "name": "next_dose",
                "status": atom_status,
                "tested": 2,
                "killed": 1 if weak else 2,
                "survived": 1 if weak else 0,
                "unanalyzable": 0,
                "mutants": [
                    {"id": "op-flip:Add->Sub@0", "outcome": "killed"},
                    {
                        "id": "constant:1->0@1",
                        "outcome": "survived" if weak else "killed",
                    },
                ],
            }
        ],
        "totals": {
            "atoms": 1,
            "by_status": {atom_status: 1},
            "mutants": 2,
            "killed": 1 if weak else 2,
            "survived": 1 if weak else 0,
            "unanalyzable": 0,
        },
    }


def test_negative_controls_parser_normalizes_weak_and_discriminating_reports():
    parse_entry = _load_runner()["parse_negative_controls_entry"]
    weak = parse_entry("controls_weak", "REJECTED", json.dumps(_controls_report()))
    strong = parse_entry(
        "controls_strong",
        "PASS",
        json.dumps(_controls_report("discriminating")),
    )

    assert weak == {
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
    }
    assert strong["status"] == "discriminating"
    assert strong["atoms"][0]["surviving"] == []


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        json.dumps({**_controls_report(), "schema": "wrong/v1"}),
        json.dumps({**_controls_report(), "status": []}),
        json.dumps({"schema": "mumei.controls-report/v1", "status": "fail"}),
        json.dumps({
            **_controls_report(),
            "atoms": ["not an atom object"],
        }),
        json.dumps({
            **_controls_report(),
            "atoms": [{**_controls_report()["atoms"][0], "status": []}],
        }),
        json.dumps({
            **_controls_report(),
            "atoms": [{**_controls_report()["atoms"][0], "tested": "2"}],
        }),
        json.dumps({
            **_controls_report(),
            "atoms": [{**_controls_report()["atoms"][0], "killed": 0, "survived": 0}],
        }),
        json.dumps({
            **_controls_report(),
            "atoms": [{
                key: value
                for key, value in _controls_report()["atoms"][0].items()
                if key != "killed"
            }],
        }),
    ],
    ids=[
        "invalid-json",
        "wrong-schema",
        "bad-report-status",
        "missing-atoms",
        "non-object-atom",
        "bad-atom-status",
        "bad-counts",
        "inconsistent-counts",
        "missing-field",
    ],
)
def test_malformed_negative_controls_report_fails_step_and_scenario(
    tmp_path,
    monkeypatch,
    payload,
):
    step = {
        "id": "controls_weak",
        "command": "{mumei_bin} controls weak_spec.mm --json",
        "expected_exit": 1,
        "expect_failure": True,
        "negative_controls": True,
    }
    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
        controls_stdout=payload,
        controls_exit=1,
    )

    step_result = result["layers"]["l1_z3"]["steps"][0]
    assert exit_code == 1
    assert result["overall_status"] == "FAIL"
    assert step_result["status"] == "FAIL"
    assert step_result["detail"].startswith("negative controls report unavailable:")
    assert result["negative_controls"]["entries"][0]["status"] == "unavailable"


def test_negative_controls_totals_count_steps_atoms_and_survivors():
    runner = _load_runner()
    weak = runner["parse_negative_controls_entry"](
        "controls_weak",
        "REJECTED",
        json.dumps(_controls_report()),
    )
    strong = runner["parse_negative_controls_entry"](
        "controls_strong",
        "PASS",
        json.dumps(_controls_report("discriminating")),
    )
    totals = runner["negative_controls_totals"]([
        weak,
        strong,
        {"step": "controls_skipped", "status": "skipped", "atoms": []},
    ])

    assert totals == {
        "steps": 3,
        "by_step_status": {
            "discriminating": 1,
            "skipped": 1,
            "weak": 1,
        },
        "atoms": 2,
        "by_atom_status": {"discriminating": 1, "weak": 1},
        "surviving_mutants": 1,
    }


def _observation_report(results: list[dict] | None = None) -> dict:
    return {
        "schema": "mumei.observation-check/v1",
        "results": results or [],
    }


def test_test_observations_parser_records_verdict_totals_and_contradictions(tmp_path):
    report_path = tmp_path / "observations.json"
    report_path.write_text(json.dumps(_observation_report([
        {
            "target": "late_fee",
            "test": "test_example",
            "file": "test_late_fee.py",
            "line": 12,
            "verdict": "contradicts_ensures",
        },
        {
            "target": "late_fee",
            "test": "test_rejects",
            "file": "test_late_fee.py",
            "line": 18,
            "verdict": "requires_admits_rejected",
        },
        {"verdict": "consistent"},
    ])), encoding="utf-8")

    entry = _load_runner()["parse_test_observations_entry"](
        "observe_wrong",
        "REJECTED",
        report_path,
        {},
    )

    assert entry["status"] == "ok"
    assert entry["verdict_totals"] == {
        "consistent": 1,
        "contradicts_ensures": 1,
        "inconclusive": 0,
        "not_checked": 0,
        "outside_requires": 0,
        "rejection_explained": 0,
        "requires_admits_rejected": 1,
    }
    assert entry["contradictions"] == [
        {
            "target": "late_fee",
            "test": "test_example",
            "file": "test_late_fee.py",
            "line": 12,
            "verdict": "contradicts_ensures",
        },
        {
            "target": "late_fee",
            "test": "test_rejects",
            "file": "test_late_fee.py",
            "line": 18,
            "verdict": "requires_admits_rejected",
        },
    ]


def test_unknown_test_observation_verdict_fails_without_expected_totals(tmp_path):
    report_path = tmp_path / "observations.json"
    report_path.write_text(
        json.dumps(_observation_report([{"verdict": "future_verdict"}])),
        encoding="utf-8",
    )

    entry = _load_runner()["parse_test_observations_entry"](
        "observe",
        "PASS",
        report_path,
        {},
    )

    assert entry["status"] == "unavailable"
    assert entry["detail"] == "unknown test observation verdict 'future_verdict'"


def test_known_test_observation_verdicts_pass_without_expected_totals(tmp_path):
    report_path = tmp_path / "observations.json"
    report_path.write_text(
        json.dumps(_observation_report([
            {"verdict": "consistent"},
            {"verdict": "rejection_explained"},
        ])),
        encoding="utf-8",
    )

    entry = _load_runner()["parse_test_observations_entry"](
        "observe",
        "PASS",
        report_path,
        {},
    )

    assert entry["status"] == "ok"
    assert entry["verdict_totals"]["consistent"] == 1
    assert entry["verdict_totals"]["rejection_explained"] == 1


@pytest.mark.parametrize(
    ("payload", "expected_detail"),
    [
        (None, "cannot read test observations report"),
        ("not json", "JSON is invalid"),
        (json.dumps({"schema": "wrong/v1", "results": []}), "unsupported"),
        (json.dumps({"schema": "mumei.observation-check/v1"}), "results must be an array"),
    ],
    ids=["missing-file", "bad-json", "wrong-schema", "missing-results"],
)
def test_unavailable_test_observation_reports(tmp_path, payload, expected_detail):
    report_path = tmp_path / "observations.json"
    if payload is not None:
        report_path.write_text(payload, encoding="utf-8")

    entry = _load_runner()["parse_test_observations_entry"](
        "observe",
        "PASS",
        report_path,
        {},
    )

    assert entry["status"] == "unavailable"
    assert expected_detail in entry["detail"]


def test_test_observations_totals_count_verdicts_and_steps():
    totals = _load_runner()["test_observations_totals"]([
        {
            "status": "ok",
            "verdict_totals": {"consistent": 2, "contradicts_ensures": 1},
            "contradictions": [{"verdict": "contradicts_ensures"}],
        },
        {
            "status": "failed",
            "verdict_totals": {"consistent": 1, "requires_admits_rejected": 1},
            "contradictions": [{"verdict": "requires_admits_rejected"}],
        },
    ])

    assert totals == {
        "steps": 2,
        "by_step_status": {"failed": 1, "ok": 1},
        "verdicts": {
            "consistent": 3,
            "contradicts_ensures": 1,
            "requires_admits_rejected": 1,
        },
        "contradictions": 2,
    }


def test_wrong_test_observation_gate_fails_without_expected_verdicts(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MUMEI_STUB_OBSERVE_REPORT",
        json.dumps(_observation_report([{"target": "late_fee", "test": "example", "verdict": "consistent"}])),
    )
    monkeypatch.setenv("MUMEI_STUB_OBSERVE_EXIT", "1")
    step = {
        "id": "observe_wrong",
        "command": "{mumei_bin} observe-tests --output {output_dir}/observations.json",
        "expected_exit": 1,
        "expect_failure": True,
        "test_observations": {
            "report": "observations.json",
            "expected_results": [
                {
                    "target": "late_fee",
                    "test": "example",
                    "file_suffix": "test_late_fee.py",
                    "verdict": "contradicts_ensures",
                },
                {
                    "target": "late_fee",
                    "test": "rejects",
                    "file_suffix": "test_late_fee.py",
                    "verdict": "requires_admits_rejected",
                },
            ],
        },
    }
    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
    )

    step_result = result["layers"]["l1_z3"]["steps"][0]
    assert exit_code == 1
    assert step_result["status"] == "FAIL"
    assert "missing expected observation" in step_result["detail"]


def test_aligned_test_observation_gate_fails_on_contradiction(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MUMEI_STUB_OBSERVE_REPORT",
        json.dumps(_observation_report([
            {"target": "late_fee", "test": "example", "verdict": "contradicts_ensures"}
        ])),
    )
    step = {
        "id": "observe_aligned",
        "command": "{mumei_bin} observe-tests --output {output_dir}/observations.json",
        "expected_exit": 0,
        "test_observations": {
            "report": "observations.json",
            "forbidden_verdicts": ["contradicts_ensures", "requires_admits_rejected"],
        },
    }
    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
    )

    step_result = result["layers"]["l1_z3"]["steps"][0]
    assert exit_code == 1
    assert step_result["status"] == "FAIL"
    assert "forbidden verdict contradicts_ensures" in step_result["detail"]


def test_test_observation_result_is_mirrored_to_harness_state(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MUMEI_STUB_OBSERVE_REPORT",
        json.dumps(_observation_report([{"verdict": "consistent"}])),
    )
    step = {
        "id": "observe_aligned",
        "command": "{mumei_bin} observe-tests --output {output_dir}/observations.json",
        "expected_exit": 0,
        "test_observations": {"report": "observations.json"},
    }
    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
    )

    state = json.loads(Path(result["harness_state_file"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert result["test_observations"] == state["test_observations"]


def test_negative_controls_result_is_mirrored_to_harness_state(tmp_path, monkeypatch):
    step = {
        "id": "controls_weak",
        "command": "{mumei_bin} controls weak_spec.mm --json",
        "expected_exit": 1,
        "expect_failure": True,
        "negative_controls": True,
    }
    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
        controls_stdout=json.dumps(_controls_report()),
        controls_exit=1,
    )

    state = json.loads(Path(result["harness_state_file"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert result["negative_controls"] == state["negative_controls"]


def test_unflagged_scenario_has_no_negative_controls_output(tmp_path, monkeypatch):
    step = {
        "id": "verify_unflagged",
        "command": (
            "{mumei_bin} verify source.mm --proof-cert "
            "--output {output_dir}/source.proof.json"
        ),
        "expected_exit": 0,
        "expected_patterns": ["Verification passed"],
    }
    _, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
    )

    state = json.loads(Path(result["harness_state_file"]).read_text(encoding="utf-8"))
    assert "negative_controls" not in result
    assert "negative_controls" not in state
    assert "test_observations" not in result
    assert "test_observations" not in state


def test_negative_controls_gate_steps_require_specific_evidence_patterns():
    scenario_path = (
        Path(__file__).resolve().parents[1]
        / "scenarios"
        / "negative_controls_demo"
        / "scenario.json"
    )
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    steps = {step["id"]: step for step in scenario["l1_z3"]["steps"]}

    assert "constant:1->0@1" in steps["vacuity_weak"]["expected_patterns"]
    assert "next_dose: controls weak" in steps["claims_weak_gate"]["expected_patterns"]
    assert "constant:1->0@1" in steps["claims_weak_gate"]["expected_patterns"]
    assert "controls discriminating: next_dose" in steps["claims_strong_gate"]["expected_patterns"]
    assert "--require-grade" not in steps["claims_weak_gate"]["command"]


def test_claims_weak_gate_fails_on_certificate_error(tmp_path, monkeypatch):
    scenario_path = (
        Path(__file__).resolve().parents[1]
        / "scenarios"
        / "negative_controls_demo"
        / "scenario.json"
    )
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    step = next(
        step
        for step in scenario["l1_z3"]["steps"]
        if step["id"] == "claims_weak_gate"
    )
    step["cwd"] = "{root_dir}"
    step.pop("depends_on", None)

    exit_code, result, output_dir = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
        claims_exit=1,
        claims_stderr="certificate error: invalid proof certificate",
    )

    step_result = result["layers"]["l1_z3"]["steps"][0]
    assert exit_code == 1
    assert result["overall_status"] == "FAIL"
    assert step_result["status"] == "FAIL"
    assert step_result["exit_code"] == 2
    assert "certificate error: invalid proof certificate" in step_result["stderr"]
    assert "controls weak" not in step_result["stdout"] + step_result["stderr"]
    assert not (output_dir / "claims_weak" / "claimbook.json").exists()


def test_claims_weak_gate_rejects_wrong_artifact_under_pythonoptimize(
    tmp_path, monkeypatch
):
    scenario_path = (
        Path(__file__).resolve().parents[1]
        / "scenarios"
        / "negative_controls_demo"
        / "scenario.json"
    )
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    step = next(
        step
        for step in scenario["l1_z3"]["steps"]
        if step["id"] == "claims_weak_gate"
    )
    step["cwd"] = "{root_dir}"
    step.pop("depends_on", None)
    monkeypatch.setenv("PYTHONOPTIMIZE", "1")

    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
        fixtures={
            "weak_spec": {
                "claims": [
                    {
                        "atom": "next_dose",
                        "discrimination": {"status": "discriminating"},
                    }
                ]
            }
        },
    )

    step_result = result["layers"]["l1_z3"]["steps"][0]
    assert exit_code == 1
    assert result["overall_status"] == "FAIL"
    assert step_result["status"] == "FAIL"
    assert step_result["exit_code"] == 2
    assert (
        "Claim Book discrimination check failed: expected next_dose status weak"
        in step_result["stderr"]
    )


def test_step_narratives_render_for_new_and_existing_ids(tmp_path, monkeypatch, capsys):
    new_step = {
        "id": "controls_weak",
        "command": "{mumei_bin} controls weak_spec.mm --json",
        "expected_exit": 1,
        "expect_failure": True,
        "negative_controls": True,
    }
    _run_scenario(
        tmp_path / "new",
        monkeypatch,
        [],
        scenario_steps=[new_step],
        controls_stdout=json.dumps(_controls_report()),
        controls_exit=1,
        narrative={
            "steps": {
                "controls_weak": {
                    "rejected": {
                        "icon": "🧭",
                        "headline": "CONTROLS REJECTION BANNER",
                        "follow_up": ["  Review the surviving mutant."],
                    }
                }
            }
        },
    )
    new_output = capsys.readouterr().out
    assert "🧭 CONTROLS REJECTION BANNER" in new_output
    assert "Review the surviving mutant." in new_output

    vacuity_step = {
        "id": "vacuity_weak",
        "command": (
            "{mumei_bin} verify weak_spec.mm --proof-cert "
            "--output {output_dir}/weak.proof.json"
        ),
        "expected_exit": 1,
        "expected_patterns": ["Verification passed"],
        "expect_failure": True,
    }
    _run_scenario(
        tmp_path / "vacuity",
        monkeypatch,
        [],
        scenario_steps=[vacuity_step],
        verify_exit=1,
        narrative={
            "steps": {
                "vacuity_weak": {
                    "rejected": {
                        "icon": "❌",
                        "headline": "Phase 1i: a mutation survives the weak contract",
                    }
                }
            }
        },
    )
    vacuity_output = capsys.readouterr().out
    assert "❌ Phase 1i: a mutation survives the weak contract" in vacuity_output

    existing_step = {
        "id": "detect_bug",
        "command": (
            "{mumei_bin} verify source.mm --proof-cert "
            "--output {output_dir}/source.proof.json"
        ),
        "expected_exit": 1,
        "expected_patterns": ["Verification passed"],
        "expect_failure": True,
    }
    _run_scenario(
        tmp_path / "existing",
        monkeypatch,
        [],
        scenario_steps=[existing_step],
        verify_exit=1,
        narrative={
            "steps": {
                "detect_bug": {
                    "rejected": {
                        "icon": "❌",
                        "headline": "LEGACY REJECTION BANNER",
                        "follow_up": ["  Legacy follow-up."],
                    }
                }
            }
        },
    )
    existing_output = capsys.readouterr().out
    assert "❌ LEGACY REJECTION BANNER" in existing_output
    assert "Legacy follow-up." in existing_output


def test_existing_detect_bug_fallback_narrative_is_unchanged(tmp_path, monkeypatch, capsys):
    step = {
        "id": "detect_bug",
        "command": (
            "{mumei_bin} verify source.mm --proof-cert "
            "--output {output_dir}/source.proof.json"
        ),
        "expected_exit": 1,
        "expected_patterns": ["Verification passed"],
        "expect_failure": True,
    }
    _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
        verify_exit=1,
    )

    output = capsys.readouterr().out
    assert "❌ BUG DETECTED!" in output
    assert "InvalidPreState: 'accept' requires 'PendingTransfer'" in output
    assert "Step 3: Verifying the correct implementation..." in output


def test_charter_gate_parser_accepts_pass_report():
    entry = _load_runner()["parse_charter_gate_entry"](
        "charter_pass",
        "PASS",
        json.dumps(_charter_report(status="pass", atom_status="ok")),
    )

    assert entry == {
        "step": "charter_pass",
        "status": "ok",
        "gate_status": "pass",
        "lock_status": "ok",
        "atoms": [
            {
                "name": "clamp_dose",
                "charter": "specs/dosage.charter.mm",
                "status": "ok",
                "effective_grade": "G1",
            }
        ],
    }


def test_charter_gate_parser_preserves_failure_statuses():
    parse_entry = _load_runner()["parse_charter_gate_entry"]
    for status, lock_status in (
        ("post_weakened", "ok"),
        ("pre_weakened", "ok"),
        ("grade_below", "ok"),
        ("unpinned", "mismatch"),
    ):
        report = _charter_report(atom_status=status, lock_status=lock_status)
        entry = parse_entry("reject_candidate", "REJECTED", json.dumps(report))
        assert entry["status"] == "ok"
        assert entry["gate_status"] == "fail"
        assert entry["lock_status"] == lock_status
        assert entry["atoms"][0]["status"] == status


def test_charter_gate_parser_extracts_json_after_prefix_text():
    report = _charter_report(status="pass", atom_status="ok")
    entry = _load_runner()["parse_charter_gate_entry"](
        "charter_pass",
        "PASS",
        "Verification passed\n" + json.dumps(report),
    )

    assert entry["status"] == "ok"
    assert entry["gate_status"] == "pass"


def test_charter_gate_parser_marks_non_json_unavailable():
    entry = _load_runner()["parse_charter_gate_entry"](
        "charter_check",
        "REJECTED",
        "not a charter report",
    )

    assert entry["status"] == "unavailable"
    assert "JSON object" in entry["detail"]


def test_charter_gate_parser_rejects_wrong_schema():
    report = _charter_report()
    report["schema"] = "mumei.other-report/v1"
    entry = _load_runner()["parse_charter_gate_entry"](
        "charter_check",
        "REJECTED",
        json.dumps(report),
    )

    assert entry["status"] == "unavailable"
    assert "unsupported charter report schema" in entry["detail"]


def test_charter_gate_parser_rejects_missing_atoms():
    report = _charter_report()
    del report["atoms"]
    entry = _load_runner()["parse_charter_gate_entry"](
        "charter_check",
        "REJECTED",
        json.dumps(report),
    )

    assert entry["status"] == "unavailable"
    assert "atoms must be an array" in entry["detail"]


def test_charter_gate_parser_skips_unexpected_and_skipped_steps():
    parse_entry = _load_runner()["parse_charter_gate_entry"]
    stdout = json.dumps(_charter_report())
    for step_status in ("SKIPPED", "FAIL", "FAILED"):
        entry = parse_entry("charter_check", step_status, stdout)
        assert entry["status"] == "skipped"
        assert entry["detail"] == f"Step status was {step_status}"


def test_charter_gate_totals_ignore_unavailable_and_skipped_entries():
    parse_entry = _load_runner()["parse_charter_gate_entry"]
    passed = parse_entry(
        "charter_pass",
        "PASS",
        json.dumps(_charter_report(status="pass", atom_status="ok")),
    )
    failed = parse_entry(
        "charter_reject",
        "REJECTED",
        json.dumps(_charter_report(atom_status="post_weakened")),
    )
    unavailable = parse_entry("unavailable", "REJECTED", "not JSON")
    skipped = parse_entry("skipped", "SKIPPED", "")

    totals = _load_runner()["charter_gate_totals"](
        [passed, failed, unavailable, skipped]
    )

    assert totals == {
        "checks": 2,
        "passed": 1,
        "failed": 1,
        "by_atom_status": {"ok": 1, "post_weakened": 1},
    }


def test_charter_gate_result_is_written_for_declared_step(tmp_path, monkeypatch):
    step = {
        "id": "charter_reject",
        "name": "Charter rejection",
        "command": "{mumei_bin} charter check source.mm --json",
        "expected_exit": 1,
        "expect_failure": True,
        "expected_patterns": ["post_weakened"],
        "artifacts": [],
        "charter_gate": True,
    }
    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
        charter_stdout=json.dumps(_charter_report()),
        charter_exit=1,
    )

    assert exit_code == 0
    assert result["overall_status"] == "PASS"
    assert result["layers"]["l1_z3"]["steps"][0]["status"] == "REJECTED"
    assert result["charter_gate"]["entries"][0]["status"] == "ok"
    assert result["charter_gate"]["totals"] == {
        "checks": 1,
        "passed": 0,
        "failed": 1,
        "by_atom_status": {"post_weakened": 1},
    }


def test_unavailable_charter_report_fails_passing_step(tmp_path, monkeypatch):
    step = {
        "id": "charter_pass",
        "command": "{mumei_bin} charter check source.mm --json",
        "expected_exit": 0,
        "charter_gate": True,
    }
    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
        charter_stdout="not a charter report",
    )

    step_result = result["layers"]["l1_z3"]["steps"][0]
    assert exit_code == 1
    assert result["overall_status"] == "FAIL"
    assert step_result["status"] == "FAIL"
    assert step_result["detail"].startswith("charter gate report unavailable:")
    assert result["charter_gate"]["entries"][0]["status"] == "unavailable"


def test_unavailable_charter_report_fails_rejected_step(tmp_path, monkeypatch):
    step = {
        "id": "charter_reject",
        "command": "{mumei_bin} charter check source.mm --json",
        "expected_exit": 1,
        "expect_failure": True,
        "charter_gate": True,
    }
    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
        charter_stdout="not a charter report",
        charter_exit=1,
    )

    step_result = result["layers"]["l1_z3"]["steps"][0]
    assert exit_code == 1
    assert result["overall_status"] == "FAIL"
    assert step_result["status"] == "FAIL"
    assert step_result["detail"].startswith("charter gate report unavailable:")
    assert result["charter_gate"]["entries"][0]["status"] == "unavailable"


def test_unavailable_charter_report_keeps_failed_step_skipped(tmp_path, monkeypatch):
    step = {
        "id": "charter_failed",
        "command": "{mumei_bin} charter check source.mm --json",
        "expected_exit": 0,
        "charter_gate": True,
    }
    _, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [],
        scenario_steps=[step],
        charter_stdout="not a charter report",
        charter_exit=1,
    )

    step_result = result["layers"]["l1_z3"]["steps"][0]
    assert step_result["status"] == "FAIL"
    assert "detail" not in step_result
    assert result["charter_gate"]["entries"][0]["status"] == "skipped"


def test_claim_book_totals_aggregate_freshness_and_grades(tmp_path, monkeypatch):
    drifted = _book(
        [{"effective_grade": "G4", "effective_grade_complete": True}],
        by_effective_grade={"G4": 1},
        by_freshness={"drifted": 1},
    )
    uncertified = _book(
        [{"effective_grade": "G0", "effective_grade_complete": False}],
        by_effective_grade={"G0": 1},
        by_freshness={"uncertified": 1},
    )
    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [
            {"source": "{root_dir}/source_0.mm", "cert": "certificate_0.json"},
            {"source": "{root_dir}/source_1.mm", "cert": "certificate_1.json"},
        ],
        fixtures={"source_0": drifted, "source_1": uncertified},
    )

    assert exit_code == 0
    totals = result["claim_book"]["totals"]
    assert totals["total"] == 2
    assert totals["by_effective_grade"] == {
        "G0": 1,
        "G1": 0,
        "G2": 0,
        "G3": 0,
        "G4": 1,
        "G5": 0,
    }
    assert totals["by_freshness"] == {
        "fresh": 0,
        "drifted": 1,
        "uncertified": 1,
    }
    assert totals["incomplete"] == 1
    assert totals["lowest_effective_grade"] == "G0"


def test_claim_book_failure_is_informational(tmp_path, monkeypatch):
    exit_code, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [{"source": "{root_dir}/source_0.mm", "cert": "certificate_0.json"}],
        claims_exit=2,
    )

    assert exit_code == 0
    assert result["overall_status"] == "PASS"
    entry = result["claim_book"]["entries"][0]
    assert entry["status"] == "unavailable"
    assert entry["exit_code"] == 2
    assert entry["detail"] == "fixture claims failed"


def test_claim_book_missing_file_is_unavailable(tmp_path, monkeypatch):
    _, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [{"source": "{root_dir}/source_0.mm", "cert": "certificate_0.json"}],
        claims_mode="missing",
    )

    entry = result["claim_book"]["entries"][0]
    assert entry["status"] == "unavailable"
    assert entry["exit_code"] == 0
    assert entry["file"] is None
    assert "did not write" in entry["detail"]


def test_claim_book_does_not_reuse_stale_file_from_previous_run(tmp_path, monkeypatch):
    exit_code, result, marker = _run_scenario(
        tmp_path,
        monkeypatch,
        [{"source": "{root_dir}/source_0.mm", "cert": "certificate_0.json"}],
        claims_mode="missing",
        preseed_stale_claimbook=True,
    )

    assert exit_code == 0
    assert result["overall_status"] == "PASS"
    entry = result["claim_book"]["entries"][0]
    assert entry["status"] == "unavailable"
    assert entry["exit_code"] == 0
    assert entry["file"] is None
    assert "did not write" in entry["detail"]
    assert marker.exists()


def test_claim_book_invalid_json_is_unavailable(tmp_path, monkeypatch):
    _, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [{"source": "{root_dir}/source_0.mm", "cert": "certificate_0.json"}],
        claims_mode="invalid",
    )

    entry = result["claim_book"]["entries"][0]
    assert entry["status"] == "unavailable"
    assert entry["exit_code"] == 0
    assert entry["file"] == "claimbook/verify_0/claimbook.json"
    assert "unreadable" in entry["detail"]


def test_nonpassing_step_skips_claim_book_invocation(tmp_path, monkeypatch):
    exit_code, result, marker = _run_scenario(
        tmp_path,
        monkeypatch,
        [{"source": "{root_dir}/source_0.mm", "cert": "certificate_0.json"}],
        verify_exit=1,
    )

    assert exit_code == 1
    assert result["overall_status"] == "FAIL"
    entry = result["claim_book"]["entries"][0]
    assert entry["status"] == "skipped"
    assert entry["file"] is None
    assert "FAIL" in entry["detail"]
    assert not marker.exists()


def test_no_declared_claim_book_has_no_result_key(tmp_path, monkeypatch):
    _, result, marker = _run_scenario(tmp_path, monkeypatch, [None])

    assert "claim_book" not in result
    assert not marker.exists()


def test_zero_claims_has_no_lowest_grade(tmp_path, monkeypatch):
    empty = _book([])
    _, result, _ = _run_scenario(
        tmp_path,
        monkeypatch,
        [{"source": "{root_dir}/source_0.mm", "cert": "certificate_0.json"}],
        fixtures={"source_0": empty},
    )

    entry = result["claim_book"]["entries"][0]
    assert entry["status"] == "ok"
    assert entry["total"] == 0
    assert entry["lowest_effective_grade"] is None
    assert result["claim_book"]["totals"]["lowest_effective_grade"] is None
