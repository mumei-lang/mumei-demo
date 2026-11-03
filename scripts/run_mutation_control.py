#!/usr/bin/env python3
"""Mutation control for the contract benchmark: does each contract reject small changes to the fixed port?

The contract benchmark checks one planted defect per case. A contract can
refute that one defect and still accept many other wrong bodies. This script
makes first-order mutants of every fixed reference port in proofs/ and
verifies each one under the unchanged contract:

  relational   <  <=  >  >=  ==  !=   (each swapped with its neighbour)
  logical      &&  ||
  arithmetic   +  -
  constant     an integer literal n becomes n + 1

Only the atom body is mutated; the prelude, the contract and the loop
`invariant:`/`decreases:` annotations stay fixed (changing an annotation only
breaks the proof, not the code).
Mutants whose text equals another mutant, or the original, are dropped.
A mutant is killed when mumei refutes it, survives when mumei proves it, and
is invalid when it does not verify either way (type errors, timeouts). The
mutation score is killed / (killed + survived). A survivor is either a gap in
the contract or an equivalent mutant (same behaviour on every input the
contract allows); MUTATION.md lists them for review.

`--check` re-derives the mutants from the committed ports offline (no
Mumei) and fails when the recorded result or MUTATION.md is out of date.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_contract_bench as cb  # noqa: E402

RESULT = cb.PROOFS_ROOT / "mutation.json"
REPORT = cb.PROOFS_ROOT / "MUTATION.md"

SWAPS = {"<": "<=", "<=": "<", ">": ">=", ">=": ">", "==": "!=", "!=": "==",
         "&&": "||", "||": "&&", "+": "-", "-": "+"}
OPERATOR = {"<": "relational", "<=": "relational", ">": "relational", ">=": "relational",
            "==": "relational", "!=": "relational", "&&": "logical", "||": "logical",
            "+": "arithmetic", "-": "arithmetic"}
ANNOTATION = re.compile(r"(?m)^[ \t]*(invariant|decreases)\s*:[^\n]*")
TOKEN = re.compile(r"//[^\n]*|=>|->|<=|>=|==|!=|&&|\|\||[<>+\-]|\b\d+\b")
OUTCOME = {"refuted": "killed", "proven": "survived"}


def mutants(body: str) -> list[dict]:
    """First-order mutants of a body, in source order, without duplicates or no-ops."""
    out, seen = [], {body}
    proof_only = [a.span() for a in ANNOTATION.finditer(body)]
    for m in TOKEN.finditer(body):
        tok = m.group(0)
        if tok.startswith("//") or tok in ("=>", "->") or any(lo <= m.start() < hi for lo, hi in proof_only):
            continue
        if tok.isdigit():
            op, new = "constant", str(int(tok) + 1)
        else:
            op, new = OPERATOR[tok], SWAPS[tok]
        text = body[:m.start()] + new + body[m.end():]
        if text in seen:
            continue
        seen.add(text)
        out.append({"op": op, "at": m.start(), "from": tok, "to": new})
    return out


def apply(body: str, mutant: dict) -> str:
    at = mutant["at"]
    assert body[at:at + len(mutant["from"])] == mutant["from"]
    return body[:at] + mutant["to"] + body[at + len(mutant["from"]):]


def split_fixed(case: dict) -> tuple[str, str]:
    prelude, header, body = cb.split_port(case["ports"]["fixed"], case["atom"])
    return prelude + header, body


def context(body: str, mutant: dict, width: int = 50) -> str:
    """The mutated line around the change, trimmed, for the report."""
    text = apply(body, mutant)
    at, stop = mutant["at"], mutant["at"] + len(mutant["to"])
    line_start = text.rfind("\n", 0, at) + 1
    line_end = text.find("\n", stop)
    line_end = len(text) if line_end < 0 else line_end
    lo, hi = max(line_start, at - width), min(line_end, stop + width)
    snippet = " ".join(text[lo:hi].split())
    return ("… " if lo > line_start else "") + snippet + (" …" if hi < line_end else "")


def run_case(case: dict, mumei_bin: str, timeout: int) -> dict:
    head, body = split_fixed(case)
    rows = []
    for mt in mutants(body):
        res = cb.verify_text(mumei_bin, head + apply(body, mt), timeout)
        msg = res["diagnostics"][0]["message"].splitlines()[0][:200] if res["diagnostics"] else ""
        rows.append({**mt, "outcome": OUTCOME.get(res["outcome"], "invalid"), "status": res["status"],
                     "message": msg})
    return {"id": case["id"], "language": case["language"], "function": case["function"],
            "case_hash": case["case_hash"], "mutants": rows}


def tally(rows: list[dict]) -> dict:
    t = {"mutants": len(rows), "killed": 0, "survived": 0, "invalid": 0}
    for r in rows:
        t[r["outcome"]] += 1
    decided = t["killed"] + t["survived"]
    t["score"] = round(t["killed"] / decided, 3) if decided else None
    return t


def render(doc: dict) -> str:
    cases = doc["cases"]
    every = [m for c in cases for m in c["mutants"]]
    total = tally(every)
    ver = doc.get("verifier") or {}
    out = ["# Mutation control", "",
           "<!-- Generated by scripts/run_mutation_control.py; do not edit by hand. -->", "",
           f"First-order mutants of the {len(cases)} fixed reference ports in the contract benchmark, each verified "
           "under the unchanged contract. A killed mutant is refuted, a surviving one is proven, an invalid one "
           "verifies neither way. Score = killed / (killed + survived).", "",
           f"Verifier: {ver.get('version') or 'unknown'}" + (f" at `{ver['commit'][:12]}`" if ver.get("commit") else ""), "",
           "| | Mutants | Killed | Survived | Invalid | Score |", "|---|---:|---:|---:|---:|---:|"]

    def row(label, t):
        score = "—" if t["score"] is None else f"{t['score']:.0%}"
        return f"| {label} | {t['mutants']} | {t['killed']} | {t['survived']} | {t['invalid']} | {score} |"
    out.append(row("**all**", total))
    for lang in cb.LANGUAGES:
        rows = [m for c in cases if c["language"] == lang for m in c["mutants"]]
        if rows:
            out.append(row(lang, tally(rows)))
    for op in ("relational", "logical", "arithmetic", "constant"):
        rows = [m for m in every if m["op"] == op]
        if rows:
            out.append(row(f"{op} mutants", tally(rows)))
    no_mutants = [c["id"] for c in cases if not c["mutants"]]
    if no_mutants:
        out += ["", "Ports with no mutable token: " + ", ".join(f"`{i}`" for i in no_mutants) + "."]
    out += ["", "A survivor is either a behaviour the contract does not pin down or an equivalent mutant. "
            "The benchmark contracts state one requirement each, so survivors in unrelated parts of a body "
            "are expected; they show how much of the body a contract constrains, not a defect in the "
            "benchmark.", "", "## Surviving mutants", ""]
    bodies = doc.get("_bodies", {})
    any_survivor = False
    for c in cases:
        surv = [m for m in c["mutants"] if m["outcome"] == "survived"]
        if not surv:
            continue
        any_survivor = True
        t = tally(c["mutants"])
        out.append(f"- `{c['id']}` ({c['language']}, `{c['function']}`): {t['survived']} of {t['mutants']}")
        body = bodies.get(c["id"])
        for m in surv:
            where = f" — `{context(body, m)}`" if body else ""
            out.append(f"  - {m['op']} `{m['from']}` → `{m['to']}` at {m['at']}{where}")
    if not any_survivor:
        out.append("None.")
    out.append("")
    return "\n".join(out)


def bodies_for(cases: list[dict]) -> dict:
    return {c["id"]: split_fixed(c)[1] for c in cases}


def check(cases: list[dict]) -> list[str]:
    if not RESULT.is_file():
        return [f"{RESULT.relative_to(cb.REPO_ROOT)} is missing; run scripts/run_mutation_control.py"]
    doc = json.loads(RESULT.read_text())
    problems = []
    if not (doc.get("verifier") or {}).get("commit"):
        problems.append("mutation.json does not record the mumei commit it was verified with")
    recorded = {}
    for c in doc["cases"]:
        if c["id"] in recorded:
            problems.append(f"{c['id']}: recorded more than once")
        recorded[c["id"]] = c
    for c in cases:
        r = recorded.pop(c["id"], None)
        if r is None:
            problems.append(f"{c['id']}: no mutation result")
            continue
        if r["case_hash"] != c["case_hash"]:
            problems.append(f"{c['id']}: port or contract changed since the mutation run")
            continue
        want = mutants(split_fixed(c)[1])
        got = [{k: m[k] for k in ("op", "at", "from", "to")} for m in r["mutants"]]
        if got != want:
            problems.append(f"{c['id']}: recorded mutants differ from the mutants of the current port")
        bad = [m for m in r["mutants"] if m.get("outcome") not in ("killed", "survived", "invalid")]
        if bad:
            problems.append(f"{c['id']}: {len(bad)} mutant(s) without a valid outcome")
    problems += [f"{i}: mutation result for a case that no longer exists" for i in sorted(recorded)]
    if not problems:
        expected = render({**doc, "_bodies": bodies_for(cases)})
        if not REPORT.is_file() or REPORT.read_text() != expected:
            problems.append(f"{REPORT.relative_to(cb.REPO_ROOT)} is out of date; run --render-only")
    return problems


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--only", action="append", help="limit to these defect ids (merged into the committed result)")
    p.add_argument("--jobs", type=int, default=4, help="mutants verified in parallel")
    p.add_argument("--timeout", type=int, default=120, help="per-verification timeout in seconds")
    p.add_argument("--mumei-bin", default=os.environ.get("MUMEI_BIN") or shutil.which("mumei"),
                   help="mumei binary (default: $MUMEI_BIN, then mumei on PATH)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate the committed result offline")
    mode.add_argument("--render-only", action="store_true", help="re-render MUTATION.md")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    cases, errors = cb.load_cases()
    if args.check:
        problems = errors + check(cases)
        for msg in problems:
            print(f"error: {msg}", file=sys.stderr)
        print(f"{len(cases)} cases, {len(problems)} problem(s)")
        return 1 if problems else 0
    if errors:
        for msg in errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1
    if args.render_only:
        doc = json.loads(RESULT.read_text())
        REPORT.write_text(render({**doc, "_bodies": bodies_for(cases)}))
        return 0
    if not args.mumei_bin:
        raise SystemExit("mumei binary not found; pass --mumei-bin or set MUMEI_BIN")
    todo = [c for c in cases if not args.only or c["id"] in set(args.only)]
    verifier = cb.verifier_identity(args.mumei_bin)
    if args.only:
        if not RESULT.is_file():
            raise SystemExit(f"{RESULT.relative_to(cb.REPO_ROOT)} does not exist yet; run every case before using --only")
        if json.loads(RESULT.read_text()).get("verifier") != verifier:
            raise SystemExit(f"{RESULT.relative_to(cb.REPO_ROOT)} was recorded with another mumei build; "
                             "rerun every case instead of using --only")
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        done = {r["id"]: r for r in pool.map(lambda c: run_case(c, args.mumei_bin, args.timeout), todo)}
    if args.only:
        old = {c["id"]: c for c in json.loads(RESULT.read_text())["cases"]}
        done = {**old, **done}
    doc = {"recorded_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
           "verifier": verifier,
           "cases": [done[c["id"]] for c in cases if c["id"] in done]}
    RESULT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    REPORT.write_text(render({**doc, "_bodies": bodies_for(cases)}))
    print(f"mutation: {tally([m for c in doc['cases'] for m in c['mutants']])} -> {RESULT.relative_to(cb.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
