#!/usr/bin/env python3
"""Measure native-object acceptance on the paired source-contract benchmark ports."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_contract_bench as cb  # noqa: E402

ENTRY = """
atom main() -> i64
    requires: true;
    ensures: result == 0;
    body: { 0 };
"""
CHECKED = "checked_source_machine_tv_within_profile"
OUTCOMES = ("accepted", "source_refuted", "source_recheck_refuted", "llvm_different", "object_different", "source_outside_profile",
            "machine_outside_profile", "inconclusive", "environment_error", "timeout")
SOURCE_FALSE_POSITIVE_OUTCOMES = ("source_refuted", "source_recheck_refuted")
TRANSLATION_MISMATCH_OUTCOMES = ("llvm_different", "object_different")
REJECTION_OUTCOMES = SOURCE_FALSE_POSITIVE_OUTCOMES + TRANSLATION_MISMATCH_OUTCOMES
NATIVE_FAILURE_KINDS = {
    "source_outside_profile": "unsupported",
    "machine_outside_profile": "unsupported",
    "inconclusive": "inconclusive",
    "environment_error": "environment_failure",
    "timeout": "budget_exhausted",
}
SOURCE_ADMISSION = ("unsupported or invalid module source", "source outside bounded module profile")
TOOLCHAIN_FAILURES = ("unsupported host for first native profile", "native link or toolchain observation failed")
ARTIFACT_DIFFERENCE = "pinned artifact differs from the toolchain's output for the pinned inputs"
LLVM_DIFFERENCES = ("native LLVM body differs from source",
                    "native LLVM body reaches undefined behavior on an input the source defines")
DIFFERENCES = ("native object symbol surface differs from LLVM IR", "native object call edges differ from LLVM IR",
               "linked executable function bytes or call targets differ from the object",
               "reproduced object machine code differs from the verified source",
               "object translation correspondence inconsistent with the pinned LLVM IR (")


def command(args: list[str], cwd: Path, timeout: int) -> dict:
    started = time.monotonic()
    try:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "seconds": round(time.monotonic() - started, 3)}
    except OSError:
        return {"error": "environment_error", "seconds": round(time.monotonic() - started, 3)}
    return {"exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr,
            "seconds": round(time.monotonic() - started, 3)}


def json_stdout(result: dict) -> dict:
    try:
        doc = json.loads(result.get("stdout", ""))
    except ValueError:
        return {}
    return doc if isinstance(doc, dict) else {}


def diagnostic(result: dict, messages: tuple[str, ...]) -> str | None:
    return next((message for message in messages if message in result.get("stderr", "")), None)


def build_verdict(result: dict, z3: str) -> tuple[str, str]:
    if result.get("error"):
        return result["error"], "build_command"
    if reason := diagnostic(result, TOOLCHAIN_FAILURES):
        return "environment_error", reason
    if reason := diagnostic(result, SOURCE_ADMISSION):
        # Core's admission error also covers invalid input; only label a known valid port outside profile.
        if z3 in {"proven", "refuted"}:
            return "source_outside_profile", reason
    if diagnostic(result, ("source verification failed",)) and z3 == "refuted":
        return "source_refuted", "source verification failed (independently refuted)"
    return "inconclusive", "bundle build failed without a classified rejection"


def acceptance_verdict(result: dict, build_id: str, atom: str) -> tuple[str, str]:
    if result.get("error"):
        return result["error"], "accept_object_command"
    if result["exit"] == 0:
        doc = json_stdout(result)
        tv, functions = doc.get("source_machine_tv"), doc.get("functions")
        target = functions.get(atom) if isinstance(functions, dict) else None
        if (doc.get("schema_version") == "mumei.native-evidence-acceptance/v1"
                and doc.get("acceptance") == "evaluated" and doc.get("accepted") is True
                and doc.get("build_id") == build_id
                and isinstance(tv, dict) and tv.get("status") == CHECKED
                and isinstance(target, dict) and target.get("outcome") == "equivalent_within_profile"):
            return "accepted", CHECKED
        return "inconclusive", "missing or unbound machine-TV acceptance"
    if result["exit"] == 1 and (reason := diagnostic(result, DIFFERENCES)):
        return "object_different", reason
    if result["exit"] == 1 and diagnostic(result, (ARTIFACT_DIFFERENCE,)):
        return "inconclusive", "artifact_needs_llvm_diagnosis"
    if result["exit"] == 1 and diagnostic(result, ("native bundle rejected: source postcondition refuted",)):
        return "source_recheck_refuted", "source postcondition refuted during object acceptance"
    if result["exit"] == 1 and (reason := diagnostic(result, ("native LLVM snapshot outside bounded module profile",))):
        return "source_outside_profile", reason
    if reason := diagnostic(result, TOOLCHAIN_FAILURES):
        return "environment_error", reason
    if result["exit"] == 3:
        if reason := diagnostic(result, ("source is outside the pure-i64 model profile",)):
            return "machine_outside_profile", reason
        if diagnostic(result, ("Native source/LLVM recheck inconclusive",)):
            return "inconclusive", "source/LLVM recheck inconclusive"
        if diagnostic(result, ("Machine-code TV inconclusive; not every source-atom function was proved equivalent",)):
            return "inconclusive", "machine_tv_needs_profile_diagnosis"
        if diagnostic(result, ("Object translation correspondence not fully checked",
                               "Canonical link argument vector not reproduced")):
            return "inconclusive", "object correspondence not fully checked"
    return "inconclusive", "accept-object did not establish a verdict"


def llvm_verdict(result: dict) -> tuple[str, str]:
    if result.get("error"):
        return result["error"], "recheck_llvm_command"
    if result["exit"] == 1 and (reason := diagnostic(result, LLVM_DIFFERENCES)):
        return "llvm_different", reason
    if result["exit"] == 0:
        return "object_different", ARTIFACT_DIFFERENCE
    return "inconclusive", "pinned artifact differs; LLVM recheck did not identify the stage"


def profile_verdict(result: dict, build_id: str) -> tuple[str, str]:
    if result.get("error"):
        return result["error"], "recheck_machine_tv_command"
    if result["exit"] == 3 and diagnostic(result, ("entry wrapper is outside the profile",)):
        return "machine_outside_profile", "entry wrapper is outside the profile"
    doc = json_stdout(result)
    if (result["exit"] == 0 and doc.get("schema_version") == "mumei.machine-code-tv/v1"
            and doc.get("build_id") == build_id and isinstance(doc.get("functions"), dict)):
        reasons = {f.get("reason") for f in doc["functions"].values()
                   if isinstance(f, dict) and f.get("outcome") == "outside_profile"
                   and isinstance(f.get("reason"), str) and f["reason"] != "not_a_source_atom"}
        if reasons:
            return "machine_outside_profile", ", ".join(sorted(reasons))
    return "inconclusive", "machine-TV recheck did not establish an out-of-profile function"


def run_native(mumei_bin: str, source: str, atom: str, z3: str, timeout: int) -> dict:
    stages = {}

    def call(stage: str, *args: str) -> dict:
        result = command([mumei_bin, "native-bundle", *args], work, timeout)
        stages[stage] = {k: result[k] for k in ("seconds", "exit", "error") if k in result}
        stages[stage]["budget_seconds"] = timeout
        return result

    def record(verdict: tuple[str, str], **details) -> dict:
        failure_kind = NATIVE_FAILURE_KINDS.get(verdict[0])
        measured = {"failure_kind": failure_kind} if failure_kind else {}
        return {"outcome": verdict[0], "reason": verdict[1], "stages": stages, **measured, **details}

    with tempfile.TemporaryDirectory(prefix="machine-tv-bench-") as directory:
        work = Path(directory)
        (work / "case.mm").write_text(source + ENTRY, encoding="utf-8")
        built = call("build", "build", "case.mm", "-o", "bundle")
        if built.get("exit") != 0:
            return record(build_verdict(built, z3))
        try:
            manifest = (work / "bundle/native-bundle.json").read_bytes()
            profile = json.loads(manifest)["profile"]
        except (OSError, ValueError, KeyError, TypeError):
            return record(("inconclusive", "missing or invalid bundle manifest"))
        build_id = hashlib.sha256(manifest).hexdigest()
        pinned = ("--expected-build-id", build_id, "--json", "bundle", "case.mm")
        acceptance = call("accept_object", "accept-object", *pinned)
        verdict = acceptance_verdict(acceptance, build_id, atom)
        if verdict[1] == "machine_tv_needs_profile_diagnosis":
            verdict = profile_verdict(call("recheck_machine_tv", "recheck-machine-tv", *pinned), build_id)
        elif verdict[1] == "artifact_needs_llvm_diagnosis":
            verdict = llvm_verdict(call("recheck_llvm", "recheck-llvm", "--expected-build-id", build_id,
                                        "bundle", "case.mm"))
        return record(verdict, build_id=build_id, profile=profile)


def run_case(case: dict, mumei_bin: str, timeout: int) -> dict:
    result = {k: case[k] for k in ("id", "atom", "language", "case_hash", "source_hash")}
    result["port_hashes"] = {variant: cb.sha256(case["ports"][variant]) for variant in cb.VARIANTS}
    source_verdicts = {}
    for variant in cb.VARIANTS:
        source = case["ports"][variant]
        z3 = source_verdicts[variant] = cb.verify_text(mumei_bin, source, timeout)
        result[variant] = {
            "z3": {k: z3[k] for k in ("outcome", "status", "failure_kind", "seconds", "budget_seconds") if k in z3},
            "native": run_native(mumei_bin, source, case["atom"], z3["outcome"], timeout),
        }
    result["vacuity"], control = cb.vacuity_result(case, source_verdicts, mumei_bin, timeout)
    result["vacuity_control"] = {k: control[k]
                                 for k in ("outcome", "status", "failure_kind", "seconds", "budget_seconds")
                                 if k in control}
    return result


def measurement_stats(slots: list[dict]) -> dict:
    seconds, budget, timed, budgeted = 0.0, 0.0, 0, 0
    for slot in slots:
        if cb.numeric_measurement(slot.get("seconds")):
            timed += 1
            seconds += slot["seconds"]
        if cb.numeric_measurement(slot.get("budget_seconds")):
            budgeted += 1
            budget += slot["budget_seconds"]
    return {"seconds": round(seconds, 1), "timed_calls": timed, "expected_calls": len(slots),
            "budget_seconds": round(budget, 1), "budgeted_calls": budgeted}


def source_measurement_slots(record: dict) -> list[dict]:
    slots = []
    for variant in cb.VARIANTS:
        z3 = record.get(variant, {}).get("z3")
        if isinstance(z3, dict):
            slots.append(z3)
    if "vacuity" in record:
        control = record.get("vacuity_control")
        slots.append(control if isinstance(control, dict) else {})
    return slots


def native_measurement_slots(record: dict) -> list[dict]:
    slots = []
    for variant in cb.VARIANTS:
        stages = record.get(variant, {}).get("native", {}).get("stages", {})
        slots.extend(stage for stage in stages.values() if isinstance(stage, dict))
    return slots


def host_environment() -> dict:
    """Bounded host-pressure diagnostics for interpreting repeat-run variance.

    This intentionally records only capacity/load metadata, never the process
    environment, because machine-TV verdicts can be timing- and budget-sensitive.
    """
    env = {"sampled_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
           "os": platform.system().lower(), "arch": platform.machine(),
           "cpu_count": os.cpu_count()}
    try:
        load1, load5, load15 = os.getloadavg()
    except (AttributeError, OSError):
        return env
    return {**env, "loadavg_1m": round(load1, 2), "loadavg_5m": round(load5, 2),
            "loadavg_15m": round(load15, 2)}


TOOLCHAIN_OBSERVATION_SCHEMA = "mumei.native-toolchain-observation/v1"


def valid_toolchain_observation(observation: dict) -> bool:
    if not isinstance(observation, dict):
        return False
    solvers = observation.get("solvers")
    z3 = solvers.get("z3", {}) if isinstance(solvers, dict) else {}
    llvm = observation.get("llvm", {}) if isinstance(observation.get("llvm"), dict) else {}
    host = observation.get("host", {}) if isinstance(observation.get("host"), dict) else {}
    link = observation.get("link", {}) if isinstance(observation.get("link"), dict) else {}
    return (
        observation.get("schema_version") == TOOLCHAIN_OBSERVATION_SCHEMA
        and z3.get("binding") == "linked"
        and isinstance(z3.get("version"), str)
        and llvm.get("binding") == "linked"
        and isinstance(llvm.get("version"), str)
        and isinstance(observation.get("target_triple"), str)
        and isinstance(host.get("os"), str)
        and isinstance(host.get("arch"), str)
        and all(isinstance(link.get(key), str)
                for key in ("driver", "driver_version", "driver_target", "linker", "linker_version"))
    )


def toolchain_observation(mumei_bin: str, timeout: int) -> dict:
    """Observe effective solver/toolchain identity without making it acceptance evidence.

    Unavailability is explicit diagnostic metadata. Raw stderr is not copied because it
    is unconstrained output and is not needed to classify this bounded observation failure.
    """
    result = command([mumei_bin, "native-bundle", "observe-toolchain", "--json"], cb.REPO_ROOT, timeout)
    if result.get("error"):
        return {"status": "unavailable", "reason": f"observe-toolchain {result['error']}"}
    if result.get("exit") != 0:
        return {"status": "unavailable", "reason": f"observe-toolchain exit {result.get('exit')}"}
    observation = json_stdout(result)
    if not valid_toolchain_observation(observation):
        return {"status": "unavailable", "reason": "observe-toolchain returned invalid metadata"}
    return {"status": "observed", "observation": observation}


UNRESOLVED_OUTCOME_GROUPS = {
    "unsupported": ("source_outside_profile", "machine_outside_profile"),
    "inconclusive": ("inconclusive",),
    "environment_failure": ("environment_error",),
    "budget_exhausted": ("timeout",),
}


def unresolved_reasons(records: list[dict], variant: str) -> dict:
    """Reason counts for non-acceptance limiting factors, kept separate from
    assurance outcomes so unsupported/inconclusive/environment/budget are not
    collapsed into pass/fail or into each other."""
    grouped = {}
    for label, outcomes in UNRESOLVED_OUTCOME_GROUPS.items():
        counts = Counter(
            r[variant]["native"].get("reason") or "missing_reason"
            for r in records
            if r[variant]["native"]["outcome"] in outcomes
        )
        grouped[label] = dict(sorted(counts.items()))
    return grouped


def native_stage_measurements(records: list[dict]) -> dict:
    by_stage: dict[str, list[dict]] = {}
    for record in records:
        for variant in cb.VARIANTS:
            stages = record.get(variant, {}).get("native", {}).get("stages", {})
            for name, slot in stages.items():
                if isinstance(slot, dict):
                    by_stage.setdefault(name, []).append(slot)
    return {name: measurement_stats(slots) for name, slots in sorted(by_stage.items())}


def summarize(records: list[dict]) -> dict:
    by_variant = {}
    for variant in cb.VARIANTS:
        counts = Counter(r[variant]["native"]["outcome"] for r in records)
        comparison = Counter((r[variant]["z3"]["outcome"], r[variant]["native"]["outcome"]) for r in records)
        by_variant[variant] = {
            "outcomes": {outcome: counts[outcome] for outcome in OUTCOMES},
            "rejected": sum(counts[outcome] for outcome in REJECTION_OUTCOMES),
            "outside_profile": counts["source_outside_profile"] + counts["machine_outside_profile"],
            "false_acceptance": sum(r[variant]["z3"]["outcome"] == "refuted"
                                    and r[variant]["native"]["outcome"] == "accepted" for r in records),
            "false_positive": sum(r[variant]["z3"]["outcome"] == "proven"
                                  and r[variant]["native"]["outcome"] in SOURCE_FALSE_POSITIVE_OUTCOMES for r in records),
            "translation_mismatch": sum(counts[outcome] for outcome in TRANSLATION_MISMATCH_OUTCOMES),
            "unsupported": counts["source_outside_profile"] + counts["machine_outside_profile"],
            "inconclusive": counts["inconclusive"],
            "environment_failure": counts["environment_error"],
            "budget_exhausted": counts["timeout"],
            "z3_vs_native": {z3: {native: n for (source, native), n in sorted(comparison.items()) if source == z3}
                             for z3 in ("refuted", "proven", "inconclusive")},
            "unresolved_reasons": unresolved_reasons(records, variant),
        }
    return {
        "cases": len(records),
        "source_contract": {
            "buggy_refuted": sum(r["buggy"]["z3"]["outcome"] == "refuted" for r in records),
            "fixed_proven": sum(r["fixed"]["z3"]["outcome"] == "proven" for r in records),
            "vacuity": dict(sorted(Counter(r["vacuity"] for r in records).items())),
        },
        "native": by_variant,
        "measurement": {
            "source_verification": measurement_stats([slot for r in records for slot in source_measurement_slots(r)]),
            "native_pipeline": measurement_stats([slot for r in records for slot in native_measurement_slots(r)]),
            "native_pipeline_by_stage": native_stage_measurements(records),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mumei-bin", default=os.environ.get("MUMEI_BIN") or shutil.which("mumei"),
                        help="mumei binary (default: $MUMEI_BIN, then mumei on PATH)")
    parser.add_argument("--output", type=Path,
                        help="JSON report path (default: reports/machine_tv_bench.json, "
                             "or reports/machine_tv_bench_filtered.json with --only)")
    parser.add_argument("--only", action="append", help="limit to these defect ids (repeatable)")
    parser.add_argument("--jobs", type=int, default=4, help="cases run in parallel")
    parser.add_argument("--timeout", type=int, default=120, help="per-command timeout in seconds")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    binary = shutil.which(args.mumei_bin) if args.mumei_bin else None
    if binary is None:
        parser.error("a runnable --mumei-bin is required")
    if args.jobs < 1 or args.timeout < 1:
        parser.error("--jobs and --timeout must be positive")
    mumei_bin = str(Path(binary).resolve())
    cases, errors = cb.load_cases()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.only:
        missing = set(args.only) - {case["id"] for case in cases}
        if missing:
            parser.error(f"unknown defect ids: {', '.join(sorted(missing))}")
        cases = [case for case in cases if case["id"] in args.only]
    if not cases:
        parser.error("no contract benchmark cases")
    started = dt.datetime.now(dt.timezone.utc)
    environment_start = host_environment()
    toolchain = toolchain_observation(mumei_bin, args.timeout)
    clock = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        records = list(pool.map(lambda case: run_case(case, mumei_bin, args.timeout), cases))
    summary = summarize(records)
    doc = {
        "schema_version": "mumei-demo.machine-tv-bench/v1",
        "recorded_at": started.replace(microsecond=0).isoformat(),
        "demo": cb.git_identity(str(cb.REPO_ROOT)),
        "verifier": cb.verifier_identity(mumei_bin),
        "environment": {"start": environment_start, "end": host_environment()},
        "toolchain": toolchain,
        "settings": {"jobs": args.jobs, "timeout_seconds": args.timeout, "model_calls": 0},
        "seconds": round(time.monotonic() - clock, 3),
        "summary": summary,
        "cases": records,
    }
    report_name = "machine_tv_bench_filtered.json" if args.only else "machine_tv_bench.json"
    output = args.output or cb.REPO_ROOT / "reports" / report_name
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
