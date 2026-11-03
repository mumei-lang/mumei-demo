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
             verified; a body that declares an atom is rejected.
  llm-contract
             the model writes the contract instead: it gets the requirement,
             the modelling notes, the prelude and the atom signature, but no
             code and not the reference requires/ensures. Its one contract is
             put on both reference bodies, which mumei verifies, with the
             same vacuity control as the mumei arm. This measures the step
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
REFUTATION = re.compile(r"^Verification Error: (Postcondition|Call to \S+: precondition|Potential |"
                        r"(Loop )?[Ii]nvariant|[Tt]ermination|[Dd]ecreases)")

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
        templates = [inspect.getsource(f) for f in (contract_prompt, contract_header, signature)]
        return sha256(json.dumps([PROMPT_VERSION, CONTRACT_SYSTEM, templates], sort_keys=True))[:16]
    templates = [inspect.getsource(f) for f in (llm_prompt, port_prompt, assemble)]
    return sha256(json.dumps([PROMPT_VERSION, LLM_SYSTEM, PORT_SYSTEM, templates], sort_keys=True))[:16]


def split_port(text: str, atom: str) -> tuple[str, str, str] | None:
    """(prelude, header, body) of a port whose last atom is `atom`; header ends before `body:`."""
    m = re.search(rf"^(?:trusted\s+)?atom\s+{re.escape(atom)}\s*\(", text, re.M)
    if not m:
        return None
    b = text.find("body:", m.start())
    if b < 0:
        return None
    return text[:m.start()], text[m.start():b], text[b:]


def header_ensures(header: str) -> str | None:
    m = re.search(r"^\s*ensures:\s*(.*);\s*$", header, re.M)
    return m.group(1) if m else None


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


def classify(doc: dict | None, returncode: int) -> dict:
    """proven / refuted / inconclusive from `mumei verify --json` output."""
    if doc is None:
        return {"outcome": "inconclusive", "status": f"no-json (exit {returncode})", "diagnostics": []}
    status = str(doc.get("status", ""))
    diags = [{"atom": d.get("atom", ""), "code": d.get("code", ""),
              "message": str(d.get("message", ""))[:300]}
             for d in doc.get("diagnostics", []) if d.get("severity", "error") == "error"]
    if status == "success" and returncode == 0:
        outcome = "proven"
    elif status == "failed" and int(doc.get("unverifiable", 0) or 0) == 0 and int(doc.get("infra_errors", 0) or 0) == 0:
        # Only a verification failure refutes; an unknown function or a type error says nothing about the code.
        outcome = "refuted" if diags and all(REFUTATION.search(d["message"]) for d in diags) else "inconclusive"
    else:
        outcome = "inconclusive"
    return {"outcome": outcome, "status": status, "diagnostics": diags}


def verify_text(mumei_bin: str, text: str, timeout: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="contract-bench-") as tmp:
        path = Path(tmp) / "case.mm"
        path.write_text(text)
        try:
            proc = subprocess.run([mumei_bin, "verify", "--json", path.name], cwd=tmp,
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"outcome": "inconclusive", "status": "timeout", "diagnostics": []}
        try:
            doc = json.loads(proc.stdout[proc.stdout.index("{"):]) if "{" in proc.stdout else None
        except json.JSONDecodeError:
            doc = None
        return classify(doc, proc.returncode)


def vacuity_text(case: dict, header: str | None = None) -> str:
    header = case["header"] if header is None else header
    ens = header_ensures(header)
    header = header.replace(f"ensures: {ens};", "ensures: false;", 1)
    return case["prelude"] + header + split_port(case["ports"]["fixed"], case["atom"])[2]


def vacuity(case: dict, out: dict, mumei_bin: str, timeout: int, header: str | None = None) -> str:
    control = verify_text(mumei_bin, vacuity_text(case, header), timeout)
    # mumei may reject `ensures: false` up front as contradicting `requires`. That alone would also pass an
    # unsatisfiable `requires`, so it only counts when the buggy port was refuted, i.e. some input meets `requires`.
    contradiction = control["status"] == "failed" and control["diagnostics"] and all(
        "Spec contradiction" in d["message"] or REFUTATION.search(d["message"]) for d in control["diagnostics"])
    rejected = control["outcome"] == "refuted" or (contradiction and out["buggy"]["outcome"] == "refuted")
    return "ok" if rejected else ("vacuous" if control["outcome"] == "proven" else "inconclusive")


def run_mumei_case(case: dict, mumei_bin: str, timeout: int) -> dict:
    out = {k: case[k] for k in ("id", "language", "specimen", "category", "function", "case_hash", "source_hash")}
    for v in VARIANTS:
        out[v] = verify_text(mumei_bin, case["ports"][v], timeout)
    out["vacuity"] = vacuity(case, out, mumei_bin, timeout)
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


