#!/usr/bin/env python3
"""Contract benchmark: can a defect be refuted and its fix be proven against one fixed contract?

This is separate from the defect-detection benchmark in specimens/. For every
specimen defect in a category Mumei targets, proofs/<language>/<specimen>/<id>/
holds a requirement, a hand-written port of the buggy and of the fixed function
to Mumei (buggy.mm, fixed.mm) and modelling notes. Both ports share the same
prelude and the same atom header (signature, requires, ensures), so the only
difference is the body.

Arms:
  mumei      the reference ports are verified with `mumei verify --json`. The
             buggy port should be refuted and the fixed port proven. A vacuity
             control re-verifies the fixed port with `ensures: false`; it must
             fail, otherwise the requires clause is unsatisfiable.
  llm        the model gets the product file, the function name, the
             requirement, the modelling notes and the pinned atom header, and
             answers whether the function meets it (no Mumei).
  mumei-llm  the model gets the same input plus the prelude and writes only
             the atom body. The body is assembled under the pinned header and
             verified; a body that declares an atom is rejected, and a proven
             body must also pass the variant-aware fidelity acceptance gate.
  llm-contract
             the model writes the contract instead: it gets the requirement,
             the modelling notes, the prelude and the atom signature, but no
             code and not the reference requires/ensures. Its one contract is
             put on both reference bodies, which mumei verifies, with the
             same vacuity control as the mumei arm. Weak or vacuous generated
             contracts cannot support proof acceptance. This measures the step
             the mumei arm skips: turning a requirement into a contract
             without knowing the defect.

The reference ports were written with knowledge of the defects, so the mumei
arm shows what the contracts can express and that the checker separates the
two versions; it is not a detection result. The LLM arms are the
comparison.

LLM arms use the same OpenAI-compatible settings as run_llm_only.py
(LLM_API_KEY or OPENAI_API_KEY, LLM_BASE_URL, LLM_MODEL). Keys are never
written or printed. `--check` re-validates the cases and the committed results
offline (no Mumei, no model calls).
"""
from __future__ import annotations

import argparse
import ast
import atexit
import concurrent.futures
import datetime as dt
import hashlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import port_fidelity as fidelity  # noqa: E402
from port_fidelity import assemble, header_ensures, split_port  # noqa: E402
from mumei_verify import REFUTATION, classify, verify_text  # noqa: E402
import run_llm_only as llm_only  # noqa: E402
from run_specimen_audits import TARGET_CATEGORIES  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PROOFS_ROOT = REPO_ROOT / "proofs"
SPECIMENS_ROOT = REPO_ROOT / "specimens"
RESULTS_DIR = PROOFS_ROOT / "results"
RESULTS_MD = PROOFS_ROOT / "RESULTS.md"
README = REPO_ROOT / "README.md"
README_START, README_END = "<!-- contract-bench:start -->", "<!-- contract-bench:end -->"
LANGUAGES = ("python", "go", "rust", "typescript", "solidity")
VARIANTS = ("buggy", "fixed")
EXPECTED = {"buggy": "refuted", "fixed": "proven"}
PROMPT_VERSION = 2
ARMS = ("mumei", "llm", "mumei-llm", "llm-contract")
RATE_LIMIT_RETRIES = 8
TRANSPORT_ERROR = "LLM request failed"
FUNC_PATTERNS = {
    "go": r"^func\s+(\([^)]*\)\s*)?{n}\s*\(",
    "rust": r"^\s*(pub(\([^)]*\))?\s+)?fn\s+{n}\s*[<(]",
    "typescript": r"^\s*(export\s+)?(async\s+)?function\s+{n}\s*[<(]|^\s*(public\s+|private\s+)?{n}\s*\(.*\)\s*[:{{]",
    "solidity": r"^\s*(function\s+{n}\s*\(|{n}\s*\()",
}

LLM_SYSTEM = (
    "You review one function against a written requirement and the formal contract that states it. "
    "The contract is written in Mumei over a model of the function's inputs and state; the modelling notes "
    "say how the model maps to the code. Its `requires` clauses are the assumptions you may make about "
    "inputs and state, and its `ensures` clauses are what must hold. Consider every input and state that "
    "satisfies the assumptions. Reply with JSON only: "
    '{"verdict": "holds" | "violated", "witness": "<an input or state that breaks the requirement, or empty>", '
    '"reason": "<one or two sentences>"}.'
)
PORT_SYSTEM = (
    "You translate one function into the Mumei language so that it can be checked against a fixed contract. "
    "Translate the function as it is written, including any mistakes; do not repair it and do not change the contract. "
    "Follow the modelling notes. Mumei bodies are expressions: `let x = e;`, `if c { a } else { b }`, "
    "`while c invariant: I decreases: D { ... };`, struct literals `Name { field: e }`, calls to the prelude atoms. "
    "Reply with JSON only: {\"body\": \"<the statements that go inside body: { ... }>\"}."
)

CONTRACT_SYSTEM = (
    "You write the formal contract of one function from its written requirement, without seeing its code. "
    "The contract is in Mumei, over a model of the function's inputs and state; the modelling notes say how "
    "the model maps to the code. `requires` is what callers guarantee about inputs and state (not what the "
    "function checks itself); `ensures` is what the requirement promises about `result` for every such input. "
    "Each clause is one boolean expression over the parameters, `result` (in ensures), struct fields "
    "(`result.ok`), `len(a)`, `a[i]`, integer arithmetic, comparisons, `&&`, `||`, `!`, `=>` and calls to the "
    "prelude atoms. Write negative literals as `(0 - 3)`. Use `true` for no assumption. Do not guess at a "
    "possible mistake in the code; state the requirement. "
    'Reply with JSON only: {"requires": "<expression>", "ensures": "<expression>"}.'
)
CLAUSE_FORBIDDEN = re.compile(r";|\b(requires|ensures|body)\s*:|\batom\s|\btrusted\b")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_hash(arm: str | None = None) -> str:
    if arm == "llm-contract":
        templates = [inspect.getsource(f) for f in (contract_prompt, contract_header, signature, blind_notes)]
        return sha256(json.dumps([PROMPT_VERSION, CONTRACT_SYSTEM, templates, BLIND_NOTE_REWRITES],
                                 sort_keys=True))[:16]
    templates = [inspect.getsource(f) for f in (llm_prompt, port_prompt, assemble)]
    return sha256(json.dumps([PROMPT_VERSION, LLM_SYSTEM, PORT_SYSTEM, templates], sort_keys=True))[:16]


def defects_by_id(lang: str, specimen: str) -> dict[str, dict]:
    doc = json.loads((SPECIMENS_ROOT / lang / specimen / "DEFECTS.json").read_text())
    return {d["id"]: d for d in (doc["defects"] if isinstance(doc, dict) else doc)}


def target_defects() -> list[tuple[str, str, dict]]:
    out = []
    for lang in LANGUAGES:
        for p in sorted((SPECIMENS_ROOT / lang).glob("*/DEFECTS.json")):
            for d in defects_by_id(lang, p.parent.name).values():
                if d["category"] in TARGET_CATEGORIES:
                    out.append((lang, p.parent.name, d))
    return out


def fixed_tree(specimen_dir: Path, cache: dict) -> Path:
    if specimen_dir not in cache:
        tmp = Path(tempfile.mkdtemp(prefix="contract-bench-"))
        atexit.register(shutil.rmtree, tmp, True)
        shutil.copytree(specimen_dir, tmp / "s")
        subprocess.run(["git", "apply", "fixed.patch"], cwd=tmp / "s", check=True,
                       capture_output=True)
        cache[specimen_dir] = tmp / "s"
    return cache[specimen_dir]


def extract_function(lang: str, source: str, name: str) -> str | None:
    """Source text of the first function or method called `name`, or None."""
    if lang == "python":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None
        lines = source.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                return "\n".join(lines[start - 1:node.end_lineno])
        return None
    pattern = re.compile(FUNC_PATTERNS[lang].format(n=re.escape(name)))
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if pattern.search(line):
            depth, started = 0, False
            for j in range(i, len(lines)):
                depth += lines[j].count("{") - lines[j].count("}")
                started = started or "{" in lines[j]
                if started and depth <= 0:
                    return "\n".join(lines[i:j + 1])
    return None


def load_cases(cache: dict | None = None) -> tuple[list[dict], list[str]]:
    """All cases under proofs/, with validation errors (empty when everything is consistent)."""
    cache = {} if cache is None else cache
    cases, errors = [], []
    for cpath in sorted(PROOFS_ROOT.glob("*/*/*/contract.json")):
        lang, specimen, did = cpath.parts[-4:-1]
        rel = cpath.parent.relative_to(REPO_ROOT).as_posix()
        meta = json.loads(cpath.read_text())
        if meta.get("id") != did:
            errors.append(f"{rel}: id {meta.get('id')!r} does not match the directory")
            continue
        defect = defects_by_id(lang, specimen).get(did) if (SPECIMENS_ROOT / lang / specimen).is_dir() else None
        if defect is None:
            errors.append(f"{rel}: no such defect in specimens/{lang}/{specimen}/DEFECTS.json")
            continue
        for key in ("file", "function"):
            if meta.get(key) != defect[key]:
                errors.append(f"{rel}: {key} {meta.get(key)!r} differs from DEFECTS.json ({defect[key]!r})")
        ports = {v: (cpath.parent / f"{v}.mm").read_text() for v in VARIANTS if (cpath.parent / f"{v}.mm").is_file()}
        if set(ports) != set(VARIANTS):
            errors.append(f"{rel}: buggy.mm and fixed.mm are both required")
            continue
        parts = {v: split_port(t, meta["atom"]) for v, t in ports.items()}
        if any(p is None for p in parts.values()):
            errors.append(f"{rel}: atom {meta['atom']!r} with a body is missing from a port")
            continue
        if parts["buggy"][0] != parts["fixed"][0]:
            errors.append(f"{rel}: buggy and fixed ports have different preludes")
        if parts["buggy"][1] != parts["fixed"][1]:
            errors.append(f"{rel}: buggy and fixed ports have different atom headers (contract)")
        if any(re.search(r"\batom\s", parts[v][2]) for v in VARIANTS):
            errors.append(f"{rel}: the target atom must be the last atom in each port")
        if any(re.search(r"\btrusted\b", t) for t in ports.values()):
            errors.append(f"{rel}: ports must not use trusted atoms")
        if header_ensures(parts["fixed"][1]) is None:
            errors.append(f"{rel}: the atom header has no single-line ensures clause")
        sdir = SPECIMENS_ROOT / lang / specimen
        native = {"buggy": (sdir / defect["file"]).read_text(),
                  "fixed": (fixed_tree(sdir, cache) / defect["file"]).read_text()}
        funcs = {v: extract_function(lang, native[v], defect["function"]) for v in VARIANTS}
        source_hash = sha256(json.dumps([native["buggy"], native["fixed"]]))
        case_hash = sha256(json.dumps([meta, ports["buggy"], ports["fixed"]], sort_keys=True))
        cases.append({
            "id": did, "language": lang, "specimen": specimen, "category": defect["category"],
            "file": defect["file"], "function": defect["function"], "atom": meta["atom"],
            "requirement": meta["requirement"], "notes": meta.get("notes", ""),
            "dir": rel, "ports": ports, "prelude": parts["fixed"][0], "header": parts["fixed"][1],
            "native": native, "functions": funcs,
            "case_hash": case_hash, "source_hash": source_hash,
        })
    have = {c["id"] for c in cases}
    for lang, specimen, d in target_defects():
        if d["id"] not in have and not any(e.startswith(f"proofs/{lang}/{specimen}/{d['id']}:") for e in errors):
            errors.append(f"proofs/{lang}/{specimen}/{d['id']}: no case for target defect ({d['category']})")
    return cases, errors


