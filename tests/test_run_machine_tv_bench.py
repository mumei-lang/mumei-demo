from __future__ import annotations

import hashlib
import json

import pytest

from scripts import run_machine_tv_bench as bench

PORT = "atom target(x: i64) -> i64\n    requires: true;\n    ensures: result == x;\n    body: { x };\n"
MANIFEST = b'{"profile":"test-profile"}\n'
BUILD_ID = hashlib.sha256(MANIFEST).hexdigest()


def acceptance(**overrides):
    return {
        "schema_version": "mumei.native-evidence-acceptance/v1",
        "acceptance": "evaluated",
        "accepted": True,
        "build_id": BUILD_ID,
        "source_machine_tv": {"status": bench.CHECKED},
        "functions": {"target": {"outcome": "equivalent_within_profile"}},
        **overrides,
    }


def result(exit_code, *, data=None, stderr=""):
    return {"exit": exit_code, "stdout": json.dumps(data) if data is not None else "",
            "stderr": stderr, "seconds": 0.01}


@pytest.mark.parametrize(("overrides", "exit_code", "expected"), [
    ({}, 0, "accepted"),
    ({}, 3, "inconclusive"),
    ({"accepted": False}, 0, "inconclusive"),
    ({"build_id": "wrong"}, 0, "inconclusive"),
    ({"functions": {"main": {"outcome": "equivalent_within_profile"}}}, 0, "inconclusive"),
    ({"source_machine_tv": {"status": "unchecked_not_translation_validated"}}, 0, "inconclusive"),
    ({"schema_version": "mumei.machine-code-tv/v1"}, 0, "inconclusive"),
])
def test_acceptance_requires_bound_and_checked_target(overrides, exit_code, expected):
    assert bench.acceptance_verdict(result(exit_code, data=acceptance(**overrides)), BUILD_ID, "target")[0] == expected


@pytest.mark.parametrize(("stderr", "z3", "expected"), [
    ("unsupported or invalid module source", "refuted", "source_outside_profile"),
    ("unsupported or invalid module source", "inconclusive", "inconclusive"),
    ("source verification failed", "refuted", "source_refuted"),
    ("source verification failed", "proven", "inconclusive"),
    ("native link or toolchain observation failed", "refuted", "environment_error"),
    ("unrelated build error", "refuted", "inconclusive"),
])
def test_build_failure_is_not_automatically_a_buggy_rejection(stderr, z3, expected):
    assert bench.build_verdict(result(1, stderr=stderr), z3)[0] == expected


@pytest.mark.parametrize(("exit_code", "stderr", "expected"), [
    (1, "native bundle rejected: source postcondition refuted", "source_recheck_refuted"),
    (1, "native bundle rejected: native LLVM snapshot outside bounded module profile", "source_outside_profile"),
    (1, "native bundle rejected: reproduced object machine code differs from the verified source", "object_different"),
    (3, "Native source/LLVM recheck inconclusive", "inconclusive"),
    (3, "Machine-code TV inconclusive; source is outside the pure-i64 model profile.", "machine_outside_profile"),
])
def test_accept_object_nonacceptance_is_classified_by_stage(exit_code, stderr, expected):
    assert bench.acceptance_verdict(result(exit_code, stderr=stderr), BUILD_ID, "target")[0] == expected


def test_native_route_uses_same_source_and_pins_the_manifest(monkeypatch):
    seen = []

    def command(args, cwd, timeout):
        seen.append(args)
        assert timeout == 10
        assert (cwd / "case.mm").read_text() == PORT + bench.ENTRY
        if args[2] == "build":
            bundle = cwd / "bundle"
            bundle.mkdir()
            (bundle / "native-bundle.json").write_bytes(MANIFEST)
            return result(0)
        return result(0, data=acceptance())

    monkeypatch.setattr(bench, "command", command)
    measured = bench.run_native("/bin/mumei", PORT, "target", "proven", 10)
    assert measured["outcome"] == "accepted"
    assert measured["profile"] == "test-profile"
    assert seen == [
        ["/bin/mumei", "native-bundle", "build", "case.mm", "-o", "bundle"],
        ["/bin/mumei", "native-bundle", "accept-object", "--expected-build-id", BUILD_ID, "--json", "bundle", "case.mm"],
    ]


