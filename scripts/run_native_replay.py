#!/usr/bin/env python3
"""Replay concrete inputs on the native code and on the .mm ports of the contract benchmark.

For every case in proofs/, `replay.json` names concrete inputs in the port's parameter terms.
Each input runs twice:

- on the native function (buggy and fixed tree), through a per-specimen driver in
  proofs/replay/ that checks the requirement in the native language, and
- on a .mm port, by pinning the port's parameters to the input and verifying the
  original `ensures` (refuted means the port breaks the contract on that input).

A port that holds on an input where the native buggy function breaks the requirement
no longer models the native code: the port fixed the bug while translating it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_contract_bench as rb  # noqa: E402

PARAM_RE = re.compile(r"(\w+)\s*:\s*(\[i64\]|i64|bool)")


def atom_params(header: str) -> list[tuple[str, str]]:
    """(name, type) of the target atom's parameters."""
    sig = header[header.index("(") + 1:header.index(")")]
    return PARAM_RE.findall(sig)


def mm_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value) if value >= 0 else f"(0 - {-value})"
    raise ValueError(f"unsupported input value {value!r}")


def pin_requires(header: str, values: dict) -> str:
    """The `requires` clause that fixes every parameter to `values`."""
    clauses = []
    for name, typ in atom_params(header):
        if name not in values:
            raise ValueError(f"input has no value for parameter {name!r}")
        v = values[name]
        if typ == "[i64]":
            if not isinstance(v, list):
                raise ValueError(f"{name} must be a list")
            clauses.append(f"len({name}) == {len(v)}")
            clauses += [f"{name}[{i}] == {mm_literal(x)}" for i, x in enumerate(v)]
        elif typ == "bool":
            if not isinstance(v, bool):
                raise ValueError(f"{name} must be a bool")
            clauses.append(name if v else f"!{name}")
        else:
            if isinstance(v, bool) or not isinstance(v, int):
                raise ValueError(f"{name} must be an integer")
            clauses.append(f"{name} == {mm_literal(v)}")
    extra = set(values) - {n for n, _ in atom_params(header)}
    if extra:
        raise ValueError(f"input names unknown parameters: {sorted(extra)}")
    return " && ".join(clauses) or "true"


def pinned_port(port_text: str, atom: str, values: dict) -> str:
    """The port with its target atom's `requires` narrowed to the pinned input.

    The original precondition stays in place, so mumei reports an input outside it as a
    requires contradiction instead of checking a state the contract excludes.
    """
    parts = rb.split_port(port_text, atom)
    if parts is None:
        raise ValueError(f"atom {atom!r} not found in port")
    prelude, header, body = parts
    pins = pin_requires(header, values)
    pinned, found = re.subn(r"^(\s*requires:\s*)(.*?)\s*;\s*$",
                            lambda m: f"{m.group(1)}({m.group(2)}) && {pins};", header, count=1, flags=re.M)
    if not found:
        raise ValueError(f"atom {atom!r} has no single-line requires")
    return prelude + pinned + body


REQUIRES_CONTRADICTION = re.compile(r"Spec contradiction in atom '[^']*': requires")


def port_verdict(mumei_bin: str, port_text: str, atom: str, values: dict, timeout: int = 120) -> dict:
    """breaks / holds / outside requires / inconclusive for a port on one concrete input."""
    res = rb.verify_text(mumei_bin, pinned_port(port_text, atom, values), timeout)
    verdict = {"refuted": "breaks", "proven": "holds"}.get(res["outcome"], "inconclusive")
    if verdict == "inconclusive" and any(REQUIRES_CONTRADICTION.search(d["message"]) for d in res["diagnostics"]):
        verdict = "outside requires"
    return {"verdict": verdict, "status": res["status"],
            "diagnostics": [d["message"][:200] for d in res["diagnostics"]][:2]}


REPLAY_DIR = rb.PROOFS_ROOT / "replay"
GO_BIN_DIR = Path.home() / ".local" / "go" / "bin"