FAILURE_KINDS = ("unsupported", "inconclusive", "environment_failure", "budget_exhausted")


def failure_kind(result: dict) -> str | None:
    """Conservative reason an outcome is inconclusive, derived when old records lack one."""
    if result.get("outcome") != "inconclusive":
        return None
    explicit = result.get("failure_kind")
    if explicit in FAILURE_KINDS:
        return explicit
    status = str(result.get("status", ""))
    diagnostics = result.get("diagnostics") or []
    messages = " ".join(str(d.get("message", "")) for d in diagnostics if isinstance(d, dict))
    codes = {str(d.get("code", "")) for d in diagnostics if isinstance(d, dict)}
    if status == "timeout":
        return "budget_exhausted"
    if status.startswith(TRANSPORT_ERROR) or status.startswith("no-json"):
        return "environment_failure"
    if (status in {"input_error", "no-contract", "no-body"} or "input_error" in codes
            or "Unknown function" in messages):
        return "unsupported"
    return "inconclusive"


def fidelity_replay_verdict(mumei_bin: str, case: dict, port: str, values: dict, timeout: int) -> dict:
    try:
        return fidelity.port_verdict(mumei_bin, port, case["atom"], values, timeout)
    except ValueError as error:
        return {"verdict": "inconclusive", "status": "bad input", "diagnostics": [str(error)],
                "verification_attempted": False}


def replay_verification_measurement(verdicts: list[dict]) -> dict:
    """Aggregate verifier-call measurement for semantic replay verdicts."""
    seconds, budget, timed, budgeted, expected = 0.0, 0.0, 0, 0, 0
    for verdict in verdicts:
        attempted = verdict.get("verification_attempted")
        if attempted is False or verdict.get("status") in {"bad input", "missing or invalid body"}:
            continue
        expected += 1
        if numeric_measurement(verdict.get("seconds")):
            timed += 1
            seconds += verdict["seconds"]
        if numeric_measurement(verdict.get("budget_seconds")):
            budgeted += 1
            budget += verdict["budget_seconds"]
    return {"seconds": round(seconds, 1), "timed_calls": timed, "expected_calls": expected,
            "budget_seconds": round(budget, 1), "budgeted_calls": budgeted}


def replay_unresolved_counts(verdicts: list[dict]) -> dict:
    """Unresolved semantic-replay verdicts by the shared failure-kind vocabulary."""
    counts = Counter()
    for verdict in verdicts:
        if verdict.get("verdict") != "inconclusive":
            continue
        kind = verdict.get("failure_kind")
        if kind not in FAILURE_KINDS:
            kind = "unsupported" if verdict.get("status") == "bad input" else "inconclusive"
        counts[kind] += 1
    return {kind: counts[kind] for kind in FAILURE_KINDS}


def semantic_port_replay(case: dict, body: str, mumei_bin: str, timeout: int,
                         variant: str = "buggy") -> dict:
    """Replay reference inputs on a proven candidate port of one source variant.

    This is semantic fidelity evidence, not a verdict change. For a buggy
    candidate, ``diverged`` means the pinned buggy reference breaks where the
    candidate holds; for a fixed candidate, it means the candidate breaks where
    the fixed reference holds. Missing fixtures or verifier-unresolved rows are
    explicit non-evidence.
    """
    try:
        inputs, input_hash = fidelity.replay_inputs(case)
    except (OSError, ValueError, KeyError) as error:
        return {"outcome": "unavailable", "inputs": [], "error": type(error).__name__}
    try:
        port = assemble(case, body)
    except (KeyError, ValueError) as error:
        return {"outcome": "unavailable", "inputs": [], "error": str(error)}
    rows = []
    for witness in inputs:
        if not isinstance(witness.get("values"), dict):
            return {"outcome": "unavailable", "inputs": [], "error": "missing witness values"}
        reference = fidelity_replay_verdict(mumei_bin, case, case["ports"][variant], witness["values"], timeout)
        candidate = fidelity_replay_verdict(mumei_bin, case, port, witness["values"], timeout)
        rows.append({"name": witness.get("name", "input"),
                     "reference": reference["verdict"], "candidate": candidate["verdict"],
                     "input": {**witness, "reference": reference, "llm": candidate}})
    verdicts = [part for row in rows for part in (row["input"]["reference"], row["input"]["llm"])]
    outcome = fidelity.outcome if variant == "buggy" else fidelity.fixed_variant_outcome
    return {"outcome": outcome([row["input"] for row in rows]),
            "input_hash": input_hash,
            "inputs": [{"name": row["name"], "source": row["input"].get("source"),
                        "values": row["input"].get("values"),
                        "reference": row["reference"], "candidate": row["candidate"]} for row in rows],
            "unresolved": replay_unresolved_counts(verdicts),
            "verification": replay_verification_measurement(verdicts)}


def fidelity_gate_reasons(gate: dict) -> list[str]:
    """Human-readable reasons a fidelity gate blocks acceptance."""
    reasons = []
    blocking = fidelity.blocking_lint_findings(gate.get("lint_findings") or [])
    if blocking:
        reasons.append("lint:" + ",".join(sorted({finding["kind"] for finding in blocking})))
    if gate.get("source") == "generated_contract":
        if gate.get("vacuity") == "vacuous":
            reasons.append("vacuity:vacuous")
        return reasons
    semantic = gate.get("semantic_replay", {})
    outcome = semantic.get("outcome")
    confirming = "still_refutes" if gate.get("variant", "buggy") == "buggy" else "still_holds"
    if outcome == "diverged":
        reasons.append("replay:diverged")
    elif outcome != confirming:
        reasons.append(f"replay:no-confirming-evidence:{outcome}")
    return reasons


def apply_port_fidelity_gate(case: dict, body: str, result: dict, mumei_bin: str, timeout: int,
                             variant: str = "buggy") -> dict:
    """Attach fidelity acceptance evidence to a raw verifier result.

    The recorded benchmark outcome remains the raw verifier outcome. Consumers
    that need product-level verification acceptance use ``project_fidelity_result``;
    neither lint nor replay is represented as a formal proof verdict.
    """
    if result.get("outcome") != "proven":
        return result
    linted = fidelity.lint_findings(case, body, variant) if fidelity.usable_body(body) else [
        {"kind": "invalid_body", "message": "candidate body cannot be pinned safely"}
    ]
    semantic = semantic_port_replay(case, body, mumei_bin, timeout, variant)
    confirming = "still_refutes" if variant == "buggy" else "still_holds"
    blocking = fidelity.blocking_lint_findings(linted)
    # Confirming reference replay is stronger semantic evidence than syntactic lint.
    # Lint can still block when replay is unavailable or inconclusive, and replay
    # divergence always blocks; neither is represented as a formal refutation.
    blocked = semantic["outcome"] != confirming
    gate = {"schema": "mumei-demo.port-fidelity-gate/v2", "variant": variant,
            "decision": "blocked" if blocked else "accepted",
            "lint_findings": linted, "blocking_lint_findings": blocking,
            "semantic_replay": semantic}
    return {**result, "fidelity_gate": gate}


def fidelity_projection_failure_kind(gate: dict) -> str:
    """Failure subtype for a blocked fidelity acceptance projection.

    High-confidence lint or semantic divergence means the candidate is unsupported
    as fidelity evidence. Missing confirming replay without such evidence remains
    inconclusive, while verifier transport/budget/input subtypes stay explicit.
    """
    if gate.get("source") == "generated_contract" and (gate.get("lint_findings") or gate.get("vacuity") == "vacuous"):
        return "unsupported"
    blocking = gate.get("blocking_lint_findings")
    if blocking is None:
        blocking = fidelity.blocking_lint_findings(gate.get("lint_findings") or [])
    semantic = gate.get("semantic_replay", {})
    if blocking or semantic.get("outcome") == "diverged":
        return "unsupported"
    unresolved = semantic.get("unresolved") or {}
    for kind in ("environment_failure", "budget_exhausted", "unsupported"):
        if unresolved.get(kind):
            return kind
    return "inconclusive"