@pytest.mark.parametrize(("recheck", "expected"), [
    (result(1, stderr="native bundle rejected: native LLVM body differs from source"), "llvm_different"),
    (result(0), "object_different"),
    (result(3), "inconclusive"),
])
def test_ambiguous_artifact_mismatch_rechecks_llvm_before_assigning_stage(monkeypatch, recheck, expected):
    def command(args, cwd, timeout):
        if args[2] == "build":
            (cwd / "bundle").mkdir()
            (cwd / "bundle/native-bundle.json").write_bytes(MANIFEST)
            return result(0)
        if args[2] == "accept-object":
            return result(1, stderr=f"native bundle rejected: {bench.ARTIFACT_DIFFERENCE}")
        assert args[2:] == ["recheck-llvm", "--expected-build-id", BUILD_ID, "bundle", "case.mm"]
        return recheck

    monkeypatch.setattr(bench, "command", command)
    measured = bench.run_native("/bin/mumei", PORT, "target", "proven", 10)
    assert measured["outcome"] == expected
    assert set(measured["stages"]) == {"build", "accept_object", "recheck_llvm"}


@pytest.mark.parametrize(("functions", "expected"), [
    ({"target": {"outcome": "outside_profile", "reason": "instruction"}}, "machine_outside_profile"),
    ({"target": {"outcome": "equivalent_within_profile"}}, "inconclusive"),
    ({"helper": {"outcome": "outside_profile", "reason": "not_a_source_atom"}}, "inconclusive"),
])
def test_diagnostic_recheck_never_substitutes_for_acceptance(monkeypatch, functions, expected):
    def command(args, cwd, timeout):
        if args[2] == "build":
            (cwd / "bundle").mkdir()
            (cwd / "bundle/native-bundle.json").write_bytes(MANIFEST)
            return result(0)
        if args[2] == "accept-object":
            return result(3, stderr="Machine-code TV inconclusive; not every source-atom function was proved equivalent")
        assert args[2] == "recheck-machine-tv"
        return result(0, data=acceptance(schema_version="mumei.machine-code-tv/v1", functions=functions))

    monkeypatch.setattr(bench, "command", command)
    assert bench.run_native("/bin/mumei", PORT, "target", "proven", 10)["outcome"] == expected


def test_native_failure_kind_and_stage_budget_are_recorded(monkeypatch):
    def command(args, cwd, timeout):
        return {"error": "environment_error", "seconds": 0.25}

    monkeypatch.setattr(bench, "command", command)
    measured = bench.run_native("/bin/mumei", PORT, "target", "proven", 10)
    assert measured["outcome"] == "environment_error"
    assert measured["failure_kind"] == "environment_failure"
    assert measured["stages"]["build"]["budget_seconds"] == 10
    assert measured["stages"]["build"]["seconds"] == 0.25


def test_run_case_preserves_source_measurements_and_vacuity_control(monkeypatch):
    case = {"id": "A", "atom": "target", "language": "python", "case_hash": "case", "source_hash": "source",
            "ports": {"buggy": "buggy", "fixed": "fixed"}}
    control = {"outcome": "refuted", "status": "failed", "diagnostics": [{"message": "not reported"}],
               "seconds": 0.5, "budget_seconds": 10}

    def verify_text(binary, source, timeout):
        return {"outcome": "inconclusive", "status": "failed",
                "failure_kind": "inconclusive", "diagnostics": [], "seconds": 1.0, "budget_seconds": timeout}

    monkeypatch.setattr(bench.cb, "verify_text", verify_text)
    monkeypatch.setattr(bench.cb, "vacuity_result", lambda *args: ("ok", control))
    monkeypatch.setattr(bench, "run_native", lambda *args: {"outcome": "accepted", "stages": {}})
    measured = bench.run_case(case, "/bin/mumei", 10)
    assert measured["buggy"]["z3"]["seconds"] == 1.0
    assert measured["buggy"]["z3"]["budget_seconds"] == 10
    assert measured["buggy"]["z3"]["failure_kind"] == "inconclusive"
    assert measured["vacuity_control"] == {k: control[k] for k in ("outcome", "status", "seconds", "budget_seconds")}