def go_driver(specimen: str) -> str:
    """The Go driver source: the shared harness plus the specimen's replayCheck."""
    common = (REPLAY_DIR / "go" / "replay_common.go.in").read_text()
    own = (REPLAY_DIR / "go" / f"{specimen}.go.in").read_text()
    extra = re.match(r"//\s*imports:\s*(.*)\n", own)
    if extra:
        imports = "".join(f'\t"{name}"\n' for name in extra.group(1).split())
        common = common.replace('\t"testing"\n', '\t"testing"\n' + imports, 1)
        own = own[extra.end():]
    return common + own


def run_native(language: str, specimen: str, tree: Path, requests: list[dict], timeout: int = 600) -> dict:
    """{case id: {"violates", "observed"}} for every request run on `tree`."""
    lines = "".join(json.dumps(r) + "\n" for r in requests)
    env = dict(os.environ)
    if language == "python":
        cmd = [sys.executable, str(REPLAY_DIR / "python.py"), str(tree)]
        proc = subprocess.run(cmd, input=lines, capture_output=True, text=True, cwd=tree, timeout=timeout)
        stdout = proc.stdout
    elif language == "typescript":
        cmd = ["node", "--no-warnings", str(REPLAY_DIR / "typescript.mjs"), str(tree)]
        proc = subprocess.run(cmd, input=lines, capture_output=True, text=True, cwd=tree, timeout=timeout)
        stdout = proc.stdout
    elif language == "go":
        with tempfile.TemporaryDirectory(prefix="native-replay-") as tmp:
            work = Path(tmp) / "s"
            shutil.copytree(tree, work, ignore=shutil.ignore_patterns("bin", "audit", "baselines", "llm_only"))
            (work / "zz_native_replay_test.go").write_text(go_driver(specimen))
            (Path(tmp) / "in.jsonl").write_text(lines)
            env.update(PATH=f"{GO_BIN_DIR}{os.pathsep}{env.get('PATH', '')}", REPLAY_IN=str(Path(tmp) / "in.jsonl"),
                       REPLAY_OUT=str(Path(tmp) / "out.jsonl"), GOFLAGS="-mod=mod")
            proc = subprocess.run(["go", "test", "-run", "^TestNativeReplay$", "-count=1", "."],
                                  capture_output=True, text=True, cwd=work, env=env, timeout=timeout)
            out = Path(tmp) / "out.jsonl"
            stdout = out.read_text() if out.exists() else ""
    elif language == "rust":
        # run.sh ships `cargo build --release`, so replay with release overflow semantics (wrapping).
        with tempfile.TemporaryDirectory(prefix="native-replay-") as tmp:
            work = Path(tmp) / "s"
            shutil.copytree(tree, work, ignore=shutil.ignore_patterns("target", "audit", "baselines", "llm_only"))
            driver = (REPLAY_DIR / "rust" / "replay_common.rs.in").read_text() + (REPLAY_DIR / "rust" / f"{specimen}.rs.in").read_text()
            main_rs = work / "src" / "main.rs"
            main_rs.write_text(main_rs.read_text() + "\n" + driver)
            (Path(tmp) / "in.txt").write_text("".join(
                r["case"] + "".join(f"|{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in r["values"].items()) + "\n"
                for r in requests))
            env.update(REPLAY_IN=str(Path(tmp) / "in.txt"), REPLAY_OUT=str(Path(tmp) / "out.jsonl"))
            proc = subprocess.run(["cargo", "test", "--release", "--offline", "-q", "native_replay::native_replay"],
                                  capture_output=True, text=True, cwd=work, env=env, timeout=timeout)
            out = Path(tmp) / "out.jsonl"
            stdout = out.read_text() if out.exists() else ""
    elif language == "solidity":
        return run_solidity(specimen, tree, requests, timeout)
    else:
        raise ValueError(f"no native driver for {language}")
    rows = {}
    for line in stdout.splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["case"]] = {"violates": row["violates"], "observed": row["observed"]}
    missing = [r["case"] for r in requests if r["case"] not in rows]
    if missing:
        raise RuntimeError(f"{language}/{specimen}: driver gave no answer for {missing}: "
                           f"{(proc.stderr or proc.stdout)[-800:]}")
    return rows


def sol_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and value >= 0:
        return str(value)
    raise ValueError(f"no uint256/bool literal for {value!r}")