def contract_prompt(case: dict) -> list[dict]:
    prelude = case["prelude"].strip() or "(none)"
    user = (f"Language of the original code: {case['language']}\nFunction: {case['function']}\n"
            f"Requirement: {case['requirement']}\nModelling notes: {case['notes'] or '(none)'}\n\n"
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
        out.update({v: {"outcome": "inconclusive", "status": str(e)} for v in VARIANTS})
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
    out["vacuity"] = vacuity(case, out, mumei_bin, timeout, header)
    return out


def parse_json_reply(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n|\n?```$", "", text)
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None
    return doc if isinstance(doc, dict) else None


def assemble(case: dict, body: str) -> str:
    return case["prelude"] + case["header"] + "body: {\n" + body.rstrip() + "\n    }\n"


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
            out[v] = {**result, "body": body, "usage": usage}
    return out


def score(records: list[dict]) -> dict:
    s = {"cases": len(records), "buggy_refuted": 0, "fixed_proven": 0, "both": 0,
         "wrong_accept": 0, "wrong_reject": 0, "inconclusive": 0, "errors": 0, "vacuous": 0}
    for r in records:
        b, f = r["buggy"]["outcome"], r["fixed"]["outcome"]
        s["buggy_refuted"] += b == "refuted"
        s["fixed_proven"] += f == "proven"
        s["both"] += b == "refuted" and f == "proven"
        s["wrong_accept"] += b == "proven"
        s["wrong_reject"] += f == "refuted"
        for v in VARIANTS:
            if r[v]["outcome"] == "inconclusive":
                s["errors" if str(r[v].get("status", "")).startswith(TRANSPORT_ERROR) else "inconclusive"] += 1
        s["vacuous"] += r.get("vacuity") == "vacuous"
    return s


def usage_total(records: list[dict]) -> dict:
    cost, seconds, calls, unknown = 0.0, 0.0, 0, 0
    for r in records:
        for u in [r[v].get("usage") for v in VARIANTS] + [r.get("usage")]:
            if not u:
                continue
            calls += 1
            seconds += u.get("seconds") or 0
            if u.get("cost_usd") is None:
                unknown += 1
            else:
                cost += u["cost_usd"]
    return {"calls": calls, "cost_usd": round(cost, 4), "model_seconds": round(seconds, 1), "cost_unknown_calls": unknown}


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
        row = {"arm": doc["arm"], "model": doc.get("model"), "runs": len(scores)}
        for k in scores[0]:
            vals = [s[k] for s in scores]
            row[k] = median(vals)
            row[k + "_range"] = (min(vals), max(vals))
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
    lines = ["| Arm | Model | Runs | Buggy refuted | Fixed proven | Both right | Buggy accepted | Fixed rejected | Inconclusive | Cost |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        cost = "—" if r["arm"] == "mumei" else f"${r['usage']['cost_usd']:.2f}"
        lines.append(f"| {ARM_LABEL.get(r['arm'], r['arm'])} | {r['model'] or '—'} | {r['runs']} | "
                     f"{fmt(r, 'buggy_refuted')} / {r['cases']} | {fmt(r, 'fixed_proven')} / {r['cases']} | "
                     f"{fmt(r, 'both')} | {fmt(r, 'wrong_accept')} | {fmt(r, 'wrong_reject')} | {fmt(r, 'inconclusive')} | {cost} |")
    return "\n".join(lines)


def render_markdown(rows: list[dict], results: list[dict], stale: list[str]) -> str:
    out = ["# Contract benchmark results", "",
           "<!-- Generated by scripts/run_contract_bench.py; do not edit by hand. -->", "",
           f"Each of the {rows[0]['cases'] if rows else 0} specimen defects in a category Mumei targets has a requirement and one contract "
           "(requires/ensures) that the buggy and the fixed function are both checked against. "
           "The right answer is: buggy version refuted, fixed version proven. "
           "Values are medians over runs, with the range in brackets.", "",
           render_table(rows), ""]
    failed = [r for r in rows if r["errors"]]
    if failed:
        out += ["Requests that failed (rate limits, timeouts) are not counted as answers: " +
                ", ".join(f"{r['arm']} {fmt(r, 'errors')}" for r in failed) + ".", ""]
    out += ["The reference ports were written by hand with knowledge of the defects, so the first row shows "
            "that the contracts can express each requirement and how often the checker tells the two versions apart. "
            "It is not a detection result. The LLM rows are the comparison. Both LLM arms see the product "
            "source file, the requirement, the modelling notes and the contract header, never the defect list "
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
            contracts = {}
            for run in d["runs"]:
                for r in run:
                    if (r["id"], "buggy") in counts or (r["id"], "fixed") in counts:
                        if r.get("contract"):
                            contracts.setdefault(r["id"], " ".join(r["contract"]["ensures"].split())[:160])
            wrong += [f"  - `{i}` model's ensures: `{e}`" for i, e in sorted(contracts.items())]
    if wrong:
        out += ["## Wrong answers by case (runs out of total)", ""] + wrong + [""]
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


def render_readme_block(rows: list[dict]) -> str:
    return "\n".join([README_START, "", render_table(rows), "",
                      "Details, per-language results and caveats: [proofs/RESULTS.md](proofs/RESULTS.md).", "", README_END])


def replace_block(text: str, block: str) -> str | None:
    if README_START not in text or README_END not in text:
        return None
    a, b = text.index(README_START), text.index(README_END) + len(README_END)
    return text[:a] + block + text[b:]


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
    path = result_path(arm, model)
    if not path.is_file():
        raise SystemExit(f"{path.relative_to(REPO_ROOT)} does not exist yet; run every case before using --only")
    old = json.loads(path.read_text())
    if len(old["runs"]) != len(runs) or (arm != "mumei" and old.get("prompt_hash") != prompt_hash(arm)):
        raise SystemExit(f"{path.relative_to(REPO_ROOT)} has another prompt or run count; rerun without --only")
    if verifier is not None and "verifier" in old and old["verifier"] != verifier:
        raise SystemExit(f"{path.relative_to(REPO_ROOT)} was recorded with another mumei build; rerun without --only")
    merged = []
    for o, n in zip(old["runs"], runs):
        new = {r["id"]: r for r in n}
        merged.append([new.pop(r["id"], r) for r in o] + list(new.values()))
    return merged


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


def write_result(arm: str, model: str | None, runs: list[list[dict]], mumei_bin: str | None = None) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    doc = {"arm": arm, "model": model, "prompt_hash": None if arm == "mumei" else prompt_hash(arm),
           "recorded_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()}
    if mumei_bin and arm != "llm":
        doc["verifier"] = verifier_identity(mumei_bin)
    doc["runs"] = [sorted(run, key=lambda r: r["id"]) for run in runs]
    path = result_path(arm, model)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--arm", action="append", choices=ARMS, help="arm to run (repeatable)")
    p.add_argument("--only", action="append", help="limit to these defect ids")
    p.add_argument("--runs", type=int, default=1, help="runs per LLM arm (seed = run number)")
    p.add_argument("--jobs", type=int, default=4, help="cases run in parallel")
    p.add_argument("--timeout", type=int, default=120, help="per-verification timeout in seconds")
    p.add_argument("--mumei-bin", default=os.environ.get("MUMEI_BIN") or shutil.which("mumei"),
                   help="mumei binary (default: $MUMEI_BIN, then mumei on PATH)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate cases and committed results offline")
    mode.add_argument("--render-only", action="store_true", help="re-render RESULTS.md and the README block")
    return p


def main(argv: list[str], provider=None) -> int:
    args = build_parser().parse_args(argv)
    cases, errors = load_cases()
    if args.check:
        results = load_results()
        problems = errors + stale_records(cases, results)
        ref = next((d for d in results if d["arm"] == "mumei"), None)
        if ref is None:
            problems.append("no reference result (proofs/results/mumei.json); run --arm mumei")
        elif not (ref.get("verifier") or {}).get("commit"):
            problems.append("the reference result does not record the mumei commit it was verified with; "
                            "rerun --arm mumei with a mumei built from a git checkout")
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
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    for arm in args.arm or ["mumei"]:
        if arm != "llm" and not args.mumei_bin:
            raise SystemExit("mumei binary not found; pass --mumei-bin or set MUMEI_BIN")
        if arm == "mumei":
            with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
                run = list(pool.map(lambda c: run_mumei_case(c, args.mumei_bin, args.timeout), cases))
            runs = [run]
            merged = merge_runs(arm, None, runs, verifier_identity(args.mumei_bin)) if args.only else runs
            path = write_result(arm, None, merged, recording_bin(arm, None, args))
        else:
            prov = provider or llm_only.provider_from_env(timeout=600)
            prov.retries = max(getattr(prov, "retries", 0), RATE_LIMIT_RETRIES)
            runs = []
            for seed in range(args.runs):
                with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
                    if arm == "llm-contract":
                        runs.append(list(pool.map(
                            lambda c: run_contract_case(c, prov, seed, args.mumei_bin, args.timeout), cases)))
                    else:
                        runs.append(list(pool.map(
                            lambda c: run_llm_case(c, prov, arm, seed, args.mumei_bin, args.timeout), cases)))
            verifier = verifier_identity(args.mumei_bin) if arm != "llm" else None
            merged = merge_runs(arm, prov.model, runs, verifier) if args.only else runs
            path = write_result(arm, prov.model, merged, recording_bin(arm, prov.model, args))
        if arm != "mumei" and any(score(run)["errors"] for run in json.loads(path.read_text())["runs"]):
            print(f"warning: {arm} has requests that failed; rerun before publishing", file=sys.stderr)
        print(f"{arm}: {score(json.loads(path.read_text())['runs'][0])} -> {path.relative_to(REPO_ROOT)}")
    render_all(load_cases()[0], write=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
