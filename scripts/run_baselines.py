#!/usr/bin/env python3
"""Run off-the-shelf static analyzers over the specimens and score them like the audit.

Each baseline tool runs on the same inputs as `mumei-agent audit`: a scratch
copy of the git-tracked specimen files (fixed.patch excluded), and again with
fixed.patch applied when the specimen has one. For every specimen and tool
this writes specimens/<language>/<id>/baselines/<tool>.json with the
normalized findings and their scoring, and it writes the corpus totals to
specimens/scoreboard/baselines.json and specimens/BASELINES.md.

Matching mirrors run_specimen_audits.py. A finding belongs to a defect when it
is in the defect's file and either sits inside the defect's function (the
nearest enclosing definition) or within LINE_SLACK lines of the defect's
line. It is `detected` when it also points at the defect's category: the same
CWE (or one in the same CWE_EQUIVALENTS group), or a category keyword in the
rule id or message. Findings are classified for precision the same way, with
reviewed verdicts from scoreboard/baseline_reviews.json.

Tools and rule sets are pinned (see scripts/setup_baselines.sh); a run with a
different version or rules commit is refused so totals stay comparable.
`--rescore` re-scores the committed findings without running any tool.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

_SPEC = importlib.util.spec_from_file_location(
    "run_specimen_audits", Path(__file__).resolve().parent / "run_specimen_audits.py")
rsa = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("run_specimen_audits", rsa)
_SPEC.loader.exec_module(rsa)

REPO_ROOT = rsa.REPO_ROOT
SPECIMENS_ROOT = rsa.SPECIMENS_ROOT
CACHE_DIR = REPO_ROOT / ".cache" / "baselines"
REVIEWS_FILE = "baseline_reviews.json"
LINE_SLACK = 3

SEMGREP_VERSION = "1.150.0"
BANDIT_VERSION = "1.8.6"
SEMGREP_RULES_COMMIT = "16b9e6d45f10649f6a531ec4838ed9924372c3bc"
# semgrep-rules directories per specimen language.
SEMGREP_CONFIGS = {
    "python": ["python"],
    "typescript": ["typescript", "javascript"],
    "go": ["go"],
    "rust": ["rust"],
    "solidity": ["solidity"],
}
# Rule categories that claim a defect. performance and best-practice rules
# (gas tips, custom errors, file encodings) are style advice, not bug reports.
SEMGREP_CATEGORIES = {"security", "correctness"}

# CWEs that describe the same weakness at different granularity.
CWE_EQUIVALENTS = [
    {77, 78, 88},
    {22, 23, 36},
    {79, 80},
    {259, 321, 547, 798},
    {326, 327, 328, 916},
    {330, 338},
    {400, 770},
    {404, 772, 775},
]

DEF_PATTERNS = {
    "python": re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)"),
    "go": re.compile(r"^()func\s+(?:\([^)]*\)\s*)?(\w+)"),
    "rust": re.compile(r"^(\s*)(?:pub(?:\([^)]*\))?\s+)?(?:const\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)"),
    "solidity": re.compile(r"^(\s*)(?:function\s+(\w+)|(constructor|receive|fallback)\s*\(|modifier\s+(\w+))"),
    "typescript": re.compile(
        r"^(\s*)(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s*\*?\s*(\w+)"
        r"|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|\w+\s*=>)"
        r"|(?:(?:public|private|protected|static|readonly|async|get|set)\s+)*(\w+)\s*\([^)]*\)\s*(?::\s*[^{;]+)?\{)"),
}
TS_NOT_METHODS = {"if", "for", "while", "switch", "catch", "return", "function", "with"}


def parse_cwes(values) -> list[int]:
    if values is None:
        return []
    if isinstance(values, (str, int, dict)):
        values = [values]
    out = []
    for v in values:
        if isinstance(v, dict):
            v = v.get("id")
        m = re.search(r"(\d+)", str(v)) if v is not None else None
        if m:
            out.append(int(m.group(1)))
    return sorted(set(out))


def cwe_related(a: int, b: int) -> bool:
    return a == b or any(a in g and b in g for g in CWE_EQUIVALENTS)


def enclosing_function(source: str, line: int, language: str) -> str | None:
    """Name of the nearest definition above `line` (1-based) that encloses it.

    Python uses indentation; the brace languages take the nearest preceding
    definition, which is right for the flat functions the specimens use."""
    pattern = DEF_PATTERNS.get(language)
    lines = source.splitlines()
    if pattern is None or not 1 <= line <= len(lines):
        return None
    target = lines[line - 1]
    target_indent = len(target) - len(target.lstrip())
    for i in range(line - 1, -1, -1):
        m = pattern.match(lines[i])
        if not m:
            continue
        name = next((g for g in m.groups()[1:] if g), None)
        if name is None or (language == "typescript" and name in TS_NOT_METHODS):
            continue
        if language == "python" and i != line - 1 and len(m.group(1)) >= target_indent:
            continue
        return name
    return None


def finding_text(f: dict) -> str:
    where = f" in `{f['function']}`" if f.get("function") else ""
    cwe = "".join(f", CWE-{c}" for c in f.get("cwe") or [])
    return f"{f['rule']}{where} (line {f['line']}{cwe}): {f['message']}"


def normalize(raw: list[dict], scratch: Path, language: str) -> list[dict]:
    """Attach the enclosing function and sort findings into a stable order."""
    out = []
    for f in raw:
        rel = f["file"]
        path = scratch / rel
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            source = ""
        f = dict(f, function=enclosing_function(source, f["line"], language))
        out.append(f)
    return sorted(out, key=lambda f: (f["file"], f["line"], f["rule"], f["message"]))


def _relpath(path: str, scratch: Path) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(scratch.resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def parse_semgrep(doc: dict, scratch: Path) -> tuple[list[dict], int]:
    findings = []
    for r in doc.get("results") or []:
        extra = r.get("extra") or {}
        meta = extra.get("metadata") or {}
        if meta.get("category") not in SEMGREP_CATEGORIES:
            continue
        findings.append({
            "file": _relpath(r["path"], scratch),
            "line": int(r["start"]["line"]),
            "rule": r["check_id"],
            "severity": str(extra.get("severity", "")).lower(),
            "cwe": parse_cwes(meta.get("cwe")),
            "message": " ".join(str(extra.get("message", "")).split()),
        })
    return findings, len(doc.get("errors") or [])


def parse_bandit(doc: dict, scratch: Path) -> tuple[list[dict], int]:
    findings = []
    for r in doc.get("results") or []:
        findings.append({
            "file": _relpath(r["filename"], scratch),
            "line": int(r["line_number"]),
            "rule": f"{r['test_id']}:{r['test_name']}",
            "severity": str(r.get("issue_severity", "")).lower(),
            "cwe": parse_cwes(r.get("issue_cwe")),
            "message": " ".join(str(r.get("issue_text", "")).split()),
        })
    return findings, len(doc.get("errors") or [])


class Tool:
    def __init__(self, name: str, languages: set[str], version: str,
                 command: Callable[["Tool", Path, str], list[str]],
                 parse: Callable[[dict, Path], tuple[list[dict], int]],
                 ok_codes: tuple[int, ...] = (0, 1), cwd: Callable[["Tool"], Path | None] = lambda t: None):
        self.name, self.languages, self.version = name, languages, version
        self.command, self.parse, self.ok_codes, self.cwd = command, parse, ok_codes, cwd
        self.binary: str | None = None
        self.rules_dir: Path | None = None

    def meta(self) -> dict:
        m = {"tool": self.name, "version": self.version}
        if self.name == "semgrep":
            m["rules_commit"] = SEMGREP_RULES_COMMIT
            m["rule_categories"] = sorted(SEMGREP_CATEGORIES)
        return m

    def run(self, scratch: Path, language: str, timeout: int) -> tuple[list[dict], int]:
        cmd = self.command(self, scratch, language)
        proc = subprocess.run(cmd, cwd=self.cwd(self), capture_output=True, text=True, timeout=timeout)
        if proc.returncode not in self.ok_codes:
            raise SystemExit(f"{self.name} failed on {scratch.name} (exit {proc.returncode}):\n"
                             f"{proc.stderr[-2000:]}")
        try:
            doc = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise SystemExit(f"{self.name} did not return JSON on {scratch.name}:\n{proc.stderr[-2000:]}")
        raw, errors = self.parse(doc, scratch)
        return normalize(raw, scratch, language), errors


def _semgrep_cmd(tool: Tool, scratch: Path, language: str) -> list[str]:
    cmd = [tool.binary or "semgrep", "scan", "--json", "--quiet", "--metrics=off",
           "--disable-version-check", "--no-git-ignore"]
    for c in SEMGREP_CONFIGS[language]:
        cmd += ["--config", c]
    return cmd + [str(scratch)]


def _bandit_cmd(tool: Tool, scratch: Path, language: str) -> list[str]:
    return [tool.binary or "bandit", "-q", "-f", "json", "-r", str(scratch)]


TOOLS: dict[str, Tool] = {
    "semgrep": Tool("semgrep", set(SEMGREP_CONFIGS), SEMGREP_VERSION, _semgrep_cmd, parse_semgrep,
                    cwd=lambda t: t.rules_dir),
    "bandit": Tool("bandit", {"python"}, BANDIT_VERSION, _bandit_cmd, parse_bandit),
}


def find_binary(name: str, override: str | None) -> str:
    if override:
        return override
    venv = CACHE_DIR / "venv" / "bin" / name
    if venv.is_file():
        return str(venv)
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"{name} not found; run scripts/setup_baselines.sh or pass --{name}-bin")
    return found


def installed_version(binary: str) -> str:
    out = subprocess.run([binary, "--version"], capture_output=True, text=True)
    m = re.search(r"(\d+\.\d+\.\d+)", out.stdout + out.stderr)
    return m.group(1) if m else ""


def check_rules_dir(rules_dir: Path) -> None:
    if not (rules_dir / ".git").exists():
        raise SystemExit(f"{rules_dir}: no semgrep-rules checkout; run scripts/setup_baselines.sh "
                         "or pass --semgrep-rules")
    head = rsa.git_rev(rules_dir)
    if head != SEMGREP_RULES_COMMIT:
        raise SystemExit(f"{rules_dir}: semgrep-rules is at {head}, expected {SEMGREP_RULES_COMMIT}")


def load_reviews(root: Path, tools: set[str]) -> list[dict]:
    """Reviewed verdicts for baseline findings, validated like the audit's
    finding reviews plus a `tool` field naming a known tool."""
    path = root / "scoreboard" / REVIEWS_FILE
    if not path.is_file():
        return []
    entries = rsa.load_finding_reviews(root, REVIEWS_FILE, ("tool",))
    for r in entries:
        if r["tool"] not in tools:
            raise SystemExit(f"{path}: finding review for {r['specimen']}/{r['file']}: "
                             f"unknown tool {r['tool']!r}")
    return entries


def located(f: dict, d: dict) -> bool:
    if f["file"] != d["file"]:
        return False
    if f.get("function") and f["function"] == rsa.short_name(d["function"]):
        return True
    return abs(f["line"] - int(d.get("line") or -10**9)) <= LINE_SLACK


def category_evidence(f: dict, d: dict) -> bool:
    want = parse_cwes(d.get("cwe"))
    if any(cwe_related(a, b) for a in want for b in f.get("cwe") or []):
        return True
    return rsa.category_hit(f"{f['rule']} {f['message']}", d["category"])


def score(defects_doc: dict, findings: list[dict], specimen: str, reviews: list[dict]) -> dict:
    """Per-defect status and per-finding precision status for one tool."""
    evidence: set[tuple[str, int]] = set()
    index = {}
    by_file: dict[str, list[dict]] = {}
    for f in findings:
        lst = by_file.setdefault(f["file"], [])
        index[id(f)] = (f["file"], len(lst))
        lst.append({"kind": "baseline", "text": finding_text(f)})
    results = []
    for d in defects_doc["defects"]:
        hits = [f for f in findings if located(f, d)]
        cat = [f for f in hits if category_evidence(f, d)]
        status = "detected" if cat else "function_flagged" if hits else "missed"
        evidence.update(index[id(f)] for f in cat)
        results.append({
            "id": d["id"], "file": d["file"], "function": d["function"],
            "category": d["category"], "class": d["class"],
            "in_target_category": d["category"] in rsa.TARGET_CATEGORIES,
            "status": status,
            "findings": [finding_text(f) for f in (cat or hits)],
        })
    classified = rsa.classify_findings(by_file, evidence, specimen, reviews)
    return {"defects": results, "counts": rsa.counts(results), **classified}


def score_fixed(defects_doc: dict, findings: list[dict], specimen: str, reviews: list[dict]) -> dict:
    scored = score(defects_doc, findings, specimen, [])
    by_file: dict[str, list[dict]] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append({"kind": "baseline", "text": finding_text(f)})
    classified = rsa.classify_findings(by_file, set(), specimen, reviews)
    fc = classified["finding_counts"]
    return {
        "defects": len(defects_doc["defects"]),
        "still_reported": [d["id"] for d in scored["defects"] if d["status"] == "detected"],
        "false_alarms": fc["total"] - fc["real"],
        **classified,
    }


def scratch_copy(specimen_dir: Path, dest: Path, patched: bool) -> Path:
    scratch = dest / specimen_dir.name
    for f in rsa.audit_files(specimen_dir):
        out = scratch / f.relative_to(specimen_dir)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
    if patched:
        rsa.apply_fixed_patch(specimen_dir / rsa.FIXED_PATCH, scratch)
    return scratch


def baseline_hash(specimen_dir: Path) -> str:
    return rsa.specimen_hash(specimen_dir)


def build_record(tool: Tool, defects_doc: dict, findings: list[dict], errors: int,
                 fixed: tuple[list[dict], int] | None, reviews: list[dict],
                 source_hash: str, generated_at: str) -> dict:
    specimen = defects_doc["specimen"]
    own = [r for r in reviews if r["tool"] == tool.name]
    record = {
        "specimen": specimen,
        "language": defects_doc["language"],
        **tool.meta(),
        "generated_at": generated_at,
        "source_hash": source_hash,
        "tool_errors": errors,
        "raw_findings": findings,
        **score(defects_doc, findings, specimen, own),
    }
    if fixed is not None:
        record["fixed_raw_findings"] = fixed[0]
        record["fixed_tool_errors"] = fixed[1]
        record["fixed"] = score_fixed(defects_doc, fixed[0], specimen, own)
    return record


def run_specimen(specimen_dir: Path, tool: Tool, reviews: list[dict], timeout: int,
                 generated_at: str) -> dict:
    defects_doc = json.loads((specimen_dir / "DEFECTS.json").read_text(encoding="utf-8"))
    language = defects_doc["language"]
    has_fixed = (specimen_dir / rsa.FIXED_PATCH).is_file()
    with tempfile.TemporaryDirectory(prefix="specimen-baseline-") as tmp:
        findings, errors = tool.run(scratch_copy(specimen_dir, Path(tmp) / "orig", False), language, timeout)
        fixed = None
        if has_fixed:
            fixed = tool.run(scratch_copy(specimen_dir, Path(tmp) / "fixed", True), language, timeout)
    return build_record(tool, defects_doc, findings, errors, fixed, reviews,
                        baseline_hash(specimen_dir), generated_at)


def rescore_record(specimen_dir: Path, tool: Tool, reviews: list[dict]) -> dict:
    path = specimen_dir / "baselines" / f"{tool.name}.json"
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"{specimen_dir.name}: {path.name} missing; run the baselines first")
    current = baseline_hash(specimen_dir)
    if previous.get("source_hash") != current:
        raise SystemExit(f"{specimen_dir.name}: specimen changed since the {tool.name} run; "
                         "run the baselines again")
    if (specimen_dir / rsa.FIXED_PATCH).is_file() and "fixed_raw_findings" not in previous:
        raise SystemExit(f"{specimen_dir.name}: {tool.name} has no fixed-variant findings; "
                         "run the baselines again")
    defects_doc = json.loads((specimen_dir / "DEFECTS.json").read_text(encoding="utf-8"))
    fixed = None
    if "fixed_raw_findings" in previous:
        fixed = (previous["fixed_raw_findings"], previous.get("fixed_tool_errors", 0))
    return build_record(tool, defects_doc, previous["raw_findings"], previous.get("tool_errors", 0),
                        fixed, reviews, current, previous["generated_at"])


def aggregate(records: list[dict]) -> dict:
    """Corpus totals per tool, in the shape run_specimen_audits uses."""
    tools: dict[str, dict] = {}
    for rec in records:
        t = tools.setdefault(rec["tool"], {
            **{k: v for k, v in rec.items() if k in ("tool", "version", "rules_commit", "rule_categories")},
            "specimens": 0, "languages": set(),
            "counts": {"total": 0, "detected": 0, "function_flagged": 0, "missed": 0},
            "findings": rsa.empty_finding_counts(),
            "fixed": {"specimens": 0, "defects": 0, "still_reported": 0, "findings": 0,
                      "real": 0, "false_alarms": 0},
            "tool_errors": 0,
        })
        t["specimens"] += 1
        t["languages"].add(rec["language"])
        t["tool_errors"] += rec.get("tool_errors", 0) + rec.get("fixed_tool_errors", 0)
        for k in t["counts"]:
            t["counts"][k] += rec["counts"][k]
        for k, v in rec["finding_counts"].items():
            t["findings"][k] += v
        fx = rec.get("fixed")
        if fx:
            t["fixed"]["specimens"] += 1
            t["fixed"]["defects"] += fx["defects"]
            t["fixed"]["still_reported"] += len(fx["still_reported"])
            t["fixed"]["findings"] += fx["finding_counts"]["total"]
            t["fixed"]["real"] += fx["finding_counts"]["real"]
            t["fixed"]["false_alarms"] += fx["false_alarms"]
    for t in tools.values():
        t["languages"] = sorted(t["languages"])
    return {"tools": [tools[k] for k in sorted(tools)]}


def render_summary(summary: dict, stale: list[dict]) -> str:
    lines = [
        "# Baseline analyzers on the specimens",
        "",
        "Generated by `scripts/run_baselines.py`; do not edit by hand. Each tool is scored",
        "with the same matching rules as the audit (see the script docstring). Detection",
        "is over the specimens in the tool's languages only.",
        "",
        "| Tool | Version | Languages | Specimens | Detected | Function-flagged | Findings | Precision | Fixed-code false alarms |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for t in summary["tools"]:
        c = t["counts"]
        lines.append(
            f"| {t['tool']} | {t['version']} | {', '.join(t['languages'])} | {t['specimens']} "
            f"| {c['detected']}/{c['total']} ({rsa.pct(c['detected'], c['total'])}) "
            f"| {c['function_flagged']} | {t['findings']['total']} "
            f"| {rsa.fmt_precision(t['findings'])} | {rsa.fmt_fixed(t['fixed'])} |")
    for t in summary["tools"]:
        if t.get("rules_commit"):
            lines += ["", f"{t['tool']} rules: semgrep-rules `{t['rules_commit'][:12]}`, "
                          f"categories {', '.join(t['rule_categories'])}."]
        if t["tool_errors"]:
            lines += ["", f"{t['tool']} reported {t['tool_errors']} parse or scan errors; "
                          "files it could not parse count as having no findings."]
    if stale:
        lines += ["", f"{len(stale)} baseline review(s) matched no finding; see the run output."]
    return "\n".join(lines) + "\n"


def stale_reviews(records: list[dict], reviews: list[dict]) -> list[dict]:
    used = {(rec["tool"],) + tuple(k) for rec in records
            for k in rec.get("reviews_used", []) + (rec.get("fixed") or {}).get("reviews_used", [])}
    scored = {(rec["tool"], rec["specimen"]) for rec in records}
    return [r for r in reviews if (r["tool"], r["specimen"]) in scored
            and (r["tool"],) + tuple(rsa.review_key(r)) not in used]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tools", default=",".join(TOOLS),
                        help=f"comma-separated tools to run (default: {','.join(TOOLS)})")
    parser.add_argument("--semgrep-bin", help="semgrep executable (default: .cache/baselines/venv, then PATH)")
    parser.add_argument("--bandit-bin", help="bandit executable (default: .cache/baselines/venv, then PATH)")
    parser.add_argument("--semgrep-rules", default=str(CACHE_DIR / "semgrep-rules"),
                        help="semgrep-rules checkout at the pinned commit")
    parser.add_argument("--timeout", type=int, default=900, help="per-run timeout in seconds")
    parser.add_argument("--summary", default=str(SPECIMENS_ROOT / "BASELINES.md"))
    parser.add_argument("--scoreboard-dir", default=str(SPECIMENS_ROOT / "scoreboard"))
    parser.add_argument("--rescore", action="store_true",
                        help="re-score the committed baselines/<tool>.json findings with the current "
                             "baseline_reviews.json, without running any tool")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    names = [n.strip() for n in args.tools.split(",") if n.strip()]
    unknown = [n for n in names if n not in TOOLS]
    if unknown or not names:
        raise SystemExit(f"unknown tool(s): {', '.join(unknown) or '(none given)'}; "
                         f"choose from {', '.join(TOOLS)}")
    tools = [TOOLS[n] for n in names]
    reviews = load_reviews(SPECIMENS_ROOT, set(TOOLS))
    if not args.rescore:
        for tool in tools:
            tool.binary = find_binary(tool.name, getattr(args, f"{tool.name}_bin"))
            got = installed_version(tool.binary)
            if got != tool.version:
                raise SystemExit(f"{tool.name} {got or '(unknown)'} found, pinned {tool.version}; "
                                 "run scripts/setup_baselines.sh")
            if tool.name == "semgrep":
                tool.rules_dir = Path(args.semgrep_rules).resolve()
                check_rules_dir(tool.rules_dir)
    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    records = []
    for d in rsa.discover(SPECIMENS_ROOT):
        language = json.loads((d / "DEFECTS.json").read_text(encoding="utf-8"))["language"]
        for tool in tools:
            if language not in tool.languages:
                continue
            rec = (rescore_record(d, tool, reviews) if args.rescore
                   else run_specimen(d, tool, reviews, args.timeout, generated_at))
            records.append(rec)
            c, fx = rec["counts"], rec.get("fixed")
            print(f"{rec['specimen']} [{tool.name}]: {c['detected']}/{c['total']} detected, "
                  f"{c['function_flagged']} function-flagged, {rec['finding_counts']['total']} findings "
                  f"({rec['finding_counts']['unreviewed']} unreviewed)"
                  + (f"; fixed: {fx['false_alarms']} false alarms" if fx else ""))
    for rec in records:
        d = SPECIMENS_ROOT / rec["language"] / rec["specimen"]
        write_json(d / "baselines" / f"{rec['tool']}.json", rec)
    stale = stale_reviews(records, reviews)
    for r in stale:
        print(f"warning: stale baseline review (matched nothing): {r['tool']} "
              f"{r['specimen']}/{r['file']}: {r['finding_contains'][:80]!r}", file=sys.stderr)
    summary = aggregate(records)
    write_json(Path(args.scoreboard_dir) / "baselines.json", summary)
    Path(args.summary).write_text(render_summary(summary, stale), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
