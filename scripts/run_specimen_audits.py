#!/usr/bin/env python3
"""Run `mumei-agent audit` over every specimen and score it against DEFECTS.json.

For each specimen directory (specimens/<language>/<id>/) this writes:

  audit/audit.json     directory audit result (--format json)
  audit/audit.md       the same audit rendered with --format markdown
  audit/coverage.json  each planted defect mapped to the audit findings

and specimens/AUDIT_SUMMARY.md with the aggregate.

Only git-tracked files are audited: they are copied to a scratch directory
first, so build output (target/, out/, node_modules/) never leaks into the
audit. Absolute scratch paths are rewritten to repo-relative paths so the
committed reports are reproducible.

Matching is deliberately simple and is documented in AUDIT_SUMMARY.md:
a finding matches a defect when it belongs to the defect's file and names the
defect's function. It counts as `detected` when the finding text also carries
a keyword for the defect's category, `function_flagged` when it names the
function but describes something else, `advisory_only` when the only signal is
a next_steps advisory, and `missed` otherwise.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SPECIMENS_ROOT = REPO_ROOT / "specimens"

# Categories the audit pipeline targets today (see specimens/README.md).
TARGET_CATEGORIES = {
    "integer-overflow",
    "integer-underflow",
    "division-by-zero",
    "out-of-bounds",
    "off-by-one",
    "null-dereference",
    "missing-precondition",
    "invariant-violation",
    "invalid-state-transition",
    "reentrancy",
    "access-control",
    "tx-origin-auth",
    "unchecked-call",
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "integer-overflow": ["overflow", "wrap", "arithmetic bounds"],
    "integer-underflow": ["underflow", "overflow", "wrap", "negative", "arithmetic bounds"],
    "division-by-zero": ["division", "divide", "divisor", "zero"],
    "out-of-bounds": ["bounds", "index", "out of range", "len_"],
    "off-by-one": ["bounds", "index", "off-by-one", "len_"],
    "null-dereference": ["null", "nil", "none", "undefined", "dereference"],
    "missing-precondition": ["precondition", "requires", "negative", "non-negative", "positive", "bounds contract"],
    "invariant-violation": ["invariant", "conserv", "non-negative", "ensures"],
    "invalid-state-transition": ["state", "transition", "invalidprestate"],
    "reentrancy": ["reentran", "checks-effects", "cei", "external call before"],
    "access-control": ["access control", "onlyowner", "owner", "authoriz", "msg.sender"],
    "missing-authorization": ["authoriz", "access control", "owner", "msg.sender"],
    "missing-authentication": ["authenticat", "credential"],
    "tx-origin-auth": ["tx.origin"],
    "unchecked-call": ["unchecked", "return value", "low-level call"],
    "rounding-error": ["round", "precision", "truncat"],
    "float-money": ["float", "precision", "round"],
    "sql-injection": ["sql", "inject"],
    "command-injection": ["command", "shell", "inject"],
    "path-traversal": ["path", "traversal"],
    "xss": ["xss", "escape", "html"],
    "ssrf": ["ssrf", "url", "request forgery"],
    "open-redirect": ["redirect"],
    "insecure-deserialization": ["deserializ", "pickle"],
    "idor": ["authoriz", "idor", "owner"],
    "hardcoded-secret": ["secret", "hardcoded", "credential"],
    "weak-crypto": ["md5", "sha1", "crypto", "hash"],
    "insecure-randomness": ["random", "predictable"],
    "timing-side-channel": ["timing", "constant-time", "constant time"],
    "redos": ["regex", "redos", "backtrack"],
    "race-condition": ["race", "lock", "mutex", "concurren", "atomic"],
    "toctou": ["race", "toctou", "time-of-check"],
    "resource-leak": ["leak", "close", "resource"],
    "unbounded-resource": ["unbounded", "memory", "limit"],
    "denial-of-service": ["denial", "dos", "gas", "unbounded"],
    "front-running": ["front-run", "frontrun", "ordering"],
    "timestamp-dependence": ["timestamp", "block.timestamp"],
    "signature-replay": ["replay", "nonce", "signature"],
    "mass-assignment": ["mass assignment", "overwrite"],
    "information-exposure": ["exposure", "leak", "disclos"],
    "error-handling": ["error", "exception", "unwrap", "panic"],
    "logic-error": [],
}

STRONG_KINDS = ("verification_violations", "spec_health_issues", "cross_validation_gaps", "trusted_atoms")
ADVISORY_RE = re.compile(r":\s*([A-Za-z_][A-Za-z0-9_.:]*)\.(requires|ensures)\b")


def short_name(function: str) -> str:
    return re.split(r"\.|::", function)[-1]


def names_function(text: str, function: str) -> bool:
    name = re.escape(short_name(function))
    return re.search(rf"(?<![A-Za-z0-9_]){name}(?![A-Za-z0-9_])", text) is not None


def category_hit(text: str, category: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in CATEGORY_KEYWORDS.get(category, []))


def rewrite_paths(value: Any, scratch: str, label: str) -> Any:
    if isinstance(value, str):
        return value.replace(scratch, label)
    if isinstance(value, list):
        return [rewrite_paths(v, scratch, label) for v in value]
    if isinstance(value, dict):
        return {k: rewrite_paths(v, scratch, label) for k, v in value.items()}
    return value


def git_rev(path: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def tracked_files(specimen_dir: Path) -> list[Path]:
    rel = specimen_dir.relative_to(REPO_ROOT)
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--", str(rel)],
        capture_output=True, text=True, check=True,
    )
    files = [REPO_ROOT / p for p in out.stdout.split("\0") if p]
    return [f for f in files if "audit" not in f.relative_to(specimen_dir).parts[:1]]


def run_audit(agent_repo: Path, mumei_bin: str, target: Path, fmt: str, timeout: int) -> tuple[int, str, str]:
    env = dict(os.environ, MUMEI_BIN=mumei_bin)
    cmd = ["uv", "run", "python", "-m", "agent", "audit", "--code-file", str(target), "--format", fmt]
    proc = subprocess.run(cmd, cwd=agent_repo, env=env, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def collect_findings(file_result: dict) -> list[dict]:
    findings = []
    for kind in STRONG_KINDS:
        for item in file_result.get(kind) or []:
            text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, sort_keys=True)
            findings.append({"kind": kind, "text": text})
    for cx in file_result.get("counterexample_values") or []:
        fn = cx.get("function_name", "")
        findings.append({
            "kind": "counterexample_values",
            "text": f"counterexample for `{fn}`: {json.dumps(cx.get('counterexample'), sort_keys=True)}",
        })
    return findings


def advisory_functions(audit: dict) -> list[str]:
    names = []
    for step in audit.get("next_steps") or []:
        m = ADVISORY_RE.search(str(step.get("action", "")))
        if m:
            names.append(m.group(1))
    return names


def score(defects_doc: dict, audit: dict, label: str) -> dict:
    by_file: dict[str, list[dict]] = {}
    for fr in audit.get("file_results") or []:
        src = str(fr.get("source_file", ""))
        rel = src[len(label) + 1:] if src.startswith(label + "/") else src
        by_file.setdefault(rel, []).extend(collect_findings(fr))
    advisories = advisory_functions(audit)

    matched_finding_ids: set[tuple[str, int]] = set()
    results = []
    for d in defects_doc["defects"]:
        findings = by_file.get(d["file"], [])
        hits = [(i, f) for i, f in enumerate(findings) if names_function(f["text"], d["function"])]
        cat_hits = [(i, f) for i, f in hits if category_hit(f["text"], d["category"])]
        if cat_hits:
            status, used = "detected", cat_hits
        elif hits:
            status, used = "function_flagged", hits
        elif any(short_name(a) == short_name(d["function"]) for a in advisories):
            status, used = "advisory_only", []
        else:
            status, used = "missed", []
        for i, _ in hits:
            matched_finding_ids.add((d["file"], i))
        results.append({
            "id": d["id"],
            "file": d["file"],
            "function": d["function"],
            "category": d["category"],
            "class": d["class"],
            "in_target_category": d["category"] in TARGET_CATEGORIES,
            "status": status,
            "findings": [f["text"] for _, f in used],
        })

    unmatched = []
    for rel, findings in sorted(by_file.items()):
        for i, f in enumerate(findings):
            if (rel, i) not in matched_finding_ids and f["kind"] != "counterexample_values" \
                    and not f["text"].split(": ", 1)[-1].startswith("Z3 Counter-example"):
                unmatched.append({"file": rel, "kind": f["kind"], "text": f["text"]})
    return {"defects": results, "unmatched_findings": unmatched, "advisory_functions": advisories}


def counts(results: list[dict]) -> dict[str, int]:
    c = {"total": len(results), "detected": 0, "function_flagged": 0, "advisory_only": 0, "missed": 0}
    for r in results:
        c[r["status"]] += 1
    return c


def audit_specimen(specimen_dir: Path, agent_repo: Path, mumei_bin: str, timeout: int, meta: dict) -> dict:
    label = str(specimen_dir.relative_to(REPO_ROOT))
    defects_doc = json.loads((specimen_dir / "DEFECTS.json").read_text(encoding="utf-8"))
    files = tracked_files(specimen_dir)
    if not files:
        raise SystemExit(f"{label}: no git-tracked files; commit the specimen first")
    out_dir = specimen_dir / "audit"
    out_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="specimen-audit-") as tmp:
        scratch = Path(tmp) / specimen_dir.name
        for f in files:
            dest = scratch / f.relative_to(specimen_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
        scratch_str = str(scratch.resolve())
        rc_json, out_json, err_json = run_audit(agent_repo, mumei_bin, scratch, "json", timeout)
        rc_md, out_md, _ = run_audit(agent_repo, mumei_bin, scratch, "markdown", timeout)
    try:
        audit = json.loads(out_json)
    except json.JSONDecodeError:
        raise SystemExit(f"{label}: audit did not return JSON (exit {rc_json}):\n{err_json[-2000:]}")
    audit = rewrite_paths(audit, scratch_str, label)
    (out_dir / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "audit.md").write_text(out_md.replace(scratch_str, label), encoding="utf-8")
    scored = score(defects_doc, audit, label)
    coverage = {
        "specimen": defects_doc["specimen"],
        "language": defects_doc["language"],
        "audit_exit_code": rc_json,
        "audit_markdown_exit_code": rc_md,
        "verification_status": audit.get("verification_status"),
        "files_audited": audit.get("total_files"),
        "files_with_issues": audit.get("files_with_issues"),
        "counts": counts(scored["defects"]),
        **scored,
        "meta": meta,
    }
    (out_dir / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return coverage


def pct(n: int, d: int) -> str:
    return f"{(100 * n / d):.0f}%" if d else "-"


def write_summary(coverages: list[dict], meta: dict, path: Path) -> None:
    lines = [
        "# Specimen audit summary",
        "",
        "Generated by `scripts/run_specimen_audits.py`. Do not edit by hand.",
        "",
        f"- mumei-agent: `{meta['mumei_agent_commit']}`",
        f"- mumei: `{meta['mumei_commit']}` (`{meta['mumei_version']}`)",
        f"- LLM provider configured: `{meta['llm_configured']}`",
        f"- Command: `{meta['command']}`",
        f"- Generated: {meta['generated_at']}",
        "",
        "## How defects are scored",
        "",
        "A finding matches a planted defect when it is reported for the defect's file and names the defect's",
        "function. `detected` means the finding text also carries a keyword for the defect's category;",
        "`function_flagged` means the audit flagged that function for something else; `advisory_only` means the",
        "only signal is an \"underspecified intent\" next step for that function; `missed` means nothing.",
        "\"Target\" categories are the ones the audit is designed to check today (arithmetic, bounds, null,",
        "preconditions, invariants, state transitions, and the Solidity reentrancy/access-control/unchecked-call",
        "heuristics). Findings that match no planted defect are listed per specimen in `audit/coverage.json`",
        "under `unmatched_findings`; they are either extra real issues or false positives and need human review.",
        "",
        "## Per specimen",
        "",
        "| Specimen | Defects | Detected | Function flagged | Advisory only | Missed | Target-category detected | Unmatched findings |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    totals = {"total": 0, "detected": 0, "function_flagged": 0, "advisory_only": 0, "missed": 0}
    tgt_total = tgt_det = unmatched_total = 0
    by_cat: dict[str, dict[str, int]] = {}
    by_lang: dict[str, dict[str, int]] = {}
    for cov in coverages:
        c = cov["counts"]
        for k in totals:
            totals[k] += c[k]
        tgt = [r for r in cov["defects"] if r["in_target_category"]]
        td = sum(1 for r in tgt if r["status"] == "detected")
        tgt_total += len(tgt)
        tgt_det += td
        unmatched_total += len(cov["unmatched_findings"])
        lang = by_lang.setdefault(cov["language"], {"total": 0, "detected": 0, "flagged": 0, "tgt": 0, "tgt_det": 0})
        lang["total"] += c["total"]
        lang["detected"] += c["detected"]
        lang["flagged"] += c["detected"] + c["function_flagged"]
        lang["tgt"] += len(tgt)
        lang["tgt_det"] += td
        for r in cov["defects"]:
            bc = by_cat.setdefault(r["category"], {"total": 0, "detected": 0, "function_flagged": 0, "advisory_only": 0, "missed": 0})
            bc["total"] += 1
            bc[r["status"]] += 1
        rel = f"{cov['language']}/{cov['specimen']}"
        lines.append(
            f"| [{cov['specimen']}]({rel}/audit/audit.md) | {c['total']} | {c['detected']} | {c['function_flagged']} | "
            f"{c['advisory_only']} | {c['missed']} | {td}/{len(tgt)} | {len(cov['unmatched_findings'])} |"
        )
    lines.append(
        f"| **Total** | **{totals['total']}** | **{totals['detected']}** | **{totals['function_flagged']}** | "
        f"**{totals['advisory_only']}** | **{totals['missed']}** | **{tgt_det}/{tgt_total}** | **{unmatched_total}** |"
    )
    lines += [
        "",
        f"Detected overall: {totals['detected']}/{totals['total']} ({pct(totals['detected'], totals['total'])}); "
        f"target categories: {tgt_det}/{tgt_total} ({pct(tgt_det, tgt_total)}).",
        "",
        "## Per language",
        "",
        "| Language | Defects | Detected | Detected or function flagged | Target-category detected |",
        "|---|---:|---:|---:|---:|",
    ]
    for lang, v in sorted(by_lang.items()):
        lines.append(
            f"| {lang} | {v['total']} | {v['detected']} ({pct(v['detected'], v['total'])}) | "
            f"{v['flagged']} ({pct(v['flagged'], v['total'])}) | {v['tgt_det']}/{v['tgt']} ({pct(v['tgt_det'], v['tgt'])}) |"
        )
    lines += [
        "",
        "## Per category",
        "",
        "| Category | Target | Defects | Detected | Function flagged | Advisory only | Missed |",
        "|---|:---:|---:|---:|---:|---:|---:|",
    ]
    for cat, v in sorted(by_cat.items(), key=lambda kv: (kv[0] not in TARGET_CATEGORIES, kv[0])):
        lines.append(
            f"| {cat} | {'yes' if cat in TARGET_CATEGORIES else ''} | {v['total']} | {v['detected']} | "
            f"{v['function_flagged']} | {v['advisory_only']} | {v['missed']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def discover(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.glob("*/*/DEFECTS.json"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("specimens", nargs="*", help="specimen dirs (default: all)")
    parser.add_argument("--mumei-agent-repo", default=str(REPO_ROOT.parent / "mumei-agent"))
    parser.add_argument("--mumei-repo", default=str(REPO_ROOT.parent / "mumei"))
    parser.add_argument("--mumei-bin", default=os.environ.get("MUMEI_BIN"))
    parser.add_argument("--timeout", type=int, default=900, help="per-audit timeout in seconds")
    parser.add_argument("--summary", default=str(SPECIMENS_ROOT / "AUDIT_SUMMARY.md"))
    args = parser.parse_args(argv)

    agent_repo = Path(args.mumei_agent_repo).resolve()
    mumei_repo = Path(args.mumei_repo).resolve()
    mumei_bin = args.mumei_bin or str(mumei_repo / "target" / "debug" / "mumei")
    try:
        version = subprocess.run([mumei_bin, "--version"], capture_output=True, text=True).stdout.strip()
    except OSError as exc:
        raise SystemExit(f"cannot run mumei binary {mumei_bin}: {exc}")
    meta = {
        "mumei_agent_commit": git_rev(agent_repo),
        "mumei_commit": git_rev(mumei_repo),
        "mumei_version": version,
        "llm_configured": bool(os.environ.get("LLM_API_KEY")) or (agent_repo / ".env").is_file(),
        "command": "mumei-agent audit --code-file <specimen-dir> --format json|markdown",
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    dirs = [Path(d).resolve() for d in args.specimens] or discover(SPECIMENS_ROOT)
    coverages = []
    for d in dirs:
        cov = audit_specimen(d, agent_repo, mumei_bin, args.timeout, meta)
        c = cov["counts"]
        print(f"{cov['specimen']}: {c['detected']}/{c['total']} detected, {c['function_flagged']} function-flagged, "
              f"{c['advisory_only']} advisory, {c['missed']} missed, {len(cov['unmatched_findings'])} unmatched")
        coverages.append(cov)
    if not args.specimens:
        write_summary(coverages, meta, Path(args.summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