def run_solidity(specimen: str, tree: Path, requests: list[dict], timeout: int = 600) -> dict:
    """Run each input as one forge test that calls check_<case> from the specimen's ReplayChecks."""
    rows: dict = {}
    tests = []
    for i, req in enumerate(requests):
        try:
            args = ", ".join(sol_literal(v) for v in req["values"].values())
        except ValueError as error:
            rows[req["case"]] = {"violates": False, "unexpressible": True, "observed": str(error)}
            continue
        fn = "check_" + req["case"].replace("-", "_")
        tests.append((i, req["case"], f"    function test_{i}() public {{ {fn}({args}); }}\n"))
    if tests:
        with tempfile.TemporaryDirectory(prefix="native-replay-") as tmp:
            work = Path(tmp) / "s"
            shutil.copytree(tree, work, ignore=shutil.ignore_patterns("out", "cache", "audit", "baselines", "llm_only"))
            shutil.copy(REPLAY_DIR / "solidity" / f"{specimen}.sol.in", work / "test" / "zz_ReplayChecks.sol")
            (work / "test" / "zz_NativeReplay.t.sol").write_text(
                "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n\nimport \"./zz_ReplayChecks.sol\";\n\n"
                "contract NativeReplayTest is ReplayChecks {\n" + "".join(t for _, _, t in tests) + "}\n")
            proc = subprocess.run(
                ["forge", "test", "--offline", "--match-path", "test/zz_NativeReplay.t.sol", "--json"],
                capture_output=True, text=True, cwd=work, timeout=timeout)
            try:
                report = json.loads(proc.stdout[proc.stdout.index("{"):])
            except ValueError:
                raise RuntimeError(f"solidity/{specimen}: forge gave no JSON: {(proc.stderr or proc.stdout)[-800:]}")
            results = {}
            for suite in report.values():
                results.update(suite.get("test_results", {}))
            for i, case, _ in tests:
                res = results.get(f"test_{i}()")
                if res is None:
                    raise RuntimeError(f"solidity/{specimen}: no result for {case}")
                reason = res.get("reason") or ""
                if res["status"] == "Success":
                    rows[case] = {"violates": False, "observed": "requirement held"}
                elif reason.startswith("violated: "):
                    rows[case] = {"violates": True, "observed": reason[len("violated: "):][:300]}
                elif reason.startswith("unexpressible: "):
                    rows[case] = {"violates": False, "unexpressible": True, "observed": reason[len("unexpressible: "):][:300]}
                else:
                    raise RuntimeError(f"solidity/{specimen}: harness failure in {case}: {reason[:300]}")
    return rows


# ---- harness

import argparse  # noqa: E402
import hashlib  # noqa: E402
from collections import Counter  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

RESULT_PATH = rb.PROOFS_ROOT / "native_replay.json"
REPLAY_MD = rb.PROOFS_ROOT / "REPLAY.md"
LLM_RESULT = rb.RESULTS_DIR / "llm-openai__gpt-6-luna.json"
PORT_RESULT = rb.RESULTS_DIR / "mumei-llm-openai__gpt-6-luna.json"
I64 = (-(2**63), 2**63 - 1)
# Parameters that size a collection the driver has to build; larger witnesses are not run.
SIZE_PARAMS = {"locations", "n", "n_paths", "accounts", "recipients", "cells", "words", "sessions",
               "queued", "rows", "cols", "count"}
SIZE_LIMIT = 100_000
WITNESS_PAIR = re.compile(r"\b(\w+)\s*(?:=|:)\s*(\[[^\]]*\]|-?\d[\d_]*|(?i:true|false))(?![\w.])")