def project_fidelity_result(result: dict) -> dict:
    """Project a raw verifier result through its fidelity acceptance gate.

    This copy is report/scoring state only: the committed result keeps the raw
    verifier outcome in ``outcome``. A blocked raw proof becomes unsupported/
    inconclusive evidence, never a formal refutation.
    """
    gate = result.get("fidelity_gate") or {}
    if result.get("outcome") != "proven" or gate.get("decision") != "blocked":
        return result
    reasons = fidelity_gate_reasons(gate)
    return {**result,
            "verifier_outcome": result["outcome"],
            "verifier_status": result.get("status", ""),
            "outcome": "inconclusive",
            "status": "fidelity-gate (" + "; ".join(reasons) + ")",
            "failure_kind": fidelity_projection_failure_kind(gate)}


def project_fidelity_record(record: dict) -> dict:
    """Project both variant results in one benchmark record through fidelity gates."""
    return {**record, **{variant: project_fidelity_result(record[variant])
                         for variant in VARIANTS if isinstance(record.get(variant), dict)}}


def vacuity_text(case: dict, header: str | None = None) -> str:
    header = case["header"] if header is None else header
    ens = header_ensures(header)
    header = header.replace(f"ensures: {ens};", "ensures: false;", 1)
    return case["prelude"] + header + split_port(case["ports"]["fixed"], case["atom"])[2]


CERT_FILE = "fixed.proof.json"
TRUST = {"unsat": "z3", "lean_verified": "lean"}
TRUST_LABEL = {"z3": "Z3", "lean": "Lean", "unproven": "not proven"}
LAKE_ERROR = re.compile(r"^error: \S*?\.lean:\d+:\d+: (.*)$", re.MULTILINE)


def cert_summary(text: str, case: dict, port: str | None = None, file: str = CERT_FILE) -> dict:
    """What a proof certificate says about the case's atom, and the hashes that pin it to the fixed port.

    `port` is the certified text when it is not the reference fixed port (a mumei-llm port).
    """
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return {"status": "malformed"}
    atoms = doc.get("atoms") if isinstance(doc, dict) else None
    atom = next((a for a in atoms or [] if isinstance(a, dict) and a.get("name") == case["atom"]), None)
    result = atom.get("z3_check_result") if atom else None
    return {"status": "recorded", "file": file, "sha256": sha256(text),
            "port_sha256": sha256(case["ports"]["fixed"] if port is None else port), "all_verified": isinstance(doc, dict) and doc.get("all_verified") is True,
            "z3_check_result": result, "trust": TRUST.get(result, "unproven")}