def test_summary_does_not_turn_non_acceptance_into_rejection():
    def variant(z3, native):
        return {"z3": {"outcome": z3}, "native": {"outcome": native}}

    records = [
        {"buggy": variant("refuted", "source_outside_profile"), "fixed": variant("proven", "accepted"), "vacuity": "ok"},
        {"buggy": variant("refuted", "source_refuted"),
         "fixed": variant("proven", "machine_outside_profile"), "vacuity": "ok"},
        {"buggy": variant("refuted", "accepted"), "fixed": variant("proven", "timeout"), "vacuity": "inconclusive"},
    ]
    summary = bench.summarize(records)
    assert summary["cases"] == 3
    assert summary["source_contract"] == {"buggy_refuted": 3, "fixed_proven": 3, "vacuity": {"inconclusive": 1, "ok": 2}}
    assert summary["native"]["buggy"]["z3_vs_native"]["refuted"] == {
        "accepted": 1, "source_outside_profile": 1, "source_refuted": 1,
    }
    assert summary["native"]["buggy"]["outcomes"]["source_refuted"] == 1
    assert summary["native"]["buggy"]["rejected"] == 1
    assert summary["native"]["buggy"]["outside_profile"] == summary["native"]["fixed"]["outside_profile"] == 1
    assert summary["native"]["fixed"]["outcomes"]["timeout"] == 1
    assert summary["native"]["buggy"]["false_acceptance"] == 1
    assert summary["native"]["buggy"]["unsupported"] == 1
    assert summary["native"]["fixed"]["budget_exhausted"] == 1


def test_summary_separates_assurance_outcomes_from_time_and_budget():
    def variant(z3, native, stage):
        return {
            "z3": {"outcome": z3, "seconds": 1.0, "budget_seconds": 5},
            "native": {"outcome": native, "stages": {"build": stage}},
        }

    def record(buggy_native, fixed_native, fixed_stage):
        return {
            "buggy": variant("refuted", buggy_native, {"seconds": 2.0, "budget_seconds": 10}),
            "fixed": variant("proven", fixed_native, fixed_stage),
            "vacuity": "ok",
            "vacuity_control": {"seconds": 0.5, "budget_seconds": 5},
        }

    records = [
        record("accepted", "llvm_different", {"seconds": 2.0, "budget_seconds": 10}),
        record("machine_outside_profile", "timeout", {}),
        record("timeout", "source_recheck_refuted", {"seconds": 1.0, "budget_seconds": 10}),
    ]
    summary = bench.summarize(records)
    assert summary["native"]["buggy"]["false_acceptance"] == 1
    assert summary["native"]["buggy"]["unsupported"] == 1
    assert summary["native"]["buggy"]["budget_exhausted"] == 1
    assert summary["native"]["fixed"]["false_positive"] == 1
    assert summary["native"]["fixed"]["translation_mismatch"] == 1
    assert summary["native"]["fixed"]["budget_exhausted"] == 1
    assert summary["measurement"]["source_verification"] == {
        "seconds": 7.5, "timed_calls": 9, "expected_calls": 9,
        "budget_seconds": 45.0, "budgeted_calls": 9,
    }
    assert summary["measurement"]["native_pipeline"] == {
        "seconds": 9.0, "timed_calls": 5, "expected_calls": 6,
        "budget_seconds": 50.0, "budgeted_calls": 5,
    }


