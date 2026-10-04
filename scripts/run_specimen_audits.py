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


def aggregate(coverages: list[dict]) -> dict:
    """Totals, per-language and per-category stats over a set of coverages.

    Shared by write_summary and the history entry so numbers are computed once.
    """
    totals = {"total": 0, "detected": 0, "function_flagged": 0, "advisory_only": 0,
              "missed": 0, "target_total": 0, "target_detected": 0, "unmatched": 0}
    by_lang: dict[str, dict[str, int]] = {}
    by_cat: dict[str, dict[str, Any]] = {}
    for cov in coverages:
        c = cov["counts"]
        for k in ("total", "detected", "function_flagged", "advisory_only", "missed"):
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
                                                   "advisory_only": 0, "missed": 0,
                                                   "in_target": r["category"] in TARGET_CATEGORIES})
            bc["total"] += 1
            bc[r["status"]] += 1
    return {"totals": totals, "by_language": by_lang, "by_category": by_cat}


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
            f"{v['flagged']} ({pct(v['flagged'], v['total'])}) | "
            f"{v['target_detected']}/{v['target_total']} ({pct(v['target_detected'], v['target_total'])}) |"
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


# ---------------------------------------------------------------------------
# Benchmark history and scoreboard
# ---------------------------------------------------------------------------

SCOREBOARD_START = "<!-- scoreboard:start -->"
SCOREBOARD_END = "<!-- scoreboard:end -->"


def corpus_info(root: Path) -> dict:
    """Specimen/defect counts plus a hash of every DEFECTS.json under root."""
    h = hashlib.sha256()
    files = sorted(root.glob("*/*/DEFECTS.json"))
    defects = 0
    for f in files:
        rel = f.relative_to(root).as_posix()
        h.update(rel.encode())
        h.update(b"\0")
        data = f.read_bytes()
        h.update(data)
        h.update(b"\0")
        defects += len(json.loads(data)["defects"])
    return {"specimens": len(files), "defects": defects, "hash": h.hexdigest()}


