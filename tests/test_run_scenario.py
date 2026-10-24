"""Tests for the Python heredoc embedded in scripts/run_scenario.sh."""
from __future__ import annotations

import json
import os
from pathlib import Path

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
if not args or args[0] != "claims":
    print("unsupported command", file=sys.stderr)
    raise SystemExit(2)

marker = os.environ.get("MUMEI_STUB_CLAIMS_MARKER")
if marker:
    with Path(marker).open("a", encoding="utf-8") as handle:
        handle.write("claims\\\\n")
exit_code = int(os.environ.get("MUMEI_STUB_CLAIMS_EXIT", "0"))
if exit_code:
    print("fixture claims failed", file=sys.stderr)
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

    steps = []
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
    (scenario_dir / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")

    stub = _make_mumei_stub(root)
    marker = tmp_path / "claims-invoked.txt"
    monkeypatch.setenv("MUMEI_STUB_CLAIMS_MARKER", str(marker))
    monkeypatch.setenv("MUMEI_STUB_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("MUMEI_STUB_VERIFY_EXIT", str(verify_exit))
    monkeypatch.setenv("MUMEI_STUB_CLAIMS_EXIT", str(claims_exit))
    monkeypatch.setenv("MUMEI_STUB_CLAIMS_MODE", claims_mode)

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
