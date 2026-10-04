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
function but describes something else, and `missed` otherwise.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
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
    "missing-precondition": ["precondition", "requires", "negative", "non-negative", "positive", "bounds contract", "range contract"],
    "invariant-violation": ["invariant", "conserv", "non-negative", "ensures"],
    "invalid-state-transition": ["transition", "invalidprestate", "pre-state"],
    "reentrancy": ["reentran", "checks-effects", "cei", "external call before"],
    "access-control": ["access control", "access-control", "onlyowner", "owner", "authoriz", "msg.sender"],
    "missing-authorization": ["authoriz", "access control", "access-control", "owner", "msg.sender"],
    "missing-authentication": ["authenticat", "credential"],
    "tx-origin-auth": ["tx.origin"],
    "unchecked-call": ["unchecked", "return value", "low-level call"],
    "rounding-error": ["round", "precision", "truncat"],
    "float-money": ["float", "precision", "round"],
    "sql-injection": ["sql", "inject"],
    "command-injection": ["command", "shell", "inject"],
    "path-traversal": ["traversal", "../"],
    "xss": ["xss", "escape", "html"],
    "ssrf": ["ssrf", "request forgery"],
    "open-redirect": ["redirect"],
    "insecure-deserialization": ["deserializ", "pickle"],
    "idor": ["authoriz", "idor", "owner"],
    "hardcoded-secret": ["secret", "hardcoded", "credential"],
    "weak-crypto": ["md5", "sha1", "crypto", "hash"],
    "insecure-randomness": ["random", "predictable"],
    "timing-side-channel": ["timing", "constant-time", "constant time"],
    "redos": ["regex", "redos", "backtrack"],
    "race-condition": ["data race", "race condition", "mutex", "concurren", "atomic", "lost update"],
    "toctou": ["race condition", "toctou", "time-of-check"],
    "resource-leak": ["leak", "close", "resource"],
    "unbounded-resource": ["unbounded", "memory", "limit"],
    "denial-of-service": ["denial", "denial of service", "denial-of-service", "gas", "unbounded"],
    "front-running": ["front-run", "frontrun", "ordering"],
    "timestamp-dependence": ["timestamp", "block.timestamp"],
    "signature-replay": ["replay", "nonce", "signature"],
    "mass-assignment": ["mass assignment", "overwrite"],
    "information-exposure": ["exposure", "leak", "disclos"],
    "error-handling": ["exception", "unwrap", "panic", "ignored error", "unchecked error"],
    "logic-error": [],
}

STRONG_KINDS = ("verification_violations", "spec_health_issues", "cross_validation_gaps", "trusted_atoms")


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


def score(defects_doc: dict, audit: dict, label: str,
          adjudications: list[dict] | None = None) -> dict:
    adjudications = adjudications or []
    by_file: dict[str, list[dict]] = {}
    for fr in audit.get("file_results") or []:
        src = str(fr.get("source_file", ""))
        rel = src[len(label) + 1:] if src.startswith(label + "/") else src
        by_file.setdefault(rel, []).extend(collect_findings(fr))

    matched_finding_ids: set[tuple[str, int]] = set()
    results = []
    for d in defects_doc["defects"]:
        findings = by_file.get(d["file"], [])
        hits = [(i, f) for i, f in enumerate(findings) if names_function(f["text"], d["function"])]
        cat_hits = [(i, f) for i, f in hits if category_hit(f["text"], d["category"])]
        applied = []
        for a in adjudications:
            if a.get("defect") != d["id"] or a.get("verdict") != "not_category_evidence":
                continue
            needle = a.get("finding_contains", "")
            if not needle:
                continue
            kept = []
            for i, f in cat_hits:
                if needle in f["text"]:
                    applied.append(a.get("reason", ""))
                else:
                    kept.append((i, f))
            cat_hits = kept
        if cat_hits:
            status, used = "detected", cat_hits
        elif hits:
            status, used = "function_flagged", hits
        else:
            status, used = "missed", []
        for i, _ in hits:
            matched_finding_ids.add((d["file"], i))
        entry = {
            "id": d["id"],
            "file": d["file"],
            "function": d["function"],
            "category": d["category"],
            "class": d["class"],
            "in_target_category": d["category"] in TARGET_CATEGORIES,
            "status": status,
            "findings": [f["text"] for _, f in used],
        }
        if applied:
            entry["adjudicated"] = applied
        results.append(entry)

    unmatched = []
    for rel, findings in sorted(by_file.items()):
        for i, f in enumerate(findings):
            if (rel, i) not in matched_finding_ids and f["kind"] != "counterexample_values" \
                    and "Z3 Counter-example:" not in f["text"]:
                unmatched.append({"file": rel, "kind": f["kind"], "text": f["text"]})
    return {"defects": results, "unmatched_findings": unmatched}