def load_history(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema": 1, "runs": []}


def history_entry(coverages: list[dict], meta: dict, corpus: dict) -> dict:
    agg = aggregate(coverages)
    t = agg["totals"]
    return {
        "generated_at": meta["generated_at"],
        "mumei_agent_commit": meta["mumei_agent_commit"],
        "mumei_commit": meta["mumei_commit"],
        "mumei_version": meta["mumei_version"],
        "llm_configured": meta["llm_configured"],
        "corpus": corpus,
        "totals": {k: t[k] for k in ("total", "detected", "function_flagged",
                                    "advisory_only", "missed",
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
    (agent commit, mumei commit, corpus hash) is unchanged."""
    hist = load_history(history_path)
    runs = hist.setdefault("runs", [])
    key = (entry.get("mumei_agent_commit"), entry.get("mumei_commit"),
           (entry.get("corpus") or {}).get("hash"))
    if runs:
        last = runs[-1]
        last_key = (last.get("mumei_agent_commit"), last.get("mumei_commit"),
                    (last.get("corpus") or {}).get("hash"))
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


def svg_by_language(run: dict | None) -> str:
    """Grouped horizontal bars: detected % and detected-or-flagged % per language."""
    if run is None:
        return svg_placeholder()
    rows = [(lang, v["total"], v["detected"], v["flagged"])
            for lang, v in sorted(run["by_language"].items())]
    t = run["totals"]
    rows.append(("overall", t["total"], t["detected"],
                 t["detected"] + t["function_flagged"]))
    sha = (run.get("mumei_agent_commit") or "?")[:7]
    date = (run.get("generated_at") or "")[:10]

    W = 720
    label_w, bar_w, bar_h, gap, row_h = 150, 460, 15, 5, 58
    top, bottom = 78, 78
    H = top + row_h * len(rows) + bottom
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
    # x-axis: 0..100% in 25% steps
    axis_y = top + row_h * len(rows) + 6
    for step in (0, 25, 50, 75, 100):
        gx = x0 + bar_w * step / 100
        parts.append(
            f'  <line x1="{gx:.1f}" y1="{top - 4}" x2="{gx:.1f}" y2="{axis_y}" '
            f'stroke="#d0d7de" stroke-width="1"/>')
        parts.append(
            f'  <text x="{gx:.1f}" y="{axis_y + 16}" font-size="10" fill="#57606a" '
            f'text-anchor="middle">{step}%</text>')
    for i, (lang, total, det, flag) in enumerate(rows):
        y = top + i * row_h
        weight = "bold" if lang == "overall" else "normal"
        parts.append(
            f'  <text x="{x0 - 10}" y="{y + bar_h + gap // 2}" font-size="12" '
            f'font-weight="{weight}" fill="#24292f" text-anchor="end">{_esc(lang)}</text>')
        parts.append(bar(y, det, total, "#2f81f7"))
        parts.append(bar(y + bar_h + gap, flag, total, "#bf8700"))
    legend_y = axis_y + 36
    parts += [
        f'  <rect x="{x0}" y="{legend_y}" width="12" height="12" fill="#2f81f7"/>',
        f'  <text x="{x0 + 18}" y="{legend_y + 11}" font-size="11" fill="#24292f">detected</text>',
        f'  <rect x="{x0 + 110}" y="{legend_y}" width="12" height="12" fill="#bf8700"/>',
        f'  <text x="{x0 + 128}" y="{legend_y + 11}" font-size="11" fill="#24292f">'
        f'detected or function-flagged</text>',
        '</svg>',
    ]
    return "\n".join(parts) + "\n"


def svg_history(runs: list[dict]) -> str:
    """Line chart of detected %, target detected %, detected-or-flagged % per run."""
    if not runs:
        return svg_placeholder()
    W, H = 720, 340
    left, right, top, bottom = 60, 30, 60, 70
    plot_w, plot_h = W - left - right, H - top - bottom

    def xy(i: int, pct_val: float) -> tuple[float, float]:
        x = left + (plot_w * i / (len(runs) - 1) if len(runs) > 1 else plot_w / 2)
        y = top + plot_h * (1 - pct_val / 100)
        return x, y

    series = [
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
    for name, color, fn in series:
        pts = [xy(i, fn(r)) for i, r in enumerate(runs)]
        if len(pts) > 1:
            d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            parts.append(f'  <polyline points="{d}" fill="none" stroke="{color}" '
                         f'stroke-width="2"/>')
        for x, y in pts:
            parts.append(f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>')
    for i, r in enumerate(runs):
        x, _ = xy(i, 0)
        sha = (r.get("mumei_agent_commit") or "?")[:7]
        date = (r.get("generated_at") or "")[:10]
        parts.append(f'  <text x="{x:.1f}" y="{H - bottom + 18}" font-size="10" '
                     f'fill="#57606a" text-anchor="middle">'
                     f'<tspan x="{x:.1f}" dy="0">{_esc(sha)}</tspan>'
                     f'<tspan x="{x:.1f}" dy="12">{_esc(date)}</tspan></text>')
    lx = left
    for name, color, _ in series:
        parts.append(f'  <rect x="{lx}" y="{H - 20}" width="12" height="12" fill="{color}"/>')
        parts.append(f'  <text x="{lx + 18}" y="{H - 9}" font-size="11" '
                     f'fill="#24292f">{_esc(name)}</text>')
        lx += 18 + 8 * len(name) + 24
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
        latest = runs[-1]
        t = latest["totals"]
        lines += [
            f"Latest run: mumei-agent `{_sha7(latest.get('mumei_agent_commit'))}` · "
            f"mumei `{_sha7(latest.get('mumei_commit'))}` ({latest.get('mumei_version')}) · "
            f"{latest.get('generated_at')} · LLM configured: `{latest.get('llm_configured')}`",
            "",
            "| Language | Defects | Detected | Detected % | Detected or flagged % | Target detected |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for lang, v in sorted(latest["by_language"].items()):
            lines.append(
                f"| {lang} | {v['total']} | {v['detected']} | "
                f"{pct(v['detected'], v['total'])} | {pct(v['flagged'], v['total'])} | "
                f"{v['target_detected']}/{v['target_total']} |"
            )
        lines.append(
            f"| **Total** | **{t['total']}** | **{t['detected']}** | "
            f"**{pct(t['detected'], t['total'])}** | "
            f"**{pct(t['detected'] + t['function_flagged'], t['total'])}** | "
            f"**{t['target_detected']}/{t['target_total']}** |"
        )
        lines += [
            "",
            "Recent runs:",
            "",
            "| Date | mumei-agent | mumei | Defects | Detected % | Target detected % | Flagged % |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
        for r in reversed(runs[-10:]):
            rt = r["totals"]
            lines.append(
                f"| {(r.get('generated_at') or '')[:10]} | `{_sha7(r.get('mumei_agent_commit'))}` | "
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
        t = runs[-1]["totals"]
        lines += [
            f"Latest: {t['detected']}/{t['total']} defects detected "
            f"({pct(t['detected'], t['total'])}), "
            f"{t['detected'] + t['function_flagged']}/{t['total']} detected or function-flagged.",
            "",
        ]
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
    latest = history["runs"][-1] if history.get("runs") else None
    scoreboard_dir.mkdir(parents=True, exist_ok=True)
    (scoreboard_dir / "by_language.svg").write_text(svg_by_language(latest), encoding="utf-8")
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
        scoreboard_dir = Path(args.scoreboard_dir)
        record_run(scoreboard_dir / "history.json",
                   history_entry(coverages, meta, corpus_info(SPECIMENS_ROOT)))
        render_scoreboard(scoreboard_dir, Path(args.specimens_readme),
                          Path(args.top_readme))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