def test_summary_attributes_unresolved_reasons_and_stage_measurements():
    def variant(z3, native_outcome, reason, stages):
        return {
            "z3": {"outcome": z3, "seconds": 1.0, "budget_seconds": 5},
            "native": {"outcome": native_outcome, "reason": reason, "stages": stages},
        }

    records = [
        {
            "buggy": variant("refuted", "inconclusive", "machine_tv_needs_profile_diagnosis",
                             {"build": {"seconds": 2.0, "budget_seconds": 10},
                              "accept_object": {"seconds": 3.0, "budget_seconds": 10}}),
            "fixed": variant("proven", "machine_outside_profile", "instruction outside profile",
                             {"build": {"seconds": 1.0, "budget_seconds": 10}}),
            "vacuity": "ok",
        },
        {
            "buggy": variant("refuted", "environment_error", "build_command",
                             {"build": {"error": "environment_error", "seconds": 0.5, "budget_seconds": 10}}),
            "fixed": variant("proven", "timeout", "accept_object_command",
                             {"build": {"seconds": 1.5, "budget_seconds": 10},
                              "accept_object": {"error": "timeout", "budget_seconds": 10}}),
            "vacuity": "ok",
        },
    ]
    summary = bench.summarize(records)
    assert summary["native"]["buggy"]["unresolved_reasons"]["inconclusive"] == {
        "machine_tv_needs_profile_diagnosis": 1,
    }
    assert summary["native"]["buggy"]["unresolved_reasons"]["environment_failure"] == {"build_command": 1}
    assert summary["native"]["fixed"]["unresolved_reasons"]["unsupported"] == {"instruction outside profile": 1}
    assert summary["native"]["fixed"]["unresolved_reasons"]["budget_exhausted"] == {"accept_object_command": 1}
    assert summary["measurement"]["native_pipeline_by_stage"] == {
        "accept_object": {"seconds": 3.0, "timed_calls": 1, "expected_calls": 2,
                          "budget_seconds": 20.0, "budgeted_calls": 2},
        "build": {"seconds": 5.0, "timed_calls": 4, "expected_calls": 4,
                  "budget_seconds": 40.0, "budgeted_calls": 4},
    }


def test_filtered_report_defaults_to_separate_path(monkeypatch, tmp_path):
    cases = [{"id": "A"}, {"id": "B"}]

    def run_case(case, binary, timeout):
        return {
            "id": case["id"], "vacuity": "ok",
            "buggy": {"z3": {"outcome": "refuted"}, "native": {"outcome": "source_refuted"}},
            "fixed": {"z3": {"outcome": "proven"}, "native": {"outcome": "accepted"}},
        }

    monkeypatch.setattr(bench.cb, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(bench.cb, "load_cases", lambda: (cases, []))
    monkeypatch.setattr(bench.cb, "git_identity", lambda _: {})
    monkeypatch.setattr(bench.cb, "verifier_identity", lambda _: {})
    monkeypatch.setattr(bench.shutil, "which", lambda binary: binary)
    monkeypatch.setattr(bench, "run_case", run_case)

    args = ["--mumei-bin", "/fake/mumei"]
    full = tmp_path / "reports/machine_tv_bench.json"
    filtered = tmp_path / "reports/machine_tv_bench_filtered.json"
    assert bench.main(args) == 0
    full_report = full.read_bytes()
    assert [case["id"] for case in json.loads(full_report)["cases"]] == ["A", "B"]
    assert bench.main(args + ["--only", "A"]) == 0
    assert full.read_bytes() == full_report
    assert [case["id"] for case in json.loads(filtered.read_text())["cases"]] == ["A"]
    assert bench.main(args + ["--only", "B", "--output", str(tmp_path / "custom.json")]) == 0
    assert [case["id"] for case in json.loads((tmp_path / "custom.json").read_text())["cases"]] == ["B"]


def test_host_environment_is_bounded_and_serializable(monkeypatch):
    monkeypatch.setattr(bench.os, "getloadavg", lambda: (1.234, 2.345, 3.456), raising=False)
    env = bench.host_environment()
    assert set(env) <= {"os", "arch", "cpu_count", "loadavg_1m", "loadavg_5m", "loadavg_15m"}
    assert env["loadavg_1m"] == 1.23 and env["loadavg_15m"] == 3.46
    json.dumps(env)


def test_host_environment_tolerates_missing_loadavg(monkeypatch):
    monkeypatch.delattr(bench.os, "getloadavg", raising=False)
    env = bench.host_environment()
    assert "loadavg_1m" not in env
    assert {"os", "arch", "cpu_count"} <= set(env)
