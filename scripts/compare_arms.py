#!/usr/bin/env python3
"""Compare three ways of reviewing the specimen corpus side by side.

- mumei only: `mumei-agent audit` with no LLM provider (audit/coverage.json)
- mumei + LLM: the same audit with an LLM provider (audit/with-llm/coverage.json)
- LLM only: the model reviews the source on its own (llm_only/<model>.json,
  written by scripts/run_llm_only.py)

All three are scored against the same DEFECTS.json ground truth, so the
counts line up. This script reads committed output only; it calls no model
and runs no audit. It writes specimens/scoreboard/arms.{json,svg},
specimens/COMPARISON.md and the comparison block of the top-level README.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_llm_only as rlo  # noqa: E402
import run_specimen_audits as rsa  # noqa: E402

COMPARISON_START = "<!-- comparison:start -->"
COMPARISON_END = "<!-- comparison:end -->"
ARMS = ("mumei", "mumei+llm", "llm")
ARM_LABEL = {"mumei": "mumei only", "mumei+llm": "mumei + LLM", "llm": "LLM only"}
ARM_COLOR = {"mumei": "#2f81f7", "mumei+llm": "#8250df", "llm": "#1a7f37"}
KIND_LABEL = {
    "verification_violations": "Verifier violations",
    "cross_validation_gaps": "Spec vs code cross-check gaps",
    "spec_health_issues": "Spec health issues",
    "trusted_atoms": "Trusted atoms",
}
VERIFIER_KIND = "verification_violations"


def _sum_findings(parts: list[dict]) -> dict:
    keys = ("total", "defect_evidence", "real", "false_positive", "unreviewed")
    return {k: sum(p.get(k, 0) for p in parts) for k in keys}


def _detected(defects: list[dict], statuses=("detected",)) -> set[tuple[str, str]]:
    return {(d["specimen"], d["id"]) for d in defects if d["status"] in statuses}


def load_audit_arm(specimens: list[Path], llm: bool) -> dict | None:
    """Per-defect results of one audit mode, or None when any specimen lacks it."""
    covs = []
    for d in specimens:
        path = rsa.audit_dir(d, llm) / "coverage.json"
        if not path.is_file():
            return None
        cov = json.loads(path.read_text(encoding="utf-8"))
        if cov.get("source_hash") is not None and cov["source_hash"] != rsa.specimen_hash(d):
            raise SystemExit(f"{d.name}: specimen changed since the {'with-LLM' if llm else 'no-LLM'} "
                             "audit; run scripts/run_specimen_audits.py again")
        covs.append(cov)
    metas = {json.dumps(c["meta"], sort_keys=True) for c in covs}
    if len(metas) != 1:
        raise SystemExit(f"{'with-LLM' if llm else 'no-LLM'} audit output comes from different runs")
    defects = [dict(df, specimen=c["specimen"], language=c["language"]) for c in covs for df in c["defects"]]
    fixed = [c["fixed"] for c in covs if c.get("fixed")]
    return {
        "meta": covs[0]["meta"],
        "defects": defects,
        "kinds": _audit_kinds(specimens, covs, llm),
        "runs": [{
            "detected": _detected(defects),
            "flagged": _detected(defects, ("detected", "function_flagged")),
            "findings": _sum_findings([c["finding_counts"] for c in covs]),
            "fixed_false_alarms": sum(f["false_alarms"] for f in fixed),
        }],
        "fixed_specimens": len(fixed),
    }


def _kind_counts(findings) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in findings:
        if not rsa.is_supporting(f):
            out[f["kind"]] = out.get(f["kind"], 0) + 1
    return dict(sorted(out.items()))


def _audit_kinds(specimens: list[Path], covs: list[dict], llm: bool) -> dict:
    """Findings per audit finding kind on the buggy code and, when every
    specimen with a fixed.patch kept its fixed-variant audit.json, on the fixed code."""
    buggy = _kind_counts(f for c in covs for f in c.get("findings") or [])
    with_patch = [d for d in specimens if (d / rsa.FIXED_PATCH).is_file()]
    if not with_patch:
        return {"buggy": buggy, "fixed": None}
    fixed_findings = []
    for d in with_patch:
        path = rsa.audit_dir(d, llm) / "fixed" / "audit.json"
        if not path.is_file():
            return {"buggy": buggy, "fixed": None}
        audit = json.loads(path.read_text(encoding="utf-8"))
        label = str(d.relative_to(rsa.REPO_ROOT))
        fixed_findings += [f for fs in rsa.findings_by_file(audit, label).values() for f in fs]
    return {"buggy": buggy, "fixed": _kind_counts(fixed_findings)}


def load_llm_arm(specimens: list[Path], model: str) -> dict | None:
    recs = []
    for d in specimens:
        path = rlo.record_path(d, model)
        if not path.is_file():
            return None
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("source_hash") is not None and rec["source_hash"] != rlo.rb.baseline_hash(d):
            raise SystemExit(f"{d.name}: specimen changed since the LLM-only review; "
                             "run scripts/run_llm_only.py again")
        recs.append(rec)
    numbers = sorted({r["run"] for rec in recs for r in rec["runs"]})
    runs, usage = [], []
    for n in numbers:
        parts = [(rec, next((r for r in rec["runs"] if r["run"] == n), None)) for rec in recs]
        if any(r is None for _, r in parts):
            raise SystemExit(f"LLM-only run {n} is missing for some specimens; re-run scripts/run_llm_only.py")
        defects = [dict(df, specimen=rec["specimen"], language=rec["language"])
                   for rec, r in parts for df in r["defects"]]
        runs.append({
            "run": n,
            "defects": defects,
            "detected": _detected(defects),
            "flagged": _detected(defects, ("detected", "function_flagged")),
            "findings": _sum_findings([r["finding_counts"] for _, r in parts]),
            "fixed_false_alarms": sum(r["fixed"]["false_alarms"] for _, r in parts if r.get("fixed")),
        })
        calls = [u for _, r in parts for u in (r.get("usage"), r.get("fixed_usage")) if u]
        usage.append({"seconds": round(sum(u.get("seconds", 0) for u in calls), 1),
                      "cost_usd": round(sum(u.get("cost_usd") or 0 for u in calls), 6),
                      "cost_unknown_calls": sum(1 for u in calls if u.get("cost_usd") is None)})
    return {
        "meta": {k: recs[0][k] for k in ("model", "prompt_version", "prompt_hash", "temperature")},
        "defects": runs[0]["defects"] if runs else [],
        "runs": runs,
        "usage": usage,
        "fixed_specimens": sum(1 for rec in recs if rec["runs"] and rec["runs"][0].get("fixed")),
    }


def _spread(values: list[int]) -> dict:
    return {"min": min(values), "median": statistics.median(values), "max": max(values)}


def summarize(arms: dict[str, dict | None], history: dict, total: int,
              by_language_totals: dict[str, int]) -> dict:
    latest = rsa.latest_by_mode(history.get("runs") or [])
    out: dict = {"defects": total, "arms": {}}
    for name in ARMS:
        arm = arms.get(name)
        if arm is None:
            out["arms"][name] = None
            continue
        runs = arm["runs"]
        detected = [len(r["detected"]) for r in runs]
        flagged = [len(r["flagged"]) for r in runs]
        fixed = [r["fixed_false_alarms"] for r in runs]
        precision = [rsa.precision_range(r["findings"]) for r in runs]
        langs = {}
        for lang in sorted(by_language_totals):
            per_run = [sum(1 for s, i in r["detected"] if (s, i) in arm["_lang"][lang]) for r in runs]
            langs[lang] = _spread(per_run)
        entry = {
            "runs": len(runs),
            "detected": _spread(detected),
            "detected_or_flagged": _spread(flagged),
            "detected_in_any_run": len(set().union(*(r["detected"] for r in runs))),
            "detected_in_every_run": len(set.intersection(*(r["detected"] for r in runs))),
            "findings": _spread([r["findings"]["total"] for r in runs]),
            "unreviewed": _spread([r["findings"]["unreviewed"] for r in runs]),
            "precision": [list(p) if p else None for p in precision],
            "fixed_false_alarms": _spread(fixed),
            "fixed_specimens": arm["fixed_specimens"],
            "by_language": langs,
            "meta": arm["meta"],
        }
        if name == "llm":
            entry["cost_usd"] = round(sum(u["cost_usd"] for u in arm["usage"]) / len(arm["usage"]), 6)
            entry["seconds"] = round(sum(u["seconds"] for u in arm["usage"]) / len(arm["usage"]), 1)
            entry["cost_unknown_calls"] = sum(u["cost_unknown_calls"] for u in arm["usage"])
        else:
            run = _history_run(history, latest, name == "mumei+llm", arm["meta"])
            entry["cost_usd"] = run.get("llm_cost_usd", 0.0 if name == "mumei" else None)
            entry["seconds"] = run.get("audit_seconds")
            entry["findings_by_kind"] = arm["kinds"]
        out["arms"][name] = entry
    sets = {name: (set().union(*(r["detected"] for r in arms[name]["runs"])) if arms.get(name) else None)
            for name in ARMS}
    out["overlap"] = overlap(sets)
    return out


def _history_run(history: dict, latest: dict, llm: bool, meta: dict) -> dict:
    """The history entry of the audit run the coverage files come from, or {}
    when history has no such run. Older coverage without a timestamp falls back
    to the newest run of the same mode."""
    stamp = meta.get("generated_at")
    if stamp is None:
        return latest[llm] or {}
    return next((r for r in reversed(history.get("runs") or [])
                 if rsa.entry_llm(r) == llm and r.get("generated_at") == stamp), {})


def overlap(sets: dict[str, set | None]) -> list[dict]:
    """Pairwise complementarity: what each side finds that the other misses."""
    rows = []
    for a, b in (("mumei", "llm"), ("mumei+llm", "llm"), ("mumei", "mumei+llm")):
        if sets.get(a) is None or sets.get(b) is None:
            continue
        sa, sb = sets[a], sets[b]
        rows.append({"a": a, "b": b, "both": len(sa & sb), "only_a": len(sa - sb),
                     "only_b": len(sb - sa), "union": len(sa | sb)})
    return rows


def _fmt_spread(s: dict | None, runs: int, total: int | None = None) -> str:
    if s is None:
        return "—"
    med = s["median"]
    med_s = f"{med:g}"
    tail = f" ({100 * med / total:.0f}%)" if total else ""
    if runs > 1 and s["min"] != s["max"]:
        return f"{med_s}{tail}, range {s['min']}–{s['max']}"
    return f"{med_s}{tail}"


def _fmt_precision_runs(ranges: list[list[float] | None]) -> str:
    vals = [r for r in ranges if r]
    if not vals:
        return "—"
    lo = statistics.median(r[0] for r in vals)
    hi = statistics.median(r[1] for r in vals)
    a, b = f"{100 * lo:.0f}%", f"{100 * hi:.0f}%"
    return a if a == b else f"{a}–{b}"


def _fmt_cost(entry: dict) -> str:
    cost = entry.get("cost_usd")
    if cost is None or (entry.get("cost_unknown_calls") and not cost):
        return "unknown"
    text = f"${cost:.2f}" if cost >= 0.01 or cost == 0 else f"${cost:.4f}"
    return f"≥ {text}" if entry.get("cost_unknown_calls") else text


def _fmt_seconds(entry: dict, model_time: bool = False) -> str:
    s = entry.get("seconds")
    if s is None:
        return "—"
    text = f"{s / 60:.0f} min" if s >= 120 else f"{s:.0f} s"
    return text + (" model time" if model_time else " wall")


def table_lines(summary: dict) -> list[str]:
    total = summary["defects"]
    lines = [
        "| | Detected | Detected or flagged | Precision | False alarms on fixed code | Cost per pass | Time per pass |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ARMS:
        e = summary["arms"].get(name)
        if e is None:
            lines.append(f"| {ARM_LABEL[name]} | not run yet | | | | | |")
            continue
        n = e["runs"]
        label = ARM_LABEL[name] + (f" ({n} runs, median)" if n > 1 else "")
        lines.append(
            f"| {label} | {_fmt_spread(e['detected'], n, total)} | "
            f"{_fmt_spread(e['detected_or_flagged'], n, total)} | {_fmt_precision_runs(e['precision'])} | "
            f"{_fmt_spread(e['fixed_false_alarms'], n)} | {_fmt_cost(e)} | {_fmt_seconds(e, name == 'llm')} |")
    return lines


def overlap_lines(summary: dict) -> list[str]:
    if not summary["overlap"]:
        return []
    lines = ["| Pair | Both | Only first | Only second | Either |", "|---|---:|---:|---:|---:|"]
    for o in summary["overlap"]:
        lines.append(f"| {ARM_LABEL[o['a']]} vs {ARM_LABEL[o['b']]} | {o['both']} | {o['only_a']} | "
                     f"{o['only_b']} | {o['union']} |")
    return lines


def _model(summary: dict) -> str | None:
    for name in ("llm", "mumei+llm"):
        e = summary["arms"].get(name)
        if e:
            return e["meta"].get("model") or e["meta"].get("llm_model")
    return None


def kind_lines(summary: dict) -> list[str]:
    present = [n for n in ("mumei", "mumei+llm") if summary["arms"].get(n)]
    if not present:
        return []
    kinds = sorted({k for n in present for side in ("buggy", "fixed")
                    for k in (summary["arms"][n]["findings_by_kind"][side] or {})},
                   key=lambda k: (list(KIND_LABEL).index(k) if k in KIND_LABEL else len(KIND_LABEL), k))
    if not kinds:
        return []
    head = " | ".join(f"{ARM_LABEL[n]}: buggy | {ARM_LABEL[n]}: fixed" for n in present)
    lines = [f"| Kind | {head} |", "|---|" + "---:|" * (2 * len(present))]

    def cell(n, side, k):
        counts = summary["arms"][n]["findings_by_kind"][side]
        return "—" if counts is None else str(counts.get(k, 0))

    for k in kinds:
        cells = " | ".join(f"{cell(n, 'buggy', k)} | {cell(n, 'fixed', k)}" for n in present)
        lines.append(f"| {KIND_LABEL.get(k, k)} | {cells} |")
    return lines


def _spec_note(summary: dict) -> str | None:
    """One line on how many with-LLM findings on fixed code are spec diagnostics."""
    arm = summary["arms"].get("mumei+llm")
    fixed = arm and arm["findings_by_kind"]["fixed"]
    if not fixed:
        return None
    total = sum(fixed.values())
    other = total - fixed.get(VERIFIER_KIND, 0)
    if not other:
        return None
    return (f"Of the {total} mumei + LLM findings on fixed code, {other} are spec diagnostics "
            f"(cross-check gaps and spec health issues) rather than verifier violations.")


def readme_block(summary: dict) -> str:
    model = _model(summary)
    lines = [
        "### mumei only vs mumei + LLM vs LLM only",
        "",
        "![mumei only vs mumei + LLM vs LLM only](specimens/scoreboard/arms.svg)",
        "",
    ]
    if all(summary["arms"].get(n) is None for n in ARMS):
        return "\n".join(lines + ["No comparison yet — run the audits and `scripts/run_llm_only.py` first."])
    lines += table_lines(summary)
    lines += [
        "",
        f"Same {summary['defects']} planted defects and the same scoring for every row"
        + (f"; the model is `{model}` for both LLM rows." if model else "."),
    ]
    pending = [f"{ARM_LABEL[n]} {summary['arms'][n]['unreviewed']['median']:g}" for n in ARMS
               if summary["arms"].get(n) and summary["arms"][n].get("unreviewed", {}).get("median")]
    if pending:
        lines.append("Precision is a range while findings are unreviewed (median unreviewed per run: "
                     + ", ".join(pending) + ").")
    note = _spec_note(summary)
    if note:
        lines.append(note)
    lines.append("Details, complementarity, findings by kind and per-language numbers: "
                 "[specimens/COMPARISON.md](specimens/COMPARISON.md).")
    return "\n".join(lines)


def report(summary: dict) -> str:
    model = _model(summary)
    lines = [
        "# mumei only vs mumei + LLM vs LLM only",
        "",
        "Generated by `scripts/compare_arms.py` from committed output; it calls no model.",
        "",
        "- **mumei only**: `mumei-agent audit` without an LLM provider (`audit/`).",
        "- **mumei + LLM**: the same audit with an LLM provider configured (`audit/with-llm/`).",
        "- **LLM only**: the model reviews each specimen's source on its own, with no mumei "
        "(`llm_only/`, see [LLM_ONLY.md](LLM_ONLY.md)).",
        "",
        f"Every row is scored against the same {summary['defects']} defects in `DEFECTS.json` with the "
        "same matcher. LLM-only rows run the model several times at temperature 0 and report the median "
        "with the min–max range, because the output still varies between runs.",
        "",
    ]
    if model:
        lines += [f"Model for both LLM rows: `{model}`.", ""]
    lines += ["## Totals", ""] + table_lines(summary) + [""]
    lines += [
        "Precision is (defect evidence + findings reviewed as real) / findings, a range while findings "
        "are unreviewed. False alarms on fixed code count findings on the specimens with their "
        "`fixed.patch` applied. Cost per pass is the OpenRouter spend for one pass over the corpus "
        "(buggy and fixed code). Time per pass is the audit wall time for the mumei rows and the summed "
        "model response time for LLM only, so the two are not directly comparable.",
        "",
    ]
    ov = overlap_lines(summary)
    if ov:
        lines += ["## Complementarity", "",
                  "Defects detected, counting an LLM-only defect when any run found it.", ""] + ov + [""]
    kl = kind_lines(summary)
    if kl:
        lines += ["## mumei findings by kind", "",
                  "Findings of the two audit rows by the audit section they come from, on the buggy code "
                  "and on the fixed code. Verifier violations come from Z3 and the smart-contract checks; "
                  "the other kinds report on the extracted spec itself.", ""] + kl + [""]
        note = _spec_note(summary)
        if note:
            lines += [note, ""]
    langs = sorted({lang for e in summary["arms"].values() if e for lang in e["by_language"]})
    if langs:
        present = [n for n in ARMS if summary["arms"].get(n)]
        lines += ["## Detected by language", "",
                  "| Language | Defects | " + " | ".join(ARM_LABEL[n] for n in present) + " |",
                  "|---|---:|" + "---:|" * len(present)]
        for lang in langs:
            cells = [_fmt_spread(summary["arms"][n]["by_language"].get(lang), summary["arms"][n]["runs"])
                     for n in present]
            lines.append(f"| {lang} | {summary['by_language_totals'][lang]} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["## Re-run", "", "```bash",
              "python3 scripts/run_specimen_audits.py                 # mumei only (no LLM provider set)",
              "LLM_API_KEY=... LLM_BASE_URL=... LLM_MODEL=... \\",
              "  python3 scripts/run_specimen_audits.py               # mumei + LLM",
              "LLM_API_KEY=... LLM_BASE_URL=... LLM_MODEL=... \\",
              "  python3 scripts/run_llm_only.py                      # LLM only",
              "python3 scripts/compare_arms.py --model <model>        # this report and the README chart",
              "```", ""]
    return "\n".join(lines)


def svg(summary: dict) -> str:
    present = [n for n in ARMS if summary["arms"].get(n)]
    if not present:
        return rsa.svg_placeholder("No comparison yet")
    total = summary["defects"]
    W, label_w, bar_w, bar_h = 720, 150, 400, 18
    panels = [("Detected", "detected", total), ("Detected or flagged", "detected_or_flagged", total),
              ("False alarms on fixed code", "fixed_false_alarms", None)]
    fa_max = max(summary["arms"][n]["fixed_false_alarms"]["max"] for n in present) or 1
    row_h = bar_h + 6
    panel_h = 26 + row_h * len(present) + 10
    top = 56
    H = top + panel_h * len(panels) + 30
    model = _model(summary)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif">',
           f'  <rect width="{W}" height="{H}" fill="white"/>',
           f'  <text x="16" y="26" font-size="16" font-weight="bold" fill="#24292f">'
           f'mumei only vs mumei + LLM vs LLM only — {total} planted defects</text>',
           f'  <text x="16" y="44" font-size="12" fill="#57606a">'
           f'{rsa._esc(f"LLM rows: {model}; " if model else "")}LLM only: median of '
           f'{summary["arms"]["llm"]["runs"] if summary["arms"].get("llm") else 0} runs, whisker = min–max</text>']
    y = top
    for title, key, denom in panels:
        out.append(f'  <text x="16" y="{y + 16}" font-size="13" font-weight="bold" fill="#24292f">{rsa._esc(title)}</text>')
        y += 26
        scale = denom or fa_max
        for name in present:
            e = summary["arms"][name]
            s = e[key]
            w = bar_w * s["median"] / scale
            out.append(f'  <text x="{label_w - 8}" y="{y + 13}" font-size="12" fill="#24292f" '
                       f'text-anchor="end">{ARM_LABEL[name]}</text>')
            out.append(f'  <rect x="{label_w}" y="{y}" width="{bar_w}" height="{bar_h}" fill="#f6f8fa"/>')
            out.append(f'  <rect x="{label_w}" y="{y}" width="{w:.1f}" height="{bar_h}" fill="{ARM_COLOR[name]}"/>')
            if s["min"] != s["max"]:
                x1, x2 = label_w + bar_w * s["min"] / scale, label_w + bar_w * s["max"] / scale
                cy = y + bar_h / 2
                out.append(f'  <line x1="{x1:.1f}" y1="{cy}" x2="{x2:.1f}" y2="{cy}" stroke="#24292f" stroke-width="1.5"/>')
                for x in (x1, x2):
                    out.append(f'  <line x1="{x:.1f}" y1="{y + 4}" x2="{x:.1f}" y2="{y + bar_h - 4}" '
                               f'stroke="#24292f" stroke-width="1.5"/>')
            text = f"{s['median']:g}" + (f" ({100 * s['median'] / denom:.0f}%)" if denom else "")
            if s["min"] != s["max"]:
                text += f" [{s['min']}–{s['max']}]"
            out.append(f'  <text x="{label_w + bar_w + 8}" y="{y + 13}" font-size="12" fill="#24292f">{text}</text>')
            y += row_h
        y += 10
    out.append(f'  <text x="16" y="{H - 10}" font-size="11" fill="#57606a">'
               'Detected: a finding names the defect\'s function and its weakness. '
               'Flagged: the function only. Lower is better for false alarms.</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def update_block(readme: Path, block: str) -> None:
    text = readme.read_text(encoding="utf-8")
    start, end = text.find(COMPARISON_START), text.find(COMPARISON_END)
    if start < 0 or end < start:
        raise SystemExit(f"{readme}: missing {COMPARISON_START} / {COMPARISON_END} markers")
    new = text[:start + len(COMPARISON_START)] + "\n" + block + "\n" + text[end:]
    readme.write_text(new, encoding="utf-8")


def build(root: Path, model: str) -> dict:
    specimens = rsa.discover(root)
    if not specimens:
        raise SystemExit(f"no specimens under {root}")
    arms = {"mumei": load_audit_arm(specimens, False), "mumei+llm": load_audit_arm(specimens, True),
            "llm": load_llm_arm(specimens, model)}
    docs = [json.loads((d / "DEFECTS.json").read_text(encoding="utf-8")) for d in specimens]
    lang_of = {}
    for doc in docs:
        for df in doc["defects"]:
            lang_of[(doc["specimen"], df["id"])] = doc["language"]
    by_language_totals: dict[str, int] = {}
    for lang in lang_of.values():
        by_language_totals[lang] = by_language_totals.get(lang, 0) + 1
    lang_sets = {lang: {k for k, v in lang_of.items() if v == lang} for lang in by_language_totals}
    audit_model = (arms["mumei+llm"] or {}).get("meta", {}).get("llm_model")
    if arms["llm"] is not None and audit_model and audit_model != model:
        raise SystemExit(f"the mumei + LLM audit used {audit_model} but --model is {model}; "
                         "compare LLM-only records of the same model")
    for arm in arms.values():
        if arm is not None:
            arm["_lang"] = lang_sets
    history = rsa.load_history(root / "scoreboard" / "history.json")
    summary = summarize(arms, history, len(lang_of), by_language_totals)
    summary["by_language_totals"] = dict(sorted(by_language_totals.items()))
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model", default=None,
                   help="model whose LLM-only records to compare (default: $LLM_MODEL or the "
                        "run_llm_only.py default)")
    p.add_argument("--check", action="store_true",
                   help="fail if the committed comparison files are out of date instead of writing them")
    return p


def main(argv: list[str]) -> int:
    import os
    args = build_parser().parse_args(argv)
    model = args.model or os.environ.get("LLM_MODEL") or rlo.DEFAULT_MODEL
    root = rsa.SPECIMENS_ROOT
    summary = build(root, model)
    outputs = {
        root / "scoreboard" / "arms.json": json.dumps(summary, indent=2, sort_keys=True) + "\n",
        root / "scoreboard" / "arms.svg": svg(summary),
        root / "COMPARISON.md": report(summary),
    }
    readme = rsa.REPO_ROOT / "README.md"
    if args.check:
        stale = [p for p, text in outputs.items() if not p.is_file() or p.read_text(encoding="utf-8") != text]
        current = readme.read_text(encoding="utf-8")
        tmp = current
        s, e = tmp.find(COMPARISON_START), tmp.find(COMPARISON_END)
        if s < 0 or e < s or tmp[s + len(COMPARISON_START):e] != "\n" + readme_block(summary) + "\n":
            stale.append(readme)
        for p in stale:
            print(f"{p} is out of date; run scripts/compare_arms.py", file=sys.stderr)
        return 1 if stale else 0
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    update_block(readme, readme_block(summary))
    for name in ARMS:
        e = summary["arms"][name]
        print(f"{ARM_LABEL[name]}: " + ("not run yet" if e is None else
              f"detected {_fmt_spread(e['detected'], e['runs'], summary['defects'])}, "
              f"fixed false alarms {_fmt_spread(e['fixed_false_alarms'], e['runs'])}"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
