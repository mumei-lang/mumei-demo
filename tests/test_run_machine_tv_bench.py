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