def counts(results: list[dict]) -> dict[str, int]:
    c = {"total": len(results), "detected": 0, "function_flagged": 0, "missed": 0}
    for r in results:
        c[r["status"]] += 1
    return c


def aggregate(coverages: list[dict]) -> dict:
    """Totals, per-language and per-category stats over a set of coverages.

    Shared by write_summary and the history entry so numbers are computed once.
    """
    totals = {"total": 0, "detected": 0, "function_flagged": 0,
              "missed": 0, "target_total": 0, "target_detected": 0, "unmatched": 0}
    by_lang: dict[str, dict[str, int]] = {}
    by_cat: dict[str, dict[str, Any]] = {}
    for cov in coverages:
        c = cov["counts"]
        for k in ("total", "detected", "function_flagged", "missed"):
            totals[k] += c[k]
        tgt = [r for r in cov["defects"] if r["in_target_category"]]
        td = sum(1 for r in tgt if r["status"] == "detected")
        totals["target_total"] += len(tgt)
        totals["target_detected"] += td
        totals["unmatched"] += len(cov["unmatched_findings"])
        lang = by_lang.setdefault(cov["language"], {"total": 0, "detected": 0, "flagged": 0,
                                                    "target_total": 0, "target_detected": 0})
        lang["total"] += c["total"]
        lang["detected"] += c["detected"]
        lang["flagged"] += c["detected"] + c["function_flagged"]
        lang["target_total"] += len(tgt)
        lang["target_detected"] += td
        for r in cov["defects"]:
            bc = by_cat.setdefault(r["category"], {"total": 0, "detected": 0, "function_flagged": 0,
                                                   "missed": 0,
                                                   "in_target": r["category"] in TARGET_CATEGORIES})
            bc["total"] += 1
            bc[r["status"]] += 1
    return {"totals": totals, "by_language": by_lang, "by_category": by_cat}


def audit_failure(rc_json: int, rc_md: int, audit: dict) -> str | None:
    """A broken audit (nonzero exit, errors, or rate-limited skips) is fatal.

    audit["success"] is False whenever issues are found, so it is NOT a
    failure signal and is deliberately not checked here.
    """
    if rc_json != 0:
        return f"audit exited {rc_json}"
    if rc_md != 0:
        return f"markdown audit exited {rc_md}"
    errors = audit.get("errors")
    if errors:
        return f"audit reported errors: {errors[:3]}"
    skipped = audit.get("skipped_rate_limited_files")
    if skipped:
        return f"audit skipped rate-limited files: {skipped}"
    return None


