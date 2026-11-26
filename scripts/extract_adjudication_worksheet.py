#!/usr/bin/env python3
"""Extract unreviewed and stale specimen-audit findings into a human-review worksheet."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_specimen_audits as rsa  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_coverages(specimens_root: Path, llm: bool) -> tuple[list[dict], list[str]]:
    coverages = []
    missing = []
    for specimen_dir in rsa.discover(specimens_root):
        path = rsa.audit_dir(specimen_dir, llm) / "coverage.json"
        if path.is_file():
            coverages.append(json.loads(path.read_text(encoding="utf-8")))
        else:
            missing.append(str(specimen_dir.relative_to(specimens_root)))
    return coverages, missing


def finding_key(specimen: str, rec: dict) -> tuple[str, str, str]:
    return (specimen, rec["file"], rec["text"])


def unreviewed_groups(coverages: list[dict]) -> list[dict]:
    groups = {}
    for cov in coverages:
        specimen = cov["specimen"]
        for variant, records in (("buggy", cov.get("findings") or []),
                                 ("fixed", (cov.get("fixed") or {}).get("findings") or [])):
            for rec in records:
                if rec.get("status") != "unreviewed":
                    continue
                key = finding_key(specimen, rec)
                group = groups.setdefault(key, {
                    "specimen": specimen,
                    "language": cov["language"],
                    "file": rec["file"],
                    "kinds": set(),
                    "text": rec["text"],
                    "variants": set(),
                    "occurrence_counts": defaultdict(int),
                })
                group["variants"].add(variant)
                group["kinds"].add(rec["kind"])
                group["occurrence_counts"][variant] += 1
    return [dict(g, variants=sorted(g["variants"]), kinds=sorted(g["kinds"]),
                 occurrence_counts=dict(g["occurrence_counts"])) for _, g in sorted(groups.items())]


def fence(text: str, language: str = "text") -> str:
    marker = "````" if "```" in text else "```"
    return f"{marker}{language}\n{text}\n{marker}"


def worksheet_link(label: str, target: Path, link_root: Path) -> str:
    rel = Path(os.path.relpath(target, link_root))
    return f"[{label}]({rel.as_posix()})"


def used_review_keys(coverages: list[dict]) -> set[tuple[str, str, str]]:
    return {tuple(key) for cov in coverages
            for key in (cov.get("reviews_used") or []) + ((cov.get("fixed") or {}).get("reviews_used") or [])}


def meta_lines(coverages: list[dict]) -> list[str]:
    metas = sorted({json.dumps(cov.get("meta") or {}, sort_keys=True) for cov in coverages})
    lines = []
    if len(metas) != 1:
        lines.append("- **Warning:** coverage files come from mixed audit runs; regenerate one full audit before adjudicating.")
    for raw in metas:
        meta = json.loads(raw)
        parts = []
        if meta.get("generated_at"):
            parts.append(f"generated `{meta['generated_at']}`")
        if meta.get("rescored_at"):
            parts.append(f"rescored `{meta['rescored_at']}`")
        if meta.get("mumei_agent_commit"):
            parts.append(f"mumei-agent `{str(meta['mumei_agent_commit'])[:7]}`")
        if meta.get("mumei_commit"):
            parts.append(f"mumei `{str(meta['mumei_commit'])[:7]}`")
        if meta.get("llm_model"):
            parts.append(f"model `{meta['llm_model']}`")
        lines.append("- " + (", ".join(parts) if parts else "provenance metadata missing"))
    return lines


def review_entry(item: dict) -> str:
    entry = {
        "specimen": item["specimen"],
        "file": item["file"],
        "finding_contains": item["text"],
        "verdict": "TODO(real or false_positive)",
        "reason": "TODO: state what behavior makes this a real issue or why it is not one",
    }
    return json.dumps(entry, ensure_ascii=False, indent=2)


def render(coverages: list[dict], finding_reviews: list[dict], specimens_root: Path,
           llm: bool, generated_by: str, include_audit_links: bool, link_root: Path,
           other_coverages: list[dict]) -> str:
    mode = "with LLM" if llm else "no LLM"
    stale = rsa.stale_reviews(coverages, finding_reviews)
    groups = unreviewed_groups(coverages)
    occurrences = sum(sum(g["occurrence_counts"].values()) for g in groups)
    variant_occurrences = {
        variant: sum(g["occurrence_counts"].get(variant, 0) for g in groups)
        for variant in ("buggy", "fixed")
    }
    other_used = used_review_keys(other_coverages)
    other_checked = bool(other_coverages)
    by_specimen_file = defaultdict(list)
    for i, g in enumerate(groups):
        by_specimen_file[(g["specimen"], g["file"])].append(f"U{i + 1}")

    lines = [
        "# Specimen adjudication worksheet",
        "",
        f"Generated by `{generated_by}`. Do not edit this worksheet to record verdicts;",
        "update `specimens/scoreboard/adjudications.json` instead.",
        "",
        f"Source: `{mode}` `coverage.json` files under `specimens/`.",
        f"Unreviewed review keys: **{len(groups)}** covering **{occurrences}** buggy/fixed finding occurrence(s).",
        f"Occurrences by variant: buggy **{variant_occurrences['buggy']}**, fixed **{variant_occurrences['fixed']}**.",
        "One review key can cover both variants and repeated occurrences of the same specimen/file/finding text.",
        f"Stale prior reviews: **{len(stale)}**.",
        "",
        "## Audit provenance",
        "",
        *meta_lines(coverages),
        "",
        "## How to adjudicate",
        "",
        "For every `U` item, inspect the finding text below, the linked buggy source, and the fixed patch when present (plus the audit output when available). Then copy its JSON template into the",
        "`finding_reviews` array in `specimens/scoreboard/adjudications.json`, replace the TODO fields, and shorten",
        "`finding_contains` only when the shorter text still uniquely matches the intended finding. Use `real` when the finding points",
        "at a real problem, otherwise `false_positive`. Preserve the double quotes required by JSON.",
        "",
        "For every `S` item, first check whether it still matches the other audit mode; if it does, keep it unchanged. Otherwise either",
        "update `finding_contains` to match the same finding's current wording, or remove it only when it is emitted in neither mode.",
        "Do not mark the worksheet itself complete; completeness is measured by `--rescore`.",
        "",
        "When every item is handled, run `python3 scripts/run_specimen_audits.py --rescore` in the checkout containing the new audit output.",
        "",
        "## Unreviewed findings",
        "",
    ]
    if not groups:
        lines += ["No unreviewed findings.", ""]
    for i, item in enumerate(groups, 1):
        uid = f"U{i}"
        specimen_dir = specimens_root / item["language"] / item["specimen"]
        source = specimen_dir / item["file"]
        audit = rsa.audit_dir(specimen_dir, llm) / "audit.md"
        fixed_audit = rsa.audit_dir(specimen_dir, llm) / "fixed" / "audit.md"
        patch = specimen_dir / rsa.FIXED_PATCH
        links = []
        if include_audit_links and audit.is_file():
            links.append(worksheet_link("audit", audit, link_root))
        if include_audit_links and "fixed" in item["variants"] and fixed_audit.is_file():
            links.append(worksheet_link("fixed audit", fixed_audit, link_root))
        if source.is_file():
            links.append(worksheet_link("buggy source", source, link_root))
        if "fixed" in item["variants"] and patch.is_file():
            links.append(worksheet_link("fixed patch", patch, link_root))
        kinds = "`, `".join(item["kinds"])
        variants = ", ".join(item["variants"])
        lines += [
            f"### {uid} — `{item['specimen']}` / `{item['file']}`",
            "",
            f"- Language: `{item['language']}`; kind(s): `{kinds}`; observed in: {variants}",
            f"- Evidence: {', '.join(links) if links else 'not available'}",
            "- Finding:",
            "",
            fence(item["text"]),
            "",
            "- Review entry template:",
            "",
            fence(review_entry(item), "json"),
            "",
        ]

    lines += ["## Stale prior reviews", ""]
    if not stale:
        lines += ["No stale prior reviews.", ""]
    for i, review in enumerate(stale, 1):
        key = (review["specimen"], review["file"])
        related = ", ".join(by_specimen_file.get(key, [])) or "none in this worksheet"
        if rsa.review_key(review) in other_used:
            other_state = "matched; keep this review"
        elif other_checked:
            other_state = "not matched in the available other-mode coverage"
        else:
            other_state = "not checked (other-mode coverage unavailable)"
        lines += [
            f"### S{i} — `{review['specimen']}` / `{review['file']}`",
            "",
            f"- Prior verdict: `{review['verdict']}`",
            f"- Prior reason: {review['reason']}",
            f"- Other audit mode: {other_state}",
            f"- Possibly related unreviewed finding(s): {related}",
            "- Prior `finding_contains`:",
            "",
            fence(review["finding_contains"]),
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--specimens-root", default=str(REPO_ROOT / "specimens"),
                        help="specimens root containing language/specimen directories")
    parser.add_argument("--output", default=None,
                        help="worksheet path (default: ADJUDICATION_WORKSHEET.md under the specimens root, or ADJUDICATION_WORKSHEET_WITH_LLM.md with --llm)")
    parser.add_argument("--llm", action="store_true", help="read audit/with-llm coverage instead of no-LLM coverage")
    parser.add_argument("--include-audit-links", action="store_true",
                        help="link audit markdown in addition to source files (use when those outputs are committed or local)")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    specimens_root = Path(args.specimens_root).resolve()
    coverages, missing = load_coverages(specimens_root, args.llm)
    if missing:
        raise SystemExit(f"missing coverage.json for {len(missing)} specimen(s); first missing: {missing[0]}")
    finding_reviews = rsa.load_finding_reviews(specimens_root)
    generated_by = "scripts/extract_adjudication_worksheet.py"
    default_name = "ADJUDICATION_WORKSHEET_WITH_LLM.md" if args.llm else "ADJUDICATION_WORKSHEET.md"
    output = Path(args.output).resolve() if args.output else specimens_root / default_name
    other_coverages, _ = load_coverages(specimens_root, not args.llm)
    text = render(coverages, finding_reviews, specimens_root, args.llm, generated_by,
                  args.include_audit_links, output.parent, other_coverages)
    output.write_text(text, encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