def rel(path: Path) -> str:
    try:
        return path.relative_to(rb.REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def driver_files() -> list[Path]:
    return sorted(p for p in REPLAY_DIR.rglob("*") if p.is_file())


def drivers_hash() -> str:
    h = hashlib.sha256()
    for p in driver_files():
        h.update(p.relative_to(rb.REPO_ROOT).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


# Results of other arms that live next to a specimen's code but are not part of it.
NOT_NATIVE_CODE = {"audit", "baselines", "llm_only", "__pycache__", "node_modules", "target", "out"}


def specimen_hash(language: str, specimen: str) -> str:
    """Hash of a specimen's tracked code, fixed.patch included."""
    root = rb.SPECIMENS_ROOT / language / specimen
    listed = subprocess.run(["git", "ls-files", "-z", "--", "."], cwd=root, capture_output=True,
                            check=True).stdout.decode().split("\0")
    h = hashlib.sha256()
    for name in sorted(n for n in listed if n and not NOT_NATIVE_CODE & set(Path(n).parts)):
        h.update(name.encode() + b"\0" + (root / name).read_bytes() + b"\0")
    return h.hexdigest()


def specimen_hashes(cases: list[dict]) -> dict:
    return {f"{lang}/{spec}": specimen_hash(lang, spec)
            for lang, spec in sorted({(c["language"], c["specimen"]) for c in cases})}


def input_hashes() -> dict:
    """Hashes of the LLM results whose witnesses and ports are replayed."""
    return {rel(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
            for p in (LLM_RESULT, PORT_RESULT)}


def replay_inputs(case: dict) -> tuple[list[dict], str]:
    path = rb.REPO_ROOT / case["dir"] / "replay.json"
    text = path.read_text()
    return json.loads(text)["inputs"], rb.sha256(text)


def convert(raw: str, typ: str) -> object:
    if typ == "bool":
        if raw.lower() not in ("true", "false"):
            raise ValueError(f"{raw!r} is not a bool")
        return raw.lower() == "true"
    if typ == "[i64]":
        if not raw.startswith("["):
            raise ValueError(f"{raw!r} is not a list")
        items = [x.strip() for x in raw[1:-1].split(",") if x.strip()]
        return [convert(x, "i64") for x in items]
    if not re.fullmatch(r"-?\d[\d_]*", raw):
        raise ValueError(f"{raw!r} is not an integer")
    value = int(raw.replace("_", ""))
    if not I64[0] <= value <= I64[1]:
        raise ValueError(f"{value} is outside i64")
    return value


def parse_witness(text: str, params: list[tuple[str, str]]) -> tuple[dict | None, str]:
    """Values for every port parameter named in the free-text witness, or None and why not.

    The witness is untrusted text: only `name = literal` pairs for known parameters are read,
    and nothing in it is executed.
    """
    types = dict(params)
    found: dict = {}
    for name, raw in WITNESS_PAIR.findall(text or ""):
        if name in types and name not in found:
            try:
                found[name] = convert(raw, types[name])
            except ValueError as error:
                return None, f"{name}: {error}"
    missing = [n for n, _ in params if n not in found]
    if missing:
        return None, f"no value for {', '.join(missing)}"
    return {n: found[n] for n, _ in params}, ""


def size_problem(values: dict) -> str:
    for name, value in values.items():
        if name in SIZE_PARAMS and isinstance(value, int) and abs(value) > SIZE_LIMIT:
            return f"{name} = {value} needs a collection larger than {SIZE_LIMIT}"
    if isinstance(values.get("rows"), int) and isinstance(values.get("cols"), int) \
            and abs(values["rows"] * values["cols"]) > SIZE_LIMIT:
        return "rows * cols is larger than the replay limit"
    return ""


def native_batch(jobs: list[dict], trees: dict) -> None:
    """Fill job["native"] for jobs {case, language, specimen, variant, values}."""
    groups: dict = {}
    for job in jobs:
        groups.setdefault((job["language"], job["specimen"], job["variant"]), []).append(job)
    for (language, specimen, variant), group in sorted(groups.items()):
        rounds: list[list[dict]] = []
        for job in group:
            for r in rounds:
                if all(j["case"] != job["case"] for j in r):
                    r.append(job)
                    break
            else:
                rounds.append([job])
        for r in rounds:
            rows = run_native(language, specimen, trees[(language, specimen, variant)],
                              [{"case": j["case"], "values": j["values"]} for j in r])
            for j in r:
                j["native"] = rows[j["case"]]


def native_label(native: dict) -> str:
    if native.get("unexpressible"):
        return "unexpressible"
    return "breaks" if native["violates"] else "holds"


def record_runs(path: Path) -> list[list[dict]]:
    return json.loads(path.read_text())["runs"] if path.is_file() else []


def collect(cases: list[dict], mumei_bin: str, jobs: int, timeout: int) -> dict:
    cache: dict = {}
    trees = {}
    for case in cases:
        sdir = rb.SPECIMENS_ROOT / case["language"] / case["specimen"]
        trees[(case["language"], case["specimen"], "buggy")] = sdir
        trees[(case["language"], case["specimen"], "fixed")] = rb.fixed_tree(sdir, cache)
    by_id = {c["id"]: c for c in cases}
    params = {c["id"]: atom_params(c["header"]) for c in cases}

    reference, native_jobs, mm_jobs = [], [], []
    for case in cases:
        inputs, digest = replay_inputs(case)
        for k, inp in enumerate(inputs):
            rec = {"case": case["id"], "language": case["language"], "input": inp["name"],
                   "source": inp["source"], "values": inp["values"], "replay_hash": digest, "native": {}, "port": {}}
            reference.append(rec)
            for v in rb.VARIANTS:
                native_jobs.append({"case": case["id"], "language": case["language"], "specimen": case["specimen"],
                                    "variant": v, "values": inp["values"], "into": (rec["native"], v)})
                mm_jobs.append((case["ports"][v], case["atom"], inp["values"], (rec["port"], v)))

    witnesses = []
    for run_no, run in enumerate(record_runs(LLM_RESULT)):
        for r in run:
            case = by_id.get(r["id"])
            for v in rb.VARIANTS:
                reply = r[v].get("reply") or {}
                if case is None or reply.get("verdict") != "violated":
                    continue
                rec = {"case": r["id"], "language": r["language"], "run": run_no, "variant": v,
                       "witness": reply.get("witness") or ""}
                values, why = parse_witness(rec["witness"], params[r["id"]])
                why = why or (size_problem(values) if values else "")
                if values is None or why:
                    rec.update(classification="unexpressible", reason=why)
                else:
                    rec.update(values=values, native={}, port={})
                    native_jobs.append({"case": r["id"], "language": case["language"], "specimen": case["specimen"],
                                        "variant": v, "values": values, "into": (rec["native"], "result")})
                    mm_jobs.append((case["ports"][v], case["atom"], values, (rec["port"], "reference")))
                witnesses.append(rec)

    ports = []
    first_input = {c["id"]: replay_inputs(c)[0][0]["values"] for c in cases}
    for run_no, run in enumerate(record_runs(PORT_RESULT)):
        for r in run:
            case = by_id.get(r["id"])
            if case is None:
                continue
            for v in rb.VARIANTS:
                body = r[v].get("body")
                rec = {"case": r["id"], "language": r["language"], "run": run_no, "variant": v, "port": {}}
                if not body:
                    rec["status"] = "no port"
                else:
                    try:
                        text = rb.assemble(case, body)
                        rb.split_port(text, case["atom"]) or (_ for _ in ()).throw(ValueError("atom missing"))
                        mm_jobs.append((text, case["atom"], first_input[r["id"]], (rec["port"], "llm")))
                    except Exception as error:  # noqa: BLE001 - recorded, not fatal
                        rec["status"] = "no port"
                        rec["reason"] = str(error)[:200]
                ports.append(rec)

    # Separate rounds per witness/reference so one batch never holds a case twice.
    native_batch([j for j in native_jobs], trees)
    for j in native_jobs:
        j["into"][0][j["into"][1]] = j["native"]

    def mm(job):
        text, atom, values, (target, key) = job
        try:
            target[key] = port_verdict(mumei_bin, text, atom, values, timeout)
        except ValueError as error:
            target[key] = {"verdict": "inconclusive", "status": "bad input", "diagnostics": [str(error)[:200]]}

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        list(pool.map(mm, mm_jobs))
    return finish({"reference": reference, "witnesses": witnesses, "ports": ports}, cases)


def finish(doc: dict, cases: list[dict]) -> dict:
    """Derive every classification from the stored observations (also used by --check)."""
    by_id = {c["id"]: c for c in cases}
    native_ref = {}
    for rec in doc["reference"]:
        rec["agree"] = all(native_label(rec["native"][v]) == rec["port"][v]["verdict"] for v in rb.VARIANTS)
        native_ref.setdefault(rec["case"], rec)
    for rec in doc["witnesses"]:
        if "native" in rec:
            n = rec["native"]["result"]
            rec["classification"] = ("unexpressible" if n.get("unexpressible")
                                     else "reproduced" if n["violates"] else "not reproduced")
            if n.get("unexpressible"):
                rec["reason"] = n["observed"]
    for rec in doc["ports"]:
        if "llm" not in rec["port"]:
            continue
        ref = native_ref.get(rec["case"])
        native = native_label(ref["native"][rec["variant"]]) if ref else "unexpressible"
        got = rec["port"]["llm"]["verdict"]
        rec["native"] = native
        rec["status"] = ("inconclusive" if got == "inconclusive" or native == "unexpressible"
                         else "outside requires" if got == "outside requires"
                         else "matches" if got == native else "behaviour changed")
    doc["summary"] = summarize(doc)
    doc["case_hashes"] = {c["id"]: c["case_hash"] for c in cases if c["id"] in by_id}
    return doc


def summarize(doc: dict) -> dict:
    ref = doc["reference"]
    wit = Counter((w["variant"], w["classification"]) for w in doc["witnesses"])
    prt = Counter((p["variant"], p["status"]) for p in doc["ports"])
    return {
        "reference": {"inputs": len(ref), "agree": sum(r["agree"] for r in ref),
                      "cases": len({r["case"] for r in ref})},
        "witnesses": {f"{v}/{c}": n for (v, c), n in sorted(wit.items())},
        "ports": {f"{v}/{s}": n for (v, s), n in sorted(prt.items())},
    }


def render_markdown(doc: dict) -> str:
    s = doc["summary"]
    lines = ["# Native replay", "",
             "<!-- Generated by scripts/run_native_replay.py; do not edit by hand. -->", "",
             "Each concrete input runs on the native function (Python, Go, Rust, TypeScript, Solidity) through",
             "a driver in `proofs/replay/` and on a `.mm` port pinned to that input. See",
             "[RESULTS.md](RESULTS.md) for the contract benchmark itself.", "",
             "## Reference ports", "",
             f"{s['reference']['agree']} of {s['reference']['inputs']} inputs ({s['reference']['cases']} cases) give the",
             "same verdict natively and on the hand-written ports, for both the buggy and the fixed version.", ""]
    bad = [r for r in doc["reference"] if not r["agree"]]
    for r in bad:
        lines.append(f"- {r['case']} `{r['input']}`: native "
                     + ", ".join(f"{v} {native_label(r['native'][v])}" for v in rb.VARIANTS) + "; port "
                     + ", ".join(f"{v} {r['port'][v]['verdict']}" for v in rb.VARIANTS))
    lines += ["", "## LLM witnesses (LLM only arm)", "",
              "Every \"violated\" verdict's witness is parsed as `name = value` pairs for the port's parameters",
              "and replayed on the native code. Free text is never executed; a witness without a value for",
              "every parameter, or one that needs an oversized collection, is unexpressible.", "",
              "| version | reproduced | not reproduced | unexpressible |", "|---|---:|---:|---:|"]
    for v in rb.VARIANTS:
        lines.append(f"| {v} | " + " | ".join(str(s["witnesses"].get(f"{v}/{c}", 0))
                                              for c in ("reproduced", "not reproduced", "unexpressible")) + " |")
    lines += ["", "Witnesses against the fixed version:", ""]
    for w in sorted((w for w in doc["witnesses"] if w["variant"] == "fixed"), key=lambda w: (w["case"], w["run"])):
        detail = w.get("reason") or w.get("native", {}).get("result", {}).get("observed", "")
        lines.append(f"- {w['case']} (run {w['run'] + 1}): {w['classification']} — {detail}".rstrip(" —"))
    lines += ["", "## LLM ports (mumei + LLM arm)", "",
              "Each port the LLM wrote is pinned to the case's first reference input and compared with the",
              "native verdict on the same input. \"behaviour changed\" means the port no longer does what the",
              "native code does, typically because the bug was fixed while translating.", "",
              "| version | matches | behaviour changed | outside requires | inconclusive | no port |",
              "|---|---:|---:|---:|---:|---:|"]
    for v in rb.VARIANTS:
        lines.append(f"| {v} | " + " | ".join(str(s["ports"].get(f"{v}/{c}", 0))
                                              for c in ("matches", "behaviour changed", "outside requires", "inconclusive", "no port")) + " |")
    changed = sorted({(p["case"], p["variant"]) for p in doc["ports"] if p["status"] == "behaviour changed"})
    if changed:
        lines += ["", "Behaviour changed in: " + ", ".join(f"{c} ({v})" for c, v in changed) + "."]
    return "\n".join(lines) + "\n"


def check(doc: dict | None, cases: list[dict]) -> list[str]:
    """Offline consistency check of the committed replay results."""
    if doc is None:
        return [f"{rel(RESULT_PATH)} is missing"]
    problems = []
    if doc.get("drivers_hash") != drivers_hash():
        problems.append("native drivers changed since the replay was recorded")
    stored_code = doc.get("specimen_hashes", {})
    for key, digest in specimen_hashes(cases).items():
        if stored_code.get(key) != digest:
            problems.append(f"{key}: native code changed since the replay was recorded")
    stored_inputs = doc.get("input_hashes", {})
    for name, digest in input_hashes().items():
        if stored_inputs.get(name) != digest:
            problems.append(f"{name} changed since the replay was recorded")
    for case in cases:
        inputs, digest = replay_inputs(case)
        recs = [r for r in doc["reference"] if r["case"] == case["id"]]
        if [r["input"] for r in recs] != [i["name"] for i in inputs]:
            problems.append(f"{case['id']}: reference inputs missing or duplicated")
        if any(r["replay_hash"] != digest for r in recs):
            problems.append(f"{case['id']}: replay.json changed since the replay was recorded")
        if doc.get("case_hashes", {}).get(case["id"]) != case["case_hash"]:
            problems.append(f"{case['id']}: case changed since the replay was recorded")
    keys = [(w["case"], w["run"], w["variant"]) for w in doc["witnesses"]]
    want = sorted((r["id"], n, v) for n, run in enumerate(record_runs(LLM_RESULT)) for r in run
                  for v in rb.VARIANTS if (r[v].get("reply") or {}).get("verdict") == "violated")
    if sorted(keys) != want:
        problems.append("witness records do not match the LLM only results one to one")
    keys = sorted((p["case"], p["run"], p["variant"]) for p in doc["ports"])
    want = sorted((r["id"], n, v) for n, run in enumerate(record_runs(PORT_RESULT)) for r in run for v in rb.VARIANTS)
    if keys != want:
        problems.append("port records do not match the mumei + LLM results one to one")
    stored = json.dumps(doc, sort_keys=True)
    if json.dumps(finish(json.loads(stored), cases), sort_keys=True) != stored:
        problems.append("stored classifications do not follow from the stored observations")
    if not REPLAY_MD.is_file() or REPLAY_MD.read_text() != render_markdown(doc):
        problems.append(f"{rel(REPLAY_MD)} is out of date")
    return problems


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--check", action="store_true", help="check the committed results offline and exit")
    p.add_argument("--mumei-bin", default=os.environ.get("MUMEI_BIN") or shutil.which("mumei"),
                   help="mumei binary (default: $MUMEI_BIN, then mumei on PATH)")
    p.add_argument("--jobs", type=int, default=4, help="parallel mumei runs (default: 4)")
    p.add_argument("--timeout", type=int, default=120, help="seconds per mumei run (default: 120)")
    return p


def main(argv: list[str]) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    cases, errors = rb.load_cases()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.check:
        doc = json.loads(RESULT_PATH.read_text()) if RESULT_PATH.is_file() else None
        problems = check(doc, cases)
        for line in problems:
            print(f"error: {line}", file=sys.stderr)
        if not problems:
            print(f"ok: {doc['summary']['reference']['inputs']} reference inputs, "
                  f"{len(doc['witnesses'])} witnesses, {len(doc['ports'])} ports")
        return 1 if problems else 0
    if not args.mumei_bin:
        p.error("no mumei binary: pass --mumei-bin or set MUMEI_BIN")
    doc = collect(cases, args.mumei_bin, args.jobs, args.timeout)
    doc = {"recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "drivers_hash": drivers_hash(), "specimen_hashes": specimen_hashes(cases),
           "input_hashes": input_hashes(), **doc}
    RESULT_PATH.write_text(json.dumps(doc, indent=1) + "\n")
    REPLAY_MD.write_text(render_markdown(doc))
    print(json.dumps(doc["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