def audit_specimen(specimen_dir: Path, agent_repo: Path, mumei_bin: str, timeout: int,
                   meta: dict, adjudications: list[dict] | None = None) -> dict:
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
    failure = audit_failure(rc_json, rc_md, audit)
    if failure:
        raise SystemExit(f"{label}: {failure}")
    audit = rewrite_paths(audit, scratch_str, label)
    (out_dir / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "audit.md").write_text(out_md.replace(scratch_str, label), encoding="utf-8")
    scored = score(defects_doc, audit, label, adjudications)
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
        f"- Mode: {'with LLM' if meta['llm_configured'] else 'no LLM'}",
        f"- Command: `{meta['command']}`",
        f"- Generated: {meta['generated_at']}",
        "",
        "## How defects are scored",
        "",
        "A finding matches a planted defect when it is reported for the defect's file and names the defect's",
        "function. `detected` means the finding text also carries a keyword for the defect's category;",
        "`function_flagged` means the audit flagged that function for something else; `missed` means nothing.",
        "\"Target\" categories are the ones the audit is designed to check today (arithmetic, bounds, null,",
        "preconditions, invariants, state transitions, and the Solidity reentrancy/access-control/unchecked-call",
        "heuristics). Findings that match no planted defect are listed per specimen in `audit/coverage.json`",
        "under `unmatched_findings`; they are either extra real issues or false positives and need human review.",
        "",
        "## Per specimen",
        "",
        "| Specimen | Defects | Detected | Function flagged | Missed | Target-category detected | Unmatched findings |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    agg = aggregate(coverages)
    totals = agg["totals"]
    tgt_total = totals["target_total"]
    tgt_det = totals["target_detected"]
    unmatched_total = totals["unmatched"]
    by_cat = agg["by_category"]
    by_lang = agg["by_language"]
    for cov in coverages:
        c = cov["counts"]
        tgt = [r for r in cov["defects"] if r["in_target_category"]]
        td = sum(1 for r in tgt if r["status"] == "detected")
        rel = f"{cov['language']}/{cov['specimen']}"
        lines.append(
            f"| [{cov['specimen']}]({rel}/audit/audit.md) | {c['total']} | {c['detected']} | {c['function_flagged']} | "
            f"{c['missed']} | {td}/{len(tgt)} | {len(cov['unmatched_findings'])} |"
        )
    lines.append(
        f"| **Total** | **{totals['total']}** | **{totals['detected']}** | **{totals['function_flagged']}** | "
        f"**{totals['missed']}** | **{tgt_det}/{tgt_total}** | **{unmatched_total}** |"
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
            f"{v['flagged']} ({pct(v['flagged'], v['total'])}) | "
            f"{v['target_detected']}/{v['target_total']} ({pct(v['target_detected'], v['target_total'])}) |"
        )
    lines += [
        "",
        "## Per category",
        "",
        "| Category | Target | Defects | Detected | Function flagged | Missed |",
        "|---|:---:|---:|---:|---:|---:|" ,
    ]
    for cat, v in sorted(by_cat.items(), key=lambda kv: (kv[0] not in TARGET_CATEGORIES, kv[0])):
        lines.append(
            f"| {cat} | {'yes' if cat in TARGET_CATEGORIES else ''} | {v['total']} | {v['detected']} | "
            f"{v['function_flagged']} | {v['missed']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Benchmark history and scoreboard
# ---------------------------------------------------------------------------

SCOREBOARD_START = "<!-- scoreboard:start -->"
SCOREBOARD_END = "<!-- scoreboard:end -->"


def _specimen_files(specimen_dir: Path) -> list[Path]:
    """Files that make up a specimen, excluding audit/ output.

    Git-tracked files when specimen_dir lives under the repo; everything on
    disk (except audit/) otherwise, so corpus_info also works on scratch dirs.
    """
    try:
        return tracked_files(specimen_dir)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return sorted(f for f in specimen_dir.rglob("*")
                      if f.is_file() and "audit" not in f.relative_to(specimen_dir).parts)


def corpus_info(root: Path) -> dict:
    """Specimen/defect counts plus a hash of every specimen file under root.

    Hashes the full specimen content (not just DEFECTS.json) so a source
    change with unchanged ground truth still produces a new run key.
    """
    h = hashlib.sha256()
    dirs = sorted(d for d in root.glob("*/*")
                  if d.is_dir() and (d / "DEFECTS.json").is_file())
    defects = 0
    files: list[Path] = []
    for d in dirs:
        defects += len(json.loads((d / "DEFECTS.json").read_bytes())["defects"])
        files.extend(_specimen_files(d))
    for f in sorted(set(files), key=lambda p: p.as_posix()):
        try:
            rel = f.relative_to(root).as_posix()
        except ValueError:
            rel = f.as_posix()
        h.update(rel.encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return {"specimens": len(dirs), "defects": defects, "hash": h.hexdigest()}


ADJUDICATIONS_FILE = "adjudications.json"


def load_adjudications(root: Path) -> list[dict]:
    """Manual rulings for keyword matches that are not real category evidence.

    Validates eagerly: a ruling naming an unknown defect id or an unsupported
    verdict fails loudly instead of silently doing nothing.
    """
    path = root / "scoreboard" / ADJUDICATIONS_FILE
    if not path.is_file():
        return []
    entries = json.loads(path.read_text(encoding="utf-8")).get("adjudications") or []
    known_ids = {
        d["id"]
        for f in root.glob("*/*/DEFECTS.json")
        for d in json.loads(f.read_bytes())["defects"]
    }
    for a in entries:
        if a.get("verdict") != "not_category_evidence":
            raise SystemExit(
                f"{path}: adjudication for {a.get('defect')!r}: "
                f"unsupported verdict {a.get('verdict')!r}")
        if a.get("defect") not in known_ids:
            raise SystemExit(
                f"{path}: adjudication references unknown defect {a.get('defect')!r}")
    return entries


def load_history(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema": 1, "runs": []}


def scoring_hash(root: Path) -> str:
    """Hash of the adjudications file (empty input when absent).

    Part of the run key so a ruling change can't silently overwrite a run
    whose totals it changed."""
    path = root / "scoreboard" / ADJUDICATIONS_FILE
    data = path.read_bytes() if path.is_file() else b""
    return hashlib.sha256(data).hexdigest()


def entry_llm(entry: dict) -> bool:
    """Whether a history run was audited with an LLM provider configured.

    Entries written before the `llm` field existed infer it from
    `llm_configured`; entries with neither default to the no-LLM series."""
    if "llm" in entry:
        return bool(entry["llm"])
    return bool(entry.get("llm_configured"))


def latest_by_mode(runs: list[dict]) -> dict[bool, dict | None]:
    """The newest run per mode: {False: no-LLM run, True: with-LLM run}."""
    latest: dict[bool, dict | None] = {False: None, True: None}
    for run in runs:
        latest[entry_llm(run)] = run
    return latest


def history_entry(coverages: list[dict], meta: dict, corpus: dict,
                  score_hash: str) -> dict:
    agg = aggregate(coverages)
    t = agg["totals"]
    return {
        "generated_at": meta["generated_at"],
        "mumei_agent_commit": meta["mumei_agent_commit"],
        "mumei_commit": meta["mumei_commit"],
        "mumei_version": meta["mumei_version"],
        "llm_configured": meta["llm_configured"],
        "llm": bool(meta["llm_configured"]),
        "corpus": corpus,
        "scoring_hash": score_hash,
        "totals": {k: t[k] for k in ("total", "detected", "function_flagged",
                                    "missed",
                                    "target_total", "target_detected")},
        "by_language": {
            lang: {"total": v["total"], "detected": v["detected"], "flagged": v["flagged"],
                   "target_total": v["target_total"], "target_detected": v["target_detected"]}
            for lang, v in agg["by_language"].items()
        },
        "by_category": {
            cat: {"total": v["total"], "detected": v["detected"], "in_target": v["in_target"]}
            for cat, v in agg["by_category"].items()
        },
        "specimens": {
            cov["specimen"]: {"language": cov["language"],
                              "total": cov["counts"]["total"],
                              "detected": cov["counts"]["detected"],
                              "function_flagged": cov["counts"]["function_flagged"]}
            for cov in coverages
        },
    }


def record_run(history_path: Path, entry: dict) -> dict:
    """Append a run to history.json, replacing the last entry when the run key
    (agent commit, mumei commit, corpus hash, scoring hash, llm mode) is
    unchanged."""
    hist = load_history(history_path)
    runs = hist.setdefault("runs", [])
    empty_hash = hashlib.sha256(b"").hexdigest()
    key = (entry.get("mumei_agent_commit"), entry.get("mumei_commit"),
           (entry.get("corpus") or {}).get("hash"),
           entry.get("scoring_hash", empty_hash),
           entry_llm(entry))
    if runs:
        last = runs[-1]
        last_key = (last.get("mumei_agent_commit"), last.get("mumei_commit"),
                    (last.get("corpus") or {}).get("hash"),
                    last.get("scoring_hash", empty_hash),
                    entry_llm(last))
        if last_key == key:
            runs[-1] = entry
        else:
            runs.append(entry)
    else:
        runs.append(entry)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(hist, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    return hist


def _esc(text: Any) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def svg_placeholder(text: str = "No benchmark runs yet", width: int = 720,
                    height: int = 200) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="sans-serif">\n'
        f'  <rect width="{width}" height="{height}" fill="white"/>\n'
        f'  <text x="{width // 2}" y="{height // 2}" font-size="18" fill="#57606a" '
        f'text-anchor="middle">{_esc(text)}</text>\n'
        f'</svg>\n'
    )


# Bar colors per mode: (detected, detected or flagged)
_MODE_COLORS = {
    False: ("#2f81f7", "#bf8700"),
    True: ("#8250df", "#cf222e"),
}
_MODE_LABEL = {False: "No LLM", True: "With LLM"}
_MUTED = "#afb8c1"


def svg_by_language(modes: dict[bool, dict | None]) -> str:
    """Grouped horizontal bars per language: one detected/detected-or-flagged
    group per mode (no LLM / with LLM). Modes without runs draw no bars."""
    nollm, llm = modes.get(False), modes.get(True)
    if nollm is None and llm is None:
        return svg_placeholder()
    present = [m for m in (False, True) if modes.get(m) is not None]
    anchor = nollm or llm
    langs = sorted({lang for m in present for lang in modes[m]["by_language"]})
    sha = (anchor.get("mumei_agent_commit") or "?")[:7]
    date = (anchor.get("generated_at") or "")[:10]

    W = 720
    label_w, bar_w, bar_h, gap = 150, 460, 15, 5
    bars_per_row = 2 * len(present)
    row_h = bars_per_row * (bar_h + gap) + 12
    top, bottom = 78, 110
    H = top + row_h * (len(langs) + 1) + bottom
    x0 = label_w

    def bar(y: int, n: int, d: int, color: str) -> str:
        p = 100 * n / d if d else 0.0
        w = bar_w * p / 100
        return (
            f'  <rect x="{x0}" y="{y}" width="{w:.1f}" height="{bar_h}" fill="{color}"/>\n'
            f'  <text x="{x0 + w + 6:.1f}" y="{y + bar_h - 3}" font-size="11" '
            f'fill="#24292f">{_esc(f"{n}/{d} · {p:.0f}%")}</text>\n'
        )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif">',
        f'  <rect width="{W}" height="{H}" fill="white"/>',
        f'  <text x="20" y="28" font-size="17" font-weight="bold" fill="#24292f">'
        f'Specimen benchmark — detection by language</text>',
        f'  <text x="20" y="47" font-size="12" fill="#57606a">'
        f'mumei-agent {_esc(sha)} · {_esc(date)}</text>',
    ]
    axis_y = top + row_h * (len(langs) + 1) + 6
    for step in (0, 25, 50, 75, 100):
        gx = x0 + bar_w * step / 100
        parts.append(
            f'  <line x1="{gx:.1f}" y1="{top - 4}" x2="{gx:.1f}" y2="{axis_y}" '
            f'stroke="#d0d7de" stroke-width="1"/>')
        parts.append(
            f'  <text x="{gx:.1f}" y="{axis_y + 16}" font-size="10" fill="#57606a" '
            f'text-anchor="middle">{step}%</text>')

    def lang_values(mode_run: dict | None, lang: str) -> tuple[int, int, int] | None:
        if mode_run is None:
            return None
        if lang == "overall":
            t = mode_run["totals"]
            return (t["total"], t["detected"], t["detected"] + t["function_flagged"])
        v = mode_run["by_language"].get(lang)
        if v is None:
            return None
        return (v["total"], v["detected"], v["flagged"])

    for i, lang in enumerate(langs + ["overall"]):
        y = top + i * row_h
        weight = "bold" if lang == "overall" else "normal"
        parts.append(
            f'  <text x="{x0 - 10}" y="{y + bar_h + gap // 2}" font-size="12" '
            f'font-weight="{weight}" fill="#24292f" text-anchor="end">{_esc(lang)}</text>')
        slot = 0
        for mode in (False, True):
            values = lang_values(modes.get(mode), lang)
            if values is None:
                continue
            total, det, flag = values
            det_color, flag_color = _MODE_COLORS[mode]
            parts.append(bar(y + slot * (bar_h + gap), det, total, det_color))
            parts.append(bar(y + (slot + 1) * (bar_h + gap), flag, total, flag_color))
            slot += 2

    legend_y = axis_y + 36
    lx = x0
    for mode in (False, True):
        if modes.get(mode) is None:
            parts.append(f'  <rect x="{lx}" y="{legend_y}" width="12" height="12" fill="{_MUTED}"/>')
            parts.append(f'  <text x="{lx + 18}" y="{legend_y + 11}" font-size="11" '
                         f'fill="#57606a">{_esc(_MODE_LABEL[mode])} (not run yet)</text>')
            lx += 18 + int(6.5 * (len(_MODE_LABEL[mode]) + 14)) + 24
            continue
        det_color, flag_color = _MODE_COLORS[mode]
        for label, color in (("detected", det_color),
                             ("detected or function-flagged", flag_color)):
            parts.append(f'  <rect x="{lx}" y="{legend_y}" width="12" height="12" fill="{color}"/>')
            parts.append(f'  <text x="{lx + 18}" y="{legend_y + 11}" font-size="11" '
                         f'fill="#24292f">{_esc(_MODE_LABEL[mode])}: {label}</text>')
            lx += 18 + int(6.5 * (len(_MODE_LABEL[mode]) + len(label) + 2)) + 24
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def svg_history(runs: list[dict]) -> str:
    """Line chart of detected %, target detected %, detected-or-flagged % per
    run, split into one series per mode (solid = no LLM, dashed = with LLM).
    A mode with no runs appears in the legend only, marked "(not run yet)"."""
    if not runs:
        return svg_placeholder()
    mode_runs = {False: [r for r in runs if not entry_llm(r)],
                 True: [r for r in runs if entry_llm(r)]}
    W, H = 720, 360
    left, right, top, bottom = 60, 30, 60, 88
    plot_w, plot_h = W - left - right, H - top - bottom

    metrics = [
        ("detected", "#2f81f7",
         lambda r: 100 * r["totals"]["detected"] / r["totals"]["total"]
         if r["totals"]["total"] else 0.0),
        ("target detected", "#1a7f37",
         lambda r: 100 * r["totals"]["target_detected"] / r["totals"]["target_total"]
         if r["totals"]["target_total"] else 0.0),
        ("detected or flagged", "#bf8700",
         lambda r: 100 * (r["totals"]["detected"] + r["totals"]["function_flagged"])
         / r["totals"]["total"] if r["totals"]["total"] else 0.0),
    ]

    def xy_for(series_runs: list[dict], i: int, pct_val: float) -> tuple[float, float]:
        x = left + (plot_w * i / (len(series_runs) - 1)
                    if len(series_runs) > 1 else plot_w / 2)
        y = top + plot_h * (1 - pct_val / 100)
        return x, y

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif">',
        f'  <rect width="{W}" height="{H}" fill="white"/>',
        f'  <text x="20" y="28" font-size="17" font-weight="bold" fill="#24292f">'
        f'Specimen benchmark — detection over runs</text>',
    ]
    for step in (0, 25, 50, 75, 100):
        gy = top + plot_h * (1 - step / 100)
        parts.append(f'  <line x1="{left}" y1="{gy:.1f}" x2="{W - right}" y2="{gy:.1f}" '
                     f'stroke="#d0d7de" stroke-width="1"/>')
        parts.append(f'  <text x="{left - 8}" y="{gy + 4:.1f}" font-size="10" '
                     f'fill="#57606a" text-anchor="end">{step}%</text>')

    legend: list[tuple[str, str]] = []
    for mode in (False, True):
        series_runs = mode_runs[mode]
        if not series_runs:
            legend.append((f"{_MODE_LABEL[mode]} (not run yet)", _MUTED))
            continue
        suffix = "" if mode is False else " (with LLM)"
        dash = ' stroke-dasharray="5 3"' if mode else ""
        for name, color, fn in metrics:
            pts = [xy_for(series_runs, i, fn(r)) for i, r in enumerate(series_runs)]
            if len(pts) > 1:
                d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                parts.append(f'  <polyline points="{d}" fill="none" stroke="{color}" '
                             f'stroke-width="2"{dash}/>')
            for x, y in pts:
                parts.append(f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>')
            legend.append((f"{name}{suffix}", color))
        for i, r in enumerate(series_runs):
            x, _ = xy_for(series_runs, i, 0)
            sha = (r.get("mumei_agent_commit") or "?")[:7]
            date = (r.get("generated_at") or "")[:10]
            tag = _MODE_LABEL[mode]
            parts.append(f'  <text x="{x:.1f}" y="{H - bottom + 18}" font-size="10" '
                         f'fill="#57606a" text-anchor="middle">'
                         f'<tspan x="{x:.1f}" dy="0">{_esc(sha)}</tspan>'
                         f'<tspan x="{x:.1f}" dy="12">{_esc(date)} · {tag}</tspan></text>')
    lx = left
    ly = H - 40
    for name, color in legend:
        if lx + 18 + int(6.5 * len(name)) > W - right:
            lx = left
            ly += 18
        parts.append(f'  <rect x="{lx}" y="{ly}" width="12" height="12" fill="{color}"/>')
        parts.append(f'  <text x="{lx + 18}" y="{ly + 11}" font-size="11" '
                     f'fill="#24292f">{_esc(name)}</text>')
        lx += 18 + int(6.5 * len(name)) + 24
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _sha7(value: Any) -> str:
    return (str(value) if value else "?")[:7]


def readme_block_specimens(history: dict) -> str:
    runs = history.get("runs") or []
    lines = [
        "## Scoreboard",
        "",
        "![Detection by language](scoreboard/by_language.svg)",
        "",
        "![Detection over runs](scoreboard/history.svg)",
        "",
    ]
    if not runs:
        lines += ["No benchmark runs yet. The charts fill in after the first full run.", ""]
    else:
        modes = latest_by_mode(runs)
        for mode in (False, True):
            run = modes[mode]
            label = "with LLM" if mode else "no LLM"
            if run is None:
                lines.append(f"Latest run — {label}: not run yet.")
            else:
                lines.append(
                    f"Latest run — {label}: mumei-agent `{_sha7(run.get('mumei_agent_commit'))}` · "
                    f"mumei `{_sha7(run.get('mumei_commit'))}` ({run.get('mumei_version')}) · "
                    f"{run.get('generated_at')}"
                )
        lines += [
            "",
            "| Language | Defects | No LLM detected | No LLM detected or flagged | With LLM detected | With LLM detected or flagged |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        anchor = modes[False] or modes[True]
        langs = sorted({lang for m in modes.values() if m for lang in m["by_language"]})

        def cells(lang: str, mode: bool) -> tuple[str, str]:
            run = modes[mode]
            if run is None:
                return "—", "—"
            if lang == "overall":
                t = run["totals"]
                total, det, flag = (t["total"], t["detected"],
                                    t["detected"] + t["function_flagged"])
            else:
                v = run["by_language"].get(lang)
                if v is None:
                    return "—", "—"
                total, det, flag = v["total"], v["detected"], v["flagged"]
            return (f"{det}/{total} ({pct(det, total)})",
                    f"{flag}/{total} ({pct(flag, total)})")

        def total_of(lang: str) -> int:
            if lang == "overall":
                return anchor["totals"]["total"]
            return anchor["by_language"].get(lang, {}).get("total", 0)

        for lang in langs + ["overall"]:
            d_nl, f_nl = cells(lang, False)
            d_ll, f_ll = cells(lang, True)
            if lang == "overall":
                lines.append(
                    f"| **Total** | **{total_of(lang)}** | **{d_nl}** | **{f_nl}** | "
                    f"**{d_ll}** | **{f_ll}** |"
                )
            else:
                lines.append(
                    f"| {lang} | {total_of(lang)} | {d_nl} | {f_nl} | {d_ll} | {f_ll} |"
                )
        for mode in (False, True):
            if modes[mode] is None:
                lines += ["", f"_{_MODE_LABEL[mode]}: not run yet._"]
        lines += [
            "",
            "Recent runs:",
            "",
            "| Date | LLM | mumei-agent | mumei | Defects | Detected % | Target detected % | Flagged % |",
            "|---|---|---|---|---|---:|---:|---:|",
        ]
        for r in reversed(runs[-10:]):
            rt = r["totals"]
            lines.append(
                f"| {(r.get('generated_at') or '')[:10]} | "
                f"{'yes' if entry_llm(r) else 'no'} | "
                f"`{_sha7(r.get('mumei_agent_commit'))}` | "
                f"`{_sha7(r.get('mumei_commit'))}` | {rt['total']} | "
                f"{pct(rt['detected'], rt['total'])} | "
                f"{pct(rt['target_detected'], rt['target_total'])} | "
                f"{pct(rt['detected'] + rt['function_flagged'], rt['total'])} |"
            )
        lines.append("")
    lines += [
        "Per-specimen details and scoring rules: [AUDIT_SUMMARY.md](AUDIT_SUMMARY.md).",
        "",
        "Re-run:",
        "",
        "```bash",
        "python3 scripts/run_specimen_audits.py            # needs a mumei binary; set MUMEI_BIN",
        "                                                # or build ../mumei (cargo build)",
        "python3 scripts/run_specimen_audits.py --render-only   # re-render charts/READMEs only",
        "```",
        "",
        "The scoreboard tracks two series: audits run without an LLM provider and audits run with",
        "one. To record a with-LLM run, configure an LLM provider for mumei-agent — `LLM_API_KEY`",
        "(or `OPENAI_API_KEY`), plus `LLM_BASE_URL` / `LLM_MODEL` as needed, or a `.env` file in the",
        "agent repo — and re-run the full audit. Each mode keeps its own history entries and the",
        "tables above show the latest run of each side by side.",
    ]
    return "\n".join(lines)


def readme_block_top(history: dict) -> str:
    runs = history.get("runs") or []
    lines = [
        "## Specimen benchmark",
        "",
        "An executable corpus of deliberately broken Python/TypeScript/Go/Rust/Solidity "
        "apps with ground-truth defects, scored with `mumei-agent audit`. It includes "
        "defect classes the tools don't detect yet, so the score is expected to rise over time.",
        "",
        "![Detection by language](specimens/scoreboard/by_language.svg)",
        "",
    ]
    if not runs:
        lines += ["No benchmark runs yet — the chart fills in after the first full audit run.", ""]
    else:
        def _frag(run: dict) -> str:
            t = run["totals"]
            return (f"{t['detected']}/{t['total']} detected "
                    f"({pct(t['detected'], t['total'])}), "
                    f"{t['detected'] + t['function_flagged']}/{t['total']} "
                    f"detected or function-flagged")

        modes = latest_by_mode(runs)
        nollm = f"no LLM: {_frag(modes[False])}" if modes[False] else "no LLM: not run yet"
        llm = f"with LLM: {_frag(modes[True])}" if modes[True] else "with LLM: not run yet"
        lines += [f"Latest — {nollm} · {llm}", ""]
    lines += ["Details and history: [specimens/README.md#scoreboard](specimens/README.md#scoreboard)."]
    return "\n".join(lines)


def update_scoreboard_block(readme_path: Path, block: str) -> None:
    text = readme_path.read_text(encoding="utf-8")
    if SCOREBOARD_START not in text or SCOREBOARD_END not in text:
        raise SystemExit(f"{readme_path}: missing {SCOREBOARD_START} / {SCOREBOARD_END} markers")
    pre, rest = text.split(SCOREBOARD_START, 1)
    _, post = rest.split(SCOREBOARD_END, 1)
    readme_path.write_text(
        pre + SCOREBOARD_START + "\n" + block.rstrip() + "\n" + SCOREBOARD_END + post,
        encoding="utf-8",
    )


def render_scoreboard(scoreboard_dir: Path, specimens_readme: Path, top_readme: Path) -> dict:
    """Render history.svg / by_language.svg and rewrite both README blocks."""
    history = load_history(scoreboard_dir / "history.json")
    modes = latest_by_mode(history.get("runs") or [])
    scoreboard_dir.mkdir(parents=True, exist_ok=True)
    (scoreboard_dir / "by_language.svg").write_text(svg_by_language(modes), encoding="utf-8")
    (scoreboard_dir / "history.svg").write_text(svg_history(history.get("runs") or []),
                                                encoding="utf-8")
    update_scoreboard_block(specimens_readme, readme_block_specimens(history))
    update_scoreboard_block(top_readme, readme_block_top(history))
    return history


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
    parser.add_argument("--scoreboard-dir", default=str(SPECIMENS_ROOT / "scoreboard"))
    parser.add_argument("--specimens-readme", default=str(SPECIMENS_ROOT / "README.md"))
    parser.add_argument("--top-readme", default=str(REPO_ROOT / "README.md"))
    parser.add_argument("--render-only", action="store_true",
                        help="re-render scoreboard SVGs and README blocks from history.json "
                             "without running any audits")
    args = parser.parse_args(argv)

    if args.render_only:
        render_scoreboard(Path(args.scoreboard_dir), Path(args.specimens_readme),
                          Path(args.top_readme))
        return 0

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
    adjudications = load_adjudications(SPECIMENS_ROOT)
    dirs = [Path(d).resolve() for d in args.specimens] or discover(SPECIMENS_ROOT)
    coverages = []
    for d in dirs:
        cov = audit_specimen(d, agent_repo, mumei_bin, args.timeout, meta, adjudications)
        c = cov["counts"]
        print(f"{cov['specimen']}: {c['detected']}/{c['total']} detected, {c['function_flagged']} function-flagged, "
              f"{c['missed']} missed, {len(cov['unmatched_findings'])} unmatched")
        coverages.append(cov)
    if not args.specimens:
        write_summary(coverages, meta, Path(args.summary))
        scoreboard_dir = Path(args.scoreboard_dir)
        record_run(scoreboard_dir / "history.json",
                   history_entry(coverages, meta, corpus_info(SPECIMENS_ROOT),
                                scoring_hash(SPECIMENS_ROOT)))
        render_scoreboard(scoreboard_dir, Path(args.specimens_readme),
                          Path(args.top_readme))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