def certify(mumei_bin: str, case: dict, timeout: int, port: str | None = None,
            file: str = CERT_FILE) -> tuple[dict, str | None]:
    """Emit a proof certificate for the fixed port (or `port`) and re-check it: (summary, certificate text)."""
    with tempfile.TemporaryDirectory(prefix="contract-bench-") as tmp:
        (Path(tmp) / "fixed.mm").write_text(case["ports"]["fixed"] if port is None else port)
        try:
            subprocess.run([mumei_bin, "verify", "--json", "--proof-cert", "--output", CERT_FILE, "fixed.mm"],
                           cwd=tmp, capture_output=True, text=True, timeout=timeout, check=False)
            cert = Path(tmp) / CERT_FILE
            if not cert.is_file():
                return {"status": "not-emitted"}, None
            check = subprocess.run([mumei_bin, "verify-cert", "--strict", CERT_FILE, "fixed.mm"],
                                   cwd=tmp, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return {"status": "timeout"}, None
        text = cert.read_text()
    return {**cert_summary(text, case, port, file), "verify_cert": "ok" if check.returncode == 0 else "failed"}, text


def llm_cert_file(model: str, seed: int) -> str:
    """Where a proven mumei-llm fixed port's certificate lives, relative to the case directory."""
    return f"mumei-llm/{llm_only.model_slug(model)}-run{seed + 1}.{CERT_FILE}"


def lean_dual_check(lean_dir: str, case: dict, cert_text: str, timeout: int) -> dict:
    """Restate the certified Z3 obligation in Lean 4 with the mumei-lean bridge and record whether it closes.

    The bridge builds inside the mumei-lean checkout, so calls must not run in parallel.
    """
    module = Path(lean_dir) / "generated" / "Generated" / "Fixed.lean"
    with tempfile.TemporaryDirectory(prefix="contract-bench-lean-") as tmp:
        cert, out = Path(tmp) / CERT_FILE, Path(tmp) / "fixed.lean-cert.json"
        cert.write_text(cert_text)
        previous = module.read_bytes() if module.is_file() else None
        try:
            proc = subprocess.run([sys.executable, "scripts/bridge.py", "--cert", str(cert), "--dual-check",
                                   "--lean-cert-out", str(out)],
                                  cwd=lean_dir, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return {"status": "timeout"}
        finally:
            if previous is None:
                module.unlink(missing_ok=True)
            else:
                module.write_bytes(previous)
        try:
            doc = json.loads(out.read_text())
        except (OSError, json.JSONDecodeError):
            return {"status": "no-certificate"}
    atoms = doc.get("atoms") if isinstance(doc, dict) else None
    atom = next((a for a in atoms or [] if isinstance(a, dict) and a.get("name") == case["atom"]), {})
    check = atom.get("lean_dual_check")
    result = {"status": str(check.get("status") or "not-checked") if isinstance(check, dict) else "not-checked"}
    if result["status"] == "failed":
        error = LAKE_ERROR.search(proc.stdout + proc.stderr)
        if error:
            result["error"] = error.group(1)[:200]
    return result


def lake_on_path() -> bool:
    return shutil.which("lake") is not None


def git_identity(path: str) -> dict:
    def git(*args: str) -> str | None:
        res = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, check=False)
        return res.stdout.strip() if res.returncode == 0 else None
    commit = git("rev-parse", "HEAD")
    return {"commit": commit, "dirty": bool(git("status", "--porcelain", "--untracked-files=no")) if commit else None}


def vacuity_result(case: dict, out: dict, mumei_bin: str, timeout: int,
                   header: str | None = None) -> tuple[str, dict]:
    control = verify_text(mumei_bin, vacuity_text(case, header), timeout)
    # mumei may reject `ensures: false` up front as contradicting `requires`. That alone would also pass an
    # unsatisfiable `requires`, so it only counts when the buggy port was refuted, i.e. some input meets `requires`.
    contradiction = control["status"] == "failed" and control["diagnostics"] and all(
        "Spec contradiction" in d["message"] or REFUTATION.search(d["message"]) for d in control["diagnostics"])
    rejected = control["outcome"] == "refuted" or (contradiction and out["buggy"]["outcome"] == "refuted")
    status = "ok" if rejected else ("vacuous" if control["outcome"] == "proven" else "inconclusive")
    return status, control


def vacuity(case: dict, out: dict, mumei_bin: str, timeout: int, header: str | None = None) -> str:
    return vacuity_result(case, out, mumei_bin, timeout, header)[0]


def verifier_startup_failure(result: dict) -> bool:
    return (result.get("failure_kind") == "environment_failure"
            and str(result.get("status", "")).startswith("verifier startup failed"))


def fail_on_verifier_startup(results: list[dict]) -> None:
    if any(verifier_startup_failure(result) for result in results):
        raise RuntimeError("verifier startup failed; benchmark results and certificates were not updated")


def run_mumei_case(case: dict, mumei_bin: str, timeout: int) -> dict:
    out = {k: case[k] for k in ("id", "language", "specimen", "category", "function", "case_hash", "source_hash")}
    for v in VARIANTS:
        out[v] = verify_text(mumei_bin, case["ports"][v], timeout)
    out["vacuity"], out["vacuity_control"] = vacuity_result(case, out, mumei_bin, timeout)
    fail_on_verifier_startup([out["buggy"], out["fixed"], out["vacuity_control"]])
    path = REPO_ROOT / case["dir"] / CERT_FILE
    path.unlink(missing_ok=True)
    if out["fixed"]["outcome"] == "proven":
        out["fixed"]["certificate"], text = certify(mumei_bin, case, timeout)
        if text is not None:
            path.write_text(text)
    return out


def cert_problems(rel: str, fixed: dict, case: dict, port: str | None, label: str) -> list[str]:
    """Offline checks of one committed certificate against its record and the port it certifies."""
    path, cert = REPO_ROOT / rel, fixed.get("certificate")
    if fixed["outcome"] != "proven":
        return [f"{rel}: the fixed port is not proven, so it has no certificate to keep"] if path.is_file() else []
    if not cert or cert.get("status") != "recorded":
        return [f"{label}: the proven fixed port has no proof certificate"]
    if not path.is_file():
        return [f"{rel} is missing"]
    text = path.read_text()
    if sha256(text) != cert.get("sha256"):
        return [f"{rel} does not match its recorded hash"]
    if cert.get("port_sha256") != sha256(case["ports"]["fixed"] if port is None else port):
        what = "fixed.mm" if port is None else "the port"
        return [f"{rel} is stale: {what} changed after it was certified"]
    file = rel.rsplit(f"{case['dir']}/", 1)[-1]
    if {**cert_summary(text, case, port, file), "verify_cert": cert.get("verify_cert")} != cert:
        return [f"{rel} does not say what its record says"]
    if cert["verify_cert"] != "ok" or cert["trust"] == "unproven" or not cert["all_verified"]:
        return [f"{rel} does not prove {case['atom']} (trust {cert['trust']}, verify-cert {cert['verify_cert']})"]
    return []


def certificate_problems(cases: list[dict], results: list[dict]) -> list[str]:
    """Offline: every proven fixed port (reference and mumei-llm) has a committed certificate that matches
    its record and port, and no certificate is left over from another run."""
    by_id, out = {c["id"]: c for c in cases}, []
    ref = next((d for d in results if d["arm"] == "mumei"), None)
    if ref is not None and ref["runs"]:
        for r in ref["runs"][0]:
            c = by_id.get(r["id"])
            if c is not None:
                out += cert_problems(f"{c['dir']}/{CERT_FILE}", r["fixed"], c, None, r["id"])
    expected = set()
    for d in results:
        if d["arm"] != "mumei-llm":
            continue
        for seed, run in enumerate(d["runs"]):
            for r in run:
                c = by_id.get(r["id"])
                if c is None:
                    continue
                rel = f"{c['dir']}/{llm_cert_file(d['model'], seed)}"
                expected.add(rel)
                port = assemble(c, r["fixed"]["body"]) if isinstance(r["fixed"].get("body"), str) else None
                if r["fixed"]["outcome"] == "proven" and port is None:
                    out.append(f"{d['arm']} ({d['model']}) run {seed + 1}: {r['id']} is proven without a body")
                    continue
                out += cert_problems(rel, r["fixed"], c, port or "", f"{d['arm']} run {seed + 1}: {r['id']}")
    for path in sorted(PROOFS_ROOT.glob(f"*/*/*/mumei-llm/*.{CERT_FILE}")):
        rel = str(path.relative_to(REPO_ROOT))
        if rel not in expected:
            out.append(f"{rel} belongs to no recorded mumei-llm run")
    return out


def llm_prompt(case: dict, variant: str) -> list[dict]:
    user = (f"Language: {case['language']}\nFile: {case['file']}\nFunction: {case['function']}\n"
            f"Requirement: {case['requirement']}\nModelling notes: {case['notes'] or '(none)'}\n\n"
            f"Contract:\n```\n{case['header'].rstrip()}\n```\n\n"
            f"Does `{case['function']}` meet the requirement under these assumptions?\n\n"
            f"```\n{case['native'][variant]}\n```")
    return [{"role": "system", "content": LLM_SYSTEM}, {"role": "user", "content": user}]


def port_prompt(case: dict, variant: str) -> list[dict]:
    user = (f"Language: {case['language']}\nFile: {case['file']}\nFunction to translate: {case['function']}\n"
            f"Requirement: {case['requirement']}\nModelling notes: {case['notes'] or '(none)'}\n\n"
            f"Mumei prelude (already defined):\n```\n{case['prelude']}```\n\n"
            f"Pinned atom header; write only what goes inside body: {{ ... }}:\n```\n{case['header']}body: {{ ... }}\n```\n\n"
            f"Source file:\n```\n{case['native'][variant]}\n```")
    return [{"role": "system", "content": PORT_SYSTEM}, {"role": "user", "content": user}]


def signature(case: dict) -> str:
    """The atom's signature line, without requires/ensures."""
    return case["header"].splitlines()[0].rstrip()


BLIND_NOTE_LEAK = re.compile(r"\b(original|fixed version|buggy)\b", re.IGNORECASE)


BLIND_NOTE_REWRITES = (
    ("the fixed version's TrimPrefix result is `sku` with `has_sku`", "the SKU segment is `sku`, present when `has_sku`"),
    ("The fixed version rejects a negative -top in main before formatSummary runs",
     "A negative -top is rejected in main before formatSummary runs"),
    ("the fixed version's closed/same-account check", "the check that both accounts are open and different"),
    (" In the original, the allowance comes from the wrapping remaining_daily_allowance, so an overspent account "
     "never hits the limit check; the fixed version also subtracts already queued amounts.", ""),
    ("; the direct refund call of the original is assumed to succeed", ""),
    ("the fixed version's checked subtraction reverts (ok == false)", "a revert is ok == false"),
)


def blind_notes(notes: str) -> str:
    """The modelling notes with the wording about the original or the fixed implementation rewritten away.

    Rewriting keeps the modelling conventions (what `ok == false` or a helper stands for) that dropping the
    whole sentence would lose. A note that still names an implementation fails the committed-notes test."""
    for old, new in BLIND_NOTE_REWRITES:
        notes = notes.replace(old, new)
    return notes.strip()


def contract_prompt(case: dict) -> list[dict]:
    prelude = case["prelude"].strip() or "(none)"
    user = (f"Language of the original code: {case['language']}\nFunction: {case['function']}\n"
            f"Requirement: {case['requirement']}\nModelling notes: {blind_notes(case['notes']) or '(none)'}\n\n"
            f"Mumei prelude (already defined):\n```\n{prelude}\n```\n\n"
            f"Write requires and ensures for this atom:\n```\n{signature(case)}\n```")
    return [{"role": "system", "content": CONTRACT_SYSTEM}, {"role": "user", "content": user}]


def contract_header(case: dict, requires: str, ensures: str) -> str:
    return f"{signature(case)}\n    requires: {requires};\n    ensures: {ensures};\n    "


def contract_clauses(reply: dict | None) -> tuple[str, str] | None:
    """(requires, ensures) from a model reply, each a single expression, or None."""
    clauses = []
    for key in ("requires", "ensures"):
        value = (reply or {}).get(key)
        if not isinstance(value, str):
            return None
        value = " ".join(value.split()).removesuffix(";").strip()
        if not value or CLAUSE_FORBIDDEN.search(value) or len(value) > 2000:
            return None
        clauses.append(value)
    return clauses[0], clauses[1]


def run_contract_case(case: dict, provider, seed: int, mumei_bin: str, timeout: int) -> dict:
    out = {k: case[k] for k in ("id", "language", "specimen", "category", "function", "case_hash", "source_hash")}
    try:
        text, usage = provider.complete(contract_prompt(case), seed)
    except RuntimeError as e:
        status = str(e) if str(e).startswith(TRANSPORT_ERROR) else f"{TRANSPORT_ERROR}: {e}"
        out.update({v: {"outcome": "inconclusive", "status": status} for v in VARIANTS})
        out["usage"] = None
        return out
    out["usage"] = usage
    clauses = contract_clauses(parse_json_reply(text))
    if clauses is None:
        out.update({v: {"outcome": "inconclusive", "status": "no-contract"} for v in VARIANTS})
        out["reply"] = text[:2000]
        return out
    out["contract"] = {"requires": clauses[0], "ensures": clauses[1]}
    header = contract_header(case, *clauses)
    for v in VARIANTS:
        out[v] = verify_text(mumei_bin, case["prelude"] + header + split_port(case["ports"][v], case["atom"])[2], timeout)
    out["vacuity"], out["vacuity_control"] = vacuity_result(case, out, mumei_bin, timeout, header)
    return apply_contract_fidelity_gate(out)


def parse_json_reply(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n|\n?```$", "", text)
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None
    return doc if isinstance(doc, dict) else None


def run_llm_case(case: dict, provider, arm: str, seed: int, mumei_bin: str | None, timeout: int) -> dict:
    out = {k: case[k] for k in ("id", "language", "specimen", "category", "function", "case_hash", "source_hash")}
    for v in VARIANTS:
        prompt = llm_prompt(case, v) if arm == "llm" else port_prompt(case, v)
        try:
            text, usage = provider.complete(prompt, seed)
        except RuntimeError as e:
            out[v] = {"outcome": "inconclusive", "status": str(e), "usage": None}
            continue
        reply = parse_json_reply(text)
        if arm == "llm":
            verdict = (reply or {}).get("verdict")
            outcome = {"violated": "refuted", "holds": "proven"}.get(verdict, "inconclusive")
            out[v] = {"outcome": outcome, "status": str(verdict), "reply": reply if reply else text[:2000], "usage": usage}
        else:
            body = (reply or {}).get("body")
            if not isinstance(body, str) or not body.strip() or "atom " in body:
                out[v] = {"outcome": "inconclusive", "status": "no-body", "reply": text[:2000], "usage": usage}
                continue
            result = verify_text(mumei_bin, assemble(case, body), timeout)
            if verifier_startup_failure(result):
                raise RuntimeError("verifier startup failed; benchmark results and certificates were not updated")
            if arm == "mumei-llm":
                result = apply_port_fidelity_gate(case, body, result, mumei_bin, timeout, v)
            out[v] = {**result, "body": body, "usage": usage}
    if arm == "mumei-llm":
        fail_on_verifier_startup([out[v] for v in VARIANTS])
        file = llm_cert_file(provider.model, seed)
        path = REPO_ROOT / case["dir"] / file
        path.unlink(missing_ok=True)
        if out["fixed"]["outcome"] == "proven":
            out["fixed"]["certificate"], text = certify(mumei_bin, case, timeout, assemble(case, out["fixed"]["body"]), file)
            if text is not None:
                path.parent.mkdir(exist_ok=True)
                path.write_text(text)
    return out


def score(records: list[dict]) -> dict:
    records = [project_fidelity_record(r) for r in records]
    s = {"cases": len(records), "buggy_refuted": 0, "fixed_proven": 0, "both": 0,
         "wrong_accept": 0, "wrong_reject": 0, "false_acceptance": 0, "false_positive": 0,
         "unsupported": 0, "inconclusive": 0, "environment_failure": 0,
         "budget_exhausted": 0, "errors": 0, "vacuous": 0, "fidelity_blocked": 0}
    for r in records:
        b, f = r["buggy"]["outcome"], r["fixed"]["outcome"]
        s["buggy_refuted"] += b == "refuted"
        s["fixed_proven"] += f == "proven"
        s["both"] += b == "refuted" and f == "proven"
        s["wrong_accept"] += b == "proven"
        s["wrong_reject"] += f == "refuted"
        s["false_acceptance"] += b == "proven"
        s["false_positive"] += f == "refuted"
        for v in VARIANTS:
            if r[v]["outcome"] == "inconclusive":
                kind = failure_kind(r[v]) or "inconclusive"
                s[kind] += 1
                if kind == "environment_failure":
                    s["errors"] += 1
        s["vacuous"] += r.get("vacuity") == "vacuous"
        s["fidelity_blocked"] += sum(
            r[v].get("fidelity_gate", {}).get("decision") == "blocked" for v in VARIANTS
        )
    return s


def verification_measurement_slots(record: dict) -> list[dict]:
    """Verifier outcome/control slots, including uninstrumented historical records.

    Verifier outcomes always carry `diagnostics`; direct-LLM outcomes do not. Transport or
    generation failures before the verifier starts therefore do not create a slot. A record
    with a vacuity verdict did run the control even when old JSON lacks its measurement.
    """
    slots = []
    for v in VARIANTS:
        result = record.get(v)
        if isinstance(result, dict) and any(k in result for k in ("diagnostics", "seconds", "budget_seconds")):
            slots.append(result)
    if "vacuity" in record:
        control = record.get("vacuity_control")
        slots.append(control if isinstance(control, dict) else {})
    return slots


def numeric_measurement(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def usage_total(records: list[dict]) -> dict:
    cost, seconds, calls, unknown = 0.0, 0.0, 0, 0
    verification_seconds, verification_budget = 0.0, 0.0
    verification_timed, verification_budgeted, verification_expected = 0, 0, 0
    for r in records:
        slots = verification_measurement_slots(r)
        verification_expected += len(slots)
        for result in slots:
            if numeric_measurement(result.get("seconds")):
                verification_timed += 1
                verification_seconds += result["seconds"]
            if numeric_measurement(result.get("budget_seconds")):
                verification_budgeted += 1
                verification_budget += result["budget_seconds"]
        for v in VARIANTS:
            measurement = (r[v].get("fidelity_gate", {}).get("semantic_replay", {}) or {}).get("verification") or {}
            verification_expected += measurement.get("expected_calls", 0)
            verification_timed += measurement.get("timed_calls", 0)
            verification_seconds += measurement.get("seconds", 0.0)
            verification_budgeted += measurement.get("budgeted_calls", 0)
            verification_budget += measurement.get("budget_seconds", 0.0)
        for u in [r[v].get("usage") for v in VARIANTS] + [r.get("usage")]:
            if not u:
                continue
            calls += 1
            seconds += u.get("seconds") or 0
            if u.get("cost_usd") is None:
                unknown += 1
            else:
                cost += u["cost_usd"]
    return {"calls": calls, "cost_usd": round(cost, 4), "model_seconds": round(seconds, 1),
            "cost_unknown_calls": unknown,
            "verification_seconds": round(verification_seconds, 1),
            "verification_timed_calls": verification_timed,
            "verification_expected_calls": verification_expected,
            "verification_budget_seconds": round(verification_budget, 1),
            "verification_budgeted_calls": verification_budgeted}


def result_path(arm: str, model: str | None) -> Path:
    return RESULTS_DIR / (f"{arm}.json" if arm == "mumei" else f"{arm}-{llm_only.model_slug(model)}.json")


def load_results() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(RESULTS_DIR.glob("*.json"))]


def stale_records(cases: list[dict], results: list[dict]) -> list[str]:
    by_id = {c["id"]: c for c in cases}
    out = []
    for doc in results:
        if doc["arm"] != "mumei" and doc.get("prompt_hash") != prompt_hash(doc["arm"]):
            out.append(f"{doc['arm']} ({doc.get('model')}): prompt changed")
        label = f"{doc['arm']} ({doc.get('model') or 'reference'})"
        for n, run in enumerate(doc["runs"], 1):
            for r in run:
                c = by_id.get(r["id"])
                if c is None or c["case_hash"] != r["case_hash"] or c["source_hash"] != r["source_hash"]:
                    out.append(f"{label}: {r['id']} is stale")
            ids = [r["id"] for r in run]
            for missing in sorted(set(by_id) - set(ids)):
                out.append(f"{label}: {missing} has no result in run {n}")
            for dup in sorted({i for i in ids if ids.count(i) > 1}):
                out.append(f"{label}: {dup} appears more than once in run {n}")
    return out


def median(values: list[int]) -> float:
    v = sorted(values)
    return v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2


def arm_rows(results: list[dict]) -> list[dict]:
    order = {a: i for i, a in enumerate(ARMS)}
    rows = []
    for doc in sorted(results, key=lambda d: (order.get(d["arm"], 9), d.get("model") or "")):
        scores = [score(run) for run in doc["runs"]]
        row = {"arm": doc["arm"], "model": doc.get("model"), "runs": len(scores),
               "recorded_at": doc.get("recorded_at"), "verifier": doc.get("verifier") or {}}
        for k in scores[0]:
            vals = [s[k] for s in scores]
            row[k] = median(vals)
            row[k + "_range"] = (min(vals), max(vals))
        for variant in VARIANTS:
            key = f"raw_{variant}_proven"
            vals = [sum(1 for r in run if r[variant].get("outcome") == "proven") for run in doc["runs"]]
            row[key] = median(vals)
            row[key + "_range"] = (min(vals), max(vals))
        row["usage"] = usage_total([r for run in doc["runs"] for r in run])
        row["by_language"] = {}
        for lang in LANGUAGES:
            per = [score([r for r in run if r["language"] == lang]) for run in doc["runs"]]
            if per and per[0]["cases"]:
                row["by_language"][lang] = {k: median([p[k] for p in per]) for k in ("cases", "both", "wrong_accept", "wrong_reject")}
        rows.append(row)
    return rows


ARM_LABEL = {"mumei": "mumei (reference ports)", "llm": "LLM only (judges the source)",
             "mumei-llm": "mumei + LLM (LLM ports, mumei checks)",
             "llm-contract": "mumei + LLM contract (LLM writes the contract, reference ports)"}


def fmt(row: dict, key: str) -> str:
    v = row[key]
    v = int(v) if float(v).is_integer() else v
    lo, hi = row[key + "_range"]
    return f"{v}" if lo == hi else f"{v} ({lo}–{hi})"


def render_table(rows: list[dict]) -> str:
    lines = ["| Arm | Model | Runs | Buggy refuted | Fixed proven | Both right | False acceptance | False positive | Unsupported | Inconclusive | Env failure | Budget exhausted | Cost |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        cost = "—" if r["arm"] == "mumei" else f"${r['usage']['cost_usd']:.2f}"
        lines.append(f"| {ARM_LABEL.get(r['arm'], r['arm'])} | {r['model'] or '—'} | {r['runs']} | "
                     f"{fmt(r, 'buggy_refuted')} / {r['cases']} | {fmt(r, 'fixed_proven')} / {r['cases']} | "
                     f"{fmt(r, 'both')} | {fmt(r, 'false_acceptance')} | {fmt(r, 'false_positive')} | "
                     f"{fmt(r, 'unsupported')} | {fmt(r, 'inconclusive')} | {fmt(r, 'environment_failure')} | "
                     f"{fmt(r, 'budget_exhausted')} | {cost} |")
    return "\n".join(lines)


def render_measurement_table(rows: list[dict]) -> str:
    lines = ["| Arm | Model | Model time | Verification time | Verification budget |",
             "|---|---|---:|---:|---:|"]
    for r in rows:
        usage = r["usage"]
        model_time = "—" if r["arm"] == "mumei" else f"{usage['model_seconds']:.1f}s"
        expected = usage["verification_expected_calls"]
        if expected:
            seconds = f"{usage['verification_seconds']:.1f}s" if usage["verification_timed_calls"] else "—"
            verification_time = f"{seconds} / {usage['verification_timed_calls']} of {expected} calls"
            budget = f"{usage['verification_budget_seconds']:.1f}s" if usage["verification_budgeted_calls"] else "—"
            verification_budget = f"{budget} / {usage['verification_budgeted_calls']} of {expected} calls"
        else:
            verification_time = "—"
            verification_budget = "—"
        lines.append(f"| {ARM_LABEL.get(r['arm'], r['arm'])} | {r['model'] or '—'} | {model_time} | "
                     f"{verification_time} | {verification_budget} |")
    return "\n".join(lines)


def render_markdown(rows: list[dict], results: list[dict], stale: list[str]) -> str:
    out = ["# Contract benchmark results", "",
           "<!-- Generated by scripts/run_contract_bench.py; do not edit by hand. -->", "",
           f"Each of the {rows[0]['cases'] if rows else 0} specimen defects in a category Mumei targets has a requirement and one contract "
           "(requires/ensures) that the buggy and the fixed function are both checked against. "
           "The right answer is: buggy version refuted, fixed version proven. "
           "Values are medians over runs, with the range in brackets. Arm tables score the fidelity-acceptance "
           "projection; committed result JSON keeps raw verifier outcomes separately.", "",
           render_table(rows), "",
           "Outcome taxonomy: false acceptance is a buggy body proven; false positive is a fixed body refuted; "
           "unsupported means the input, generated port/contract or verifier capability cannot represent the case; "
           "inconclusive means no evidence either way; environment failure means tool/transport failure; budget "
           "exhausted means the declared timeout was consumed. These categories are mutually exclusive per-variant "
           "outcomes, not proof grades; one shared LLM request failure can therefore produce two environment-failure "
           "outcomes.", ""]
    gated = [r for r in rows if r.get("fidelity_blocked")]
    if gated:
        out += ["Fidelity acceptance gate: " + "; ".join(
            f"{ARM_LABEL.get(r['arm'], r['arm'])} blocks {fmt(r, 'fidelity_blocked')} candidate variant(s) per run"
            for r in gated) + ". The committed rows keep the raw verifier proof outcome; only the report projection "
            "counts a blocked candidate as unsupported/inconclusive evidence rather than verification acceptance. "
            "Lint is variant-aware and records high-confidence meaning-loss evidence: silent repair, missing modeled "
            "operations, guard folding, self-calls and success-flag rewrites. It never overrides confirming replay; "
            "added or removed guard-count warnings also stay visible without blocking alone. Reference replay is the semantic acceptance check: a buggy candidate must "
            "still refute every supplied input beside the buggy reference, a fixed candidate must still hold every "
            "supplied input beside the fixed reference, and weak/vacuous generated contracts cannot support proof acceptance. "
            + " ".join(
                f"For {ARM_LABEL.get(r['arm'], r['arm'])}, raw verifier proofs before projection were buggy "
                f"{fmt(r, 'raw_buggy_proven')} and fixed {fmt(r, 'raw_fixed_proven')} per run, while projected acceptance leaves "
                f"fixed proven at {fmt(r, 'fixed_proven')} and unresolved/unsupported at {fmt(r, 'unsupported')}"
                for r in gated) + ".", ""]
        provenance = []
        for doc in results:
            meta = doc.get("fidelity_rescore")
            if not meta:
                continue
            verifier = meta.get("replay_verifier") or {}
            version = verifier.get("version") or "unknown verifier"
            commit = verifier.get("commit")
            identity = f"`{version}`" + (f" (`{commit[:7]}`)" if commit else " (commit unavailable)")
            provenance.append(f"{ARM_LABEL.get(doc['arm'], doc['arm'])} replayed at {meta.get('rescored_at')} with {identity}")
        if provenance:
            out += ["Fidelity rescore evidence: " + "; ".join(provenance) + ".", ""]
    out += [render_measurement_table(rows), "",
           "Verification time and budget are wall seconds and the declared per-attempt timeout aggregated over "
           "recorded outcome-determining verifier calls, including vacuity controls, fidelity replay calls and the per-call input/output "
           "glue inside `verify_text`. Certificate emission/rechecks, case-level orchestration and provider calls "
           "are outside that measurement. Older committed rows show the measured fraction of "
           "expected verifier calls, so partial `--only` refreshes cannot look fully instrumented. Model time/cost "
           "come only from provider usage metadata.", "",
           "[REPLAY.md](REPLAY.md) replays concrete inputs, the LLM witnesses and the LLM ports on the native "
           "code (`scripts/run_native_replay.py`). [REGRESSION.md](REGRESSION.md) reads the same results as a "
           "pull-request gate for changes under a pinned contract (`scripts/run_regression_gate.py`).", ""]
    failed = [r for r in rows if r["errors"]]
    if failed:
        out += ["Variant outcomes blocked by tool or transport failure are not counted as answers: " +
                ", ".join(f"{r['arm']} {fmt(r, 'errors')}" for r in failed) + ".", ""]
    out += ["The reference ports were written by hand with knowledge of the defects, so the first row shows "
            "that the contracts can express each requirement and how often the checker tells the two versions apart. "
            "It is not a detection result. The LLM rows are the comparison. LLM only and mumei + LLM see the "
            "product source file, the requirement, the modelling notes and the contract header, never the defect list "
            "or the reference ports. LLM only answers holds/violated itself; a \"holds\" is the model's "
            "opinion, not a proof. mumei + LLM asks the model only for the `.mm` body under the pinned header, "
            "and mumei decides.", "",
            "mumei + LLM contract removes the hand-written contract instead: the model gets the requirement, the "
            "modelling notes, the prelude and the atom signature, but no code and not the reference requires/ensures. "
            "Its one contract is put on both reference bodies, so a wrong answer here is a contract-writing error: "
            "a buggy body accepted means the contract is too weak to catch the defect, a fixed body rejected means "
            "it asks for more than the requirement does. The same vacuity control as for the reference applies.", "",
            "A buggy function whose LLM port mumei proves is a translation problem: the reference port of the "
            "same function under the same contract is refuted, so the LLM port does not keep the defect. "
            "mumei's verdict is only as faithful as the port it checks.", "",
            "A proof covers the model in the port, not native behaviour the model leaves out, such as "
            "fixed-width overflow, nil pointers or exceptions from library calls. Some LLM-only rejections "
            "of a fixed function point at exactly that kind of behaviour; their witnesses are listed below.", ""]
    ref = next((d for d in results if d["arm"] == "mumei"), None)
    if ref:
        run = ref["runs"][0]
        vac = [r["id"] for r in run if r.get("vacuity") != "ok"]
        out += [f"Vacuity control (fixed port re-checked with `ensures: false`, must fail): "
                f"{len(run) - len(vac)} / {len(run)} pass" + (f"; not passing: {', '.join(vac)}" if vac else "") + ".", ""]
        misses = [r for r in run if r["buggy"]["outcome"] != "refuted" or r["fixed"]["outcome"] != "proven"]
        if misses:
            out += ["Reference cases where mumei did not give the right answer:", ""]
            for r in misses:
                msg = (r["fixed"]["diagnostics"] or r["buggy"]["diagnostics"] or [{"message": ""}])[0]["message"]
                out.append(f"- `{r['id']}` ({r['language']}, `{r['function']}`): buggy {r['buggy']['outcome']}, "
                           f"fixed {r['fixed']['outcome']} — {msg.splitlines()[0][:160]}")
            out.append("")
        out += certificate_lines(ref)
    for d in results:
        if d["arm"] == "mumei-llm":
            out += llm_certificate_lines(d)
        if d["arm"] == "llm-contract":
            passes = [f"{sum(r.get('vacuity') == 'ok' for r in run)} / {len(run)}" for run in d["runs"]]
            out += [f"Vacuity control for {ARM_LABEL['llm-contract']} ({d['model']}), per run: {', '.join(passes)} pass. "
                    "A raw verifier proof under a weak or vacuous contract still indicates a contract-writing error, "
                    "but the fidelity gate keeps it out of benchmark acceptance as unsupported/inconclusive evidence.", ""]
    wrong = []
    for d in results:
        if d["arm"] == "mumei":
            continue
        counts: dict[tuple[str, str], int] = {}
        for run in d["runs"]:
            for r in run:
                for v, bad in (("buggy", "proven"), ("fixed", "refuted")):
                    if r[v]["outcome"] == bad:
                        counts[(r["id"], v)] = counts.get((r["id"], v), 0) + 1
        if counts:
            witnesses = {}
            for run in d["runs"]:
                for r in run:
                    reply = r["fixed"].get("reply")
                    w = reply.get("witness") if isinstance(reply, dict) and r["fixed"]["outcome"] == "refuted" else ""
                    if w and isinstance(w, str):
                        witnesses.setdefault(r["id"], " ".join(w.split())[:140])
            wrong.append(f"- {ARM_LABEL.get(d['arm'], d['arm'])}: " + ", ".join(
                f"`{i}` {'buggy accepted' if v == 'buggy' else 'fixed rejected'} ({n}/{len(d['runs'])})"
                for (i, v), n in sorted(counts.items())))
            wrong += [f"  - `{i}` fixed rejected, witness: {w}" for i, w in sorted(witnesses.items())]
            contracts, unchecked = {}, set()
            for run in d["runs"]:
                for r in run:
                    wrong_run = r["buggy"]["outcome"] == "proven" or r["fixed"]["outcome"] == "refuted"
                    if r.get("contract") and wrong_run and r["id"] not in contracts:
                        contracts[r["id"]] = " ".join(r["contract"]["ensures"].split())[:160]
                        if r.get("vacuity") != "ok":
                            unchecked.add(r["id"])
            wrong += [f"  - `{i}` model's ensures (from a wrong run): `{e}`"
                      + (" — vacuity control not passed in that run" if i in unchecked else "")
                      for i, e in sorted(contracts.items())]
    if wrong:
        out += ["## Raw verifier/model wrong answers by case (runs out of total, before fidelity projection)", ""] + wrong + [""]
    out += ["## By language (cases with both answers right)", "",
            "| Arm | Model | " + " | ".join(LANGUAGES) + " |", "|---|---|" + "---:|" * len(LANGUAGES)]
    for r in rows:
        cells = [f"{int(r['by_language'][l]['both'])} / {r['by_language'][l]['cases']}" if l in r["by_language"] else "—"
                 for l in LANGUAGES]
        out.append(f"| {ARM_LABEL.get(r['arm'], r['arm'])} | {r['model'] or '—'} | " + " | ".join(cells) + " |")
    out.append("")
    if stale:
        out += ["## Stale results", ""] + [f"- {s}" for s in stale] + [""]
    return "\n".join(out)


def render_readme_table(rows: list[dict]) -> str:
    lines = ["| Arm | Model | Both right | False acceptance | False positive | Cost |",
             "|---|---|---:|---:|---:|---:|"]
    for r in rows:
        cost = "—" if r["arm"] == "mumei" else f"${r['usage']['cost_usd']:.2f}"
        lines.append(f"| {ARM_LABEL.get(r['arm'], r['arm'])} | {r['model'] or '—'} | "
                     f"{fmt(r, 'both')} / {r['cases']} | {fmt(r, 'false_acceptance')} | "
                     f"{fmt(r, 'false_positive')} | {cost} |")
    return "\n".join(lines)


def render_readme_evidence(rows: list[dict]) -> str:
    dates = sorted({(r.get("recorded_at") or "")[:10] for r in rows if r.get("recorded_at")})
    parts = []
    if dates:
        parts.append("recorded " + (dates[0] if len(dates) == 1 else " and ".join(dates)))
    checked = [r for r in rows if r["arm"] != "llm"]
    verifiers = sorted({(v["version"], v["commit"][:7])
                        for r in checked if (v := r.get("verifier")) and v.get("version") and v.get("commit")})
    fully_identified = len(verifiers) == 1 and all(
        (v := r.get("verifier")) and v.get("version") == verifiers[0][0]
        and (v.get("commit") or "")[:7] == verifiers[0][1]
        for r in checked)
    if fully_identified:
        version, commit = verifiers[0]
        parts.append(f"verifier for mumei-checked rows `{version}` (`{commit}`)")
    elif verifiers or checked:
        parts.append("verifier provenance is mixed or incomplete across mumei-checked rows")
    return "; ".join(parts)


def render_readme_block(rows: list[dict]) -> str:
    evidence = render_readme_evidence(rows)
    lines = [README_START, ""]
    if evidence:
        lines += [f"Evidence snapshot: {evidence}.", ""]
    lines += [render_readme_table(rows), ""]
    gated = [r for r in rows if r.get("fidelity_blocked")]
    if gated:
        lines += ["Fidelity gate note: " + "; ".join(
            f"{ARM_LABEL.get(r['arm'], r['arm'])} excludes {fmt(r, 'fidelity_blocked')} raw verifier proof(s) per run "
            "from acceptance" for r in gated) + ". False acceptance and fixed-proven are post-gate projections; "
            "raw verifier outcomes, unresolved/unsupported rows and fixed-side impact are in [proofs/RESULTS.md](proofs/RESULTS.md).", ""]
    lines += ["The reference row uses hand-written ports, so it is a contract-expression check rather than a detection result. "
              "Full outcome taxonomy, per-language results and caveats: [proofs/RESULTS.md](proofs/RESULTS.md).", "", README_END]
    return "\n".join(lines)


def replace_block(text: str, block: str) -> str | None:
    if README_START not in text or README_END not in text:
        return None
    a, b = text.index(README_START), text.index(README_END) + len(README_END)
    return text[:a] + block + text[b:]


def certificate_lines(ref: dict) -> list[str]:
    proven = [r for r in ref["runs"][0] if r["fixed"]["outcome"] == "proven"]
    certs = [r["fixed"].get("certificate") or {} for r in proven]
    ok = sum(1 for c in certs if c.get("verify_cert") == "ok")
    trust = Counter(c.get("trust", "none") for c in certs)
    out = [f"Proof certificates: {ok} / {len(proven)} proven fixed ports have one, emitted with "
           "`mumei verify --proof-cert` and re-checked with `mumei verify-cert --strict`. Trust: "
           + ", ".join(f"{TRUST_LABEL.get(k, k)} {v}" for k, v in sorted(trust.items())) + ". "
           "`--check` compares each committed `fixed.proof.json` with its recorded hash and with the "
           "current `fixed.mm`.", ""]
    lean = [r["fixed"]["lean_dual_check"] for r in proven if r["fixed"].get("lean_dual_check")]
    if not lean:
        return out + ["Lean bridge: not run for this result (`--lean-bridge`).", ""]
    commit = ((ref.get("lean_bridge") or {}).get("commit") or "unknown")[:7]
    status = Counter(d["status"] for d in lean)
    bridge_outcomes = sum(status[status_name] for status_name in ("lean_verified", "failed", "partial_translation"))
    out += [f"Lean bridge dual check (mumei-lean `{commit}`): records one outcome per certified obligation. "
            "`partial_translation` means the bridge could not state the whole obligation in Lean, so nothing was "
            "checked; `stale`, `unsupported`, `timeout`, `no-certificate` and `not-checked` mean no current Lean "
            "check completed; a failed dual check does not change the Z3 result. "
            + ", ".join(f"{k} {v}" for k, v in sorted(status.items()))
            + f" of {len(lean)} recorded obligations ({bridge_outcomes} bridge outcomes returned).", ""]
    errors = Counter(d["error"] for d in lean if d.get("error"))
    if errors:
        out += ["Most common first Lean errors:", ""]
        out += [f"- {n} × `{e[:120]}`" for e, n in errors.most_common(5)] + [""]
    return out


def llm_certificate_lines(doc: dict) -> list[str]:
    per_run, trust = [], Counter()
    for run in doc["runs"]:
        certs = [r["fixed"].get("certificate") or {} for r in run if r["fixed"]["outcome"] == "proven"]
        per_run.append(f"{sum(c.get('verify_cert') == 'ok' for c in certs)} / {len(certs)}")
        trust.update(c.get("trust", "none") for c in certs)
    return [f"Proof certificates for {ARM_LABEL['mumei-llm']} ({doc['model']}), per run: {', '.join(per_run)} proven "
            "fixed ports have one, emitted and re-checked like the reference ones and committed as "
            f"`mumei-llm/<model>-run<n>.{CERT_FILE}` next to the case. Trust: "
            + ", ".join(f"{TRUST_LABEL.get(k, k)} {v}" for k, v in sorted(trust.items())) + ".", ""]


def render_all(cases: list[dict], write: bool) -> list[str]:
    """Render RESULTS.md and the README block; with write=False return the files that are out of date."""
    results = load_results()
    if not results:
        return []
    rows = arm_rows(results)
    md = render_markdown(rows, results, stale_records(cases, results))
    readme = README.read_text()
    new_readme = replace_block(readme, render_readme_block(rows))
    outdated = []
    if not RESULTS_MD.is_file() or RESULTS_MD.read_text() != md:
        outdated.append(str(RESULTS_MD.relative_to(REPO_ROOT)))
        if write:
            RESULTS_MD.write_text(md)
    if new_readme is not None and new_readme != readme:
        outdated.append("README.md")
        if write:
            README.write_text(new_readme)
    return outdated


def merge_runs(arm: str, model: str | None, runs: list[list[dict]], verifier: dict | None = None) -> list[list[dict]]:
    """Replace the given cases in the committed result, so that --only reruns a few cases."""
    old = check_mergeable(arm, model, len(runs), verifier)
    merged = []
    for o, n in zip(old["runs"], runs):
        new = {r["id"]: r for r in n}
        merged.append([new.pop(r["id"], r) for r in o] + list(new.values()))
    return merged


def check_mergeable(arm: str, model: str | None, run_count: int, verifier: dict | None = None) -> dict:
    """The committed result an --only rerun merges into; exits before any case runs or writes a certificate."""
    path = result_path(arm, model)
    if not path.is_file():
        raise SystemExit(f"{path.relative_to(REPO_ROOT)} does not exist yet; run every case before using --only")
    old = json.loads(path.read_text())
    if len(old["runs"]) != run_count or (arm != "mumei" and old.get("prompt_hash") != prompt_hash(arm)):
        raise SystemExit(f"{path.relative_to(REPO_ROOT)} has another prompt or run count; rerun without --only")
    if verifier is not None and "verifier" in old and old["verifier"] != verifier:
        raise SystemExit(f"{path.relative_to(REPO_ROOT)} was recorded with another mumei build; rerun without --only")
    return old


def recording_bin(arm: str, model: str | None, args) -> str | None:
    """The binary to record as verifier; none when --only merges into a result that predates the record."""
    if args.only and "verifier" not in json.loads(result_path(arm, model).read_text()):
        return None
    return args.mumei_bin


def verifier_identity(mumei_bin: str) -> dict:
    """The mumei version, plus the source commit when the binary was built in a git checkout.

    The commit is only recorded for a binary under the checkout's `target/` directory that is
    newer than the last time HEAD moved; otherwise HEAD need not be what the binary was built from.
    """
    try:
        version = subprocess.run([mumei_bin, "--version"], capture_output=True, text=True,
                                 timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        version = ""
    unknown = {"version": version or None, "commit": None, "dirty": None}
    resolved = shutil.which(mumei_bin)
    if resolved is None:
        return unknown
    binary = Path(resolved).resolve()

    def git(*args: str) -> str | None:
        res = subprocess.run(["git", "-C", str(binary.parent), *args], capture_output=True, text=True)
        return res.stdout.strip() if res.returncode == 0 else None

    top = git("rev-parse", "--show-toplevel")
    if not top or not binary.is_relative_to(Path(top).resolve() / "target"):
        return unknown
    moved = git("log", "-g", "-1", "--format=%ct", "HEAD") or git("log", "-1", "--format=%ct", "HEAD")
    if not moved or binary.stat().st_mtime < int(moved):
        return unknown
    commit = git("rev-parse", "HEAD")
    dirty = git("status", "--porcelain", "--untracked-files=no")
    return {"version": version or None, "commit": commit, "dirty": bool(dirty) if commit else None}


def write_result(arm: str, model: str | None, runs: list[list[dict]], mumei_bin: str | None = None,
                 lean_bridge: dict | None = None) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    doc = {"arm": arm, "model": model, "prompt_hash": None if arm == "mumei" else prompt_hash(arm),
           "recorded_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()}
    if mumei_bin and arm != "llm":
        doc["verifier"] = verifier_identity(mumei_bin)
    if lean_bridge:
        doc["lean_bridge"] = lean_bridge
    doc["runs"] = [sorted(run, key=lambda r: r["id"]) for run in runs]
    path = result_path(arm, model)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return path


def apply_contract_fidelity_gate(out: dict) -> dict:
    """Keep proofs under weak or vacuous generated contracts out of acceptance.

    The raw verifier outcomes remain on each variant as ``verifier_outcome``.
    This does not call a lint warning or a vacuity control a formal refutation;
    it marks the affected benchmark evidence unsupported/inconclusive instead.
    """
    contract = out.get("contract")
    if not contract:
        return out
    linted = fidelity.lint_contract(contract["requires"], contract["ensures"])
    out["contract_lint_findings"] = linted
    reasons = []
    if linted:
        reasons.append("lint:" + ",".join(sorted({finding["kind"] for finding in linted})))
    if out.get("vacuity") == "vacuous":
        reasons.append("vacuity:vacuous")
    if not reasons:
        return out
    for variant in VARIANTS:
        result = out[variant]
        if result.get("outcome") != "proven":
            continue
        gate = {"schema": "mumei-demo.contract-fidelity-gate/v1", "decision": "blocked",
                "source": "generated_contract", "lint_findings": linted, "vacuity": out.get("vacuity")}
        result["fidelity_gate"] = gate
    return out


def current_replay_input_hash(case: dict) -> str | None:
    try:
        _, input_hash = fidelity.replay_inputs(case)
        return input_hash
    except (OSError, ValueError, KeyError):
        return None


def fidelity_gate_stale(case: dict, gate: dict) -> bool:
    """Whether a stored port-fidelity gate no longer matches its replay fixture."""
    expected = current_replay_input_hash(case)
    return expected is not None and gate.get("semantic_replay", {}).get("input_hash") != expected


def rescore_port_fidelity(cases: list[dict], mumei_bin: str, timeout: int) -> dict:
    """Apply the fidelity acceptance gate to committed mumei-llm records.

    This annotation uses the recorded model body and preserves the raw
    verifier outcome in each blocked row; it does not call an LLM or rewrite a
    formal proof verdict. The replay verifier identity is recorded separately
    because it is diagnostic fidelity evidence, not the original bench verdict.
    """
    by_id = {case["id"]: case for case in cases}
    updated = []
    blocked = 0
    gated = 0
    for path in sorted(RESULTS_DIR.glob("mumei-llm-*.json")):
        doc = json.loads(path.read_text())
        changed = False
        for run in doc.get("runs", []):
            for record in run:
                case = by_id.get(record.get("id"))
                if case is None:
                    continue
                for variant in VARIANTS:
                    result = record.get(variant)
                    if not isinstance(result, dict) or result.get("outcome") != "proven":
                        continue
                    existing_gate = result.get("fidelity_gate")
                    if existing_gate and not fidelity_gate_stale(case, existing_gate):
                        continue
                    body = result.get("body")
                    if not isinstance(body, str):
                        continue
                    new_result = apply_port_fidelity_gate(case, body, result, mumei_bin, timeout, variant)
                    if new_result is not result:
                        record[variant] = new_result
                        changed = True
                        gated += 1
                        blocked += new_result.get("fidelity_gate", {}).get("decision") == "blocked"
        if changed:
            doc["fidelity_rescore"] = {
                "schema": "mumei-demo.port-fidelity-gate/v2",
                "rescored_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
                "replay_verifier": verifier_identity(mumei_bin),
            }
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
            updated.append(path.relative_to(REPO_ROOT).as_posix())
    return {"updated": updated, "gated": gated, "blocked": blocked}


def fidelity_problems(results: list[dict], cases: list[dict] | None = None) -> list[str]:
    """Offline validation that raw verifier proofs are not promoted past fidelity gates."""
    problems = []
    cases_by_id = {case["id"]: case for case in cases or []}

    def raw_outcome(result: dict) -> str | None:
        return result.get("verifier_outcome", result.get("outcome"))

    for doc in results:
        label = f"{doc['arm']} ({doc.get('model')})"
        for run_index, run in enumerate(doc.get("runs", []), 1):
            if doc["arm"] == "mumei-llm":
                false_acceptance = score(run)["false_acceptance"]
                if false_acceptance > 2:
                    problems.append(f"{label} run {run_index}: false acceptance {false_acceptance} exceeds budget 2")
                for record in run:
                    for variant in VARIANTS:
                        result = record.get(variant, {})
                        if raw_outcome(result) != "proven":
                            continue
                        gate = result.get("fidelity_gate")
                        prefix = f"{label} run {run_index}: {record.get('id')} {variant} raw verifier proof"
                        if not gate:
                            problems.append(f"{prefix} has no fidelity gate")
                            continue
                        if gate.get("variant") != variant:
                            problems.append(f"{prefix} has a gate for the wrong variant")
                        case = cases_by_id.get(record.get("id"))
                        if case is not None and fidelity_gate_stale(case, gate):
                            problems.append(f"{prefix} has a fidelity gate stale against replay inputs")
                        if gate.get("decision") == "blocked":
                            projected = project_fidelity_result(result)
                            if (projected.get("outcome") != "inconclusive"
                                    or projected.get("failure_kind") != fidelity_projection_failure_kind(gate)):
                                problems.append(f"{prefix} is blocked without the explicit unsupported/inconclusive projection")
                        if gate.get("decision") == "accepted":
                            semantic = gate.get("semantic_replay", {})
                            confirming = "still_refutes" if variant == "buggy" else "still_holds"
                            blocking = gate.get("blocking_lint_findings")
                            if blocking is None:
                                blocking = fidelity.blocking_lint_findings(gate.get("lint_findings") or [])
                            if semantic.get("outcome") != confirming:
                                problems.append(f"{prefix} is accepted without confirming semantic replay")
            if doc["arm"] == "llm-contract":
                for record in run:
                    contract = record.get("contract")
                    if not contract:
                        continue
                    linted = fidelity.lint_contract(contract["requires"], contract["ensures"])
                    weak_or_vacuous = bool(linted) or record.get("vacuity") == "vacuous"
                    if not weak_or_vacuous:
                        continue
                    for variant in VARIANTS:
                        result = record.get(variant, {})
                        if raw_outcome(result) != "proven":
                            continue
                        gate = result.get("fidelity_gate", {})
                        projected = project_fidelity_result(result)
                        correctly_blocked = (gate.get("source") == "generated_contract" and gate.get("decision") == "blocked"
                                             and projected.get("outcome") == "inconclusive"
                                             and projected.get("failure_kind") == "unsupported")
                        if not correctly_blocked:
                            problems.append(
                                f"{label} run {run_index}: {record.get('id')} {variant} proof under weak/vacuous contract "
                                "is not fidelity-gated"
                            )
    return problems


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--arm", action="append", choices=ARMS, help="arm to run (repeatable)")
    p.add_argument("--only", action="append", help="limit to these defect ids")
    p.add_argument("--runs", type=int, default=1, help="runs per LLM arm (seed = run number)")
    p.add_argument("--jobs", type=int, default=4, help="cases run in parallel")
    p.add_argument("--timeout", type=int, default=120, help="per-verification timeout in seconds")
    p.add_argument("--mumei-bin", default=os.environ.get("MUMEI_BIN") or shutil.which("mumei"),
                   help="mumei binary (default: $MUMEI_BIN, then mumei on PATH)")
    p.add_argument("--lean-bridge", metavar="DIR",
                   help="mumei-lean checkout: Lean-check each certified reference fixed port (bridge --dual-check)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate cases and committed results offline")
    mode.add_argument("--render-only", action="store_true", help="re-render RESULTS.md and the README block")
    mode.add_argument("--fidelity-rescore", action="store_true",
                      help="apply the port fidelity acceptance gate to committed mumei-llm results")
    return p


def main(argv: list[str], provider=None) -> int:
    args = build_parser().parse_args(argv)
    cases, errors = load_cases()
    if args.check:
        results = load_results()
        problems = errors + stale_records(cases, results) + certificate_problems(cases, results) + fidelity_problems(results, cases)
        ref = next((d for d in results if d["arm"] == "mumei"), None)
        if ref is None:
            problems.append("no reference result (proofs/results/mumei.json); run --arm mumei")
        elif not (ref.get("verifier") or {}).get("commit"):
            problems.append("the reference result does not record the mumei commit it was verified with; "
                            "rerun --arm mumei with a mumei built from a git checkout")
        else:
            problems += [f"{result_path(d['arm'], d.get('model')).relative_to(REPO_ROOT)} was verified with another "
                         f"mumei build than the reference result; rerun it with the reference build"
                         for d in results if d["arm"] in ("llm-contract", "mumei-llm") and d.get("verifier") != ref["verifier"]]
        problems += [f"{f} is out of date; run --render-only" for f in render_all(cases, write=False)]
        for msg in problems:
            print(f"error: {msg}", file=sys.stderr)
        print(f"{len(cases)} cases, {len(problems)} problem(s)")
        return 1 if problems else 0
    if errors:
        for msg in errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1
    if args.render_only:
        render_all(cases, write=True)
        return 0
    if args.fidelity_rescore:
        if not args.mumei_bin:
            raise SystemExit("mumei binary not found; pass --mumei-bin or set MUMEI_BIN")
        stale = stale_records(cases, load_results())
        if stale:
            raise SystemExit("committed results are stale; refresh or restore them before fidelity rescoring: " + "; ".join(stale))
        binary = shutil.which(args.mumei_bin)
        if binary is None:
            raise SystemExit(f"mumei binary is not executable: {args.mumei_bin}")
        summary = rescore_port_fidelity(cases, str(Path(binary).resolve()), args.timeout)
        render_all(cases, write=True)
        print(f"fidelity gate: {summary['blocked']} blocked of {summary['gated']} newly gated raw proven ports "
              f"across {len(summary['updated'])} result file(s)")
        return 0
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    for arm in args.arm or ["mumei"]:
        if arm != "llm" and not args.mumei_bin:
            raise SystemExit("mumei binary not found; pass --mumei-bin or set MUMEI_BIN")
        if arm == "mumei":
            if args.only and result_path(arm, None).is_file():
                old = json.loads(result_path(arm, None).read_text())
                if old.get("verifier") != verifier_identity(args.mumei_bin):
                    raise SystemExit(f"{result_path(arm, None).relative_to(REPO_ROOT)} was recorded with another "
                                     "mumei build; rerun every case instead of using --only")
                if args.lean_bridge and old.get("lean_bridge") != git_identity(args.lean_bridge):
                    raise SystemExit(f"{result_path(arm, None).relative_to(REPO_ROOT)} was checked with another "
                                     "mumei-lean commit; rerun every case with --lean-bridge instead of using --only")
            if args.only:
                check_mergeable(arm, None, 1, verifier_identity(args.mumei_bin))
            if args.lean_bridge and not lake_on_path():
                raise SystemExit("--lean-bridge needs `lake` on PATH (elan's ~/.elan/bin)")
            with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
                run = list(pool.map(lambda c: run_mumei_case(c, args.mumei_bin, args.timeout), cases))
            lean = None
            if args.lean_bridge:
                lean = git_identity(args.lean_bridge)
                by_id = {c["id"]: c for c in cases}
                for r in run:
                    if r["fixed"].get("certificate", {}).get("status") == "recorded":
                        cert = (REPO_ROOT / by_id[r["id"]]["dir"] / CERT_FILE).read_text()
                        r["fixed"]["lean_dual_check"] = lean_dual_check(
                            args.lean_bridge, by_id[r["id"]], cert, args.timeout * 5)
            elif args.only and result_path(arm, None).is_file():
                lean = json.loads(result_path(arm, None).read_text()).get("lean_bridge")
            runs = [run]
            merged = merge_runs(arm, None, runs, verifier_identity(args.mumei_bin)) if args.only else runs
            path = write_result(arm, None, merged, recording_bin(arm, None, args), lean)
        else:
            prov = provider or llm_only.provider_from_env(timeout=600)
            prov.retries = max(getattr(prov, "retries", 0), RATE_LIMIT_RETRIES)
            verifier = verifier_identity(args.mumei_bin) if arm != "llm" else None
            if args.only:
                check_mergeable(arm, prov.model, args.runs, verifier)
            runs = []
            for seed in range(args.runs):
                with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
                    if arm == "llm-contract":
                        runs.append(list(pool.map(
                            lambda c: run_contract_case(c, prov, seed, args.mumei_bin, args.timeout), cases)))
                    else:
                        runs.append(list(pool.map(
                            lambda c: run_llm_case(c, prov, arm, seed, args.mumei_bin, args.timeout), cases)))
            merged = merge_runs(arm, prov.model, runs, verifier) if args.only else runs
            path = write_result(arm, prov.model, merged, recording_bin(arm, prov.model, args))
        if arm != "mumei" and any(score(run)["errors"] for run in json.loads(path.read_text())["runs"]):
            print(f"warning: {arm} has requests that failed; rerun before publishing", file=sys.stderr)
        print(f"{arm}: {score(json.loads(path.read_text())['runs'][0])} -> {path.relative_to(REPO_ROOT)}")
    render_all(load_cases()[0], write=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
