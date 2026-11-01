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

Tools: Semgrep (all languages), Bandit (Python), gosec (Go), Slither
(Solidity) and clippy (Rust). Only results that claim a defect count: Semgrep
security/correctness rules, Slither High/Medium/Low impact, clippy
correctness/suspicious lints. gosec needs `go` on PATH.

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
GOSEC_VERSION = "2.29.0"
SLITHER_VERSION = "0.11.6"
SOLC_VERSION = "0.8.24"
RUST_TOOLCHAIN = "1.99.1"
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

# Slither impact levels that claim a defect; Informational and Optimization
# results (pragma versions, naming, gas) are advice.
SLITHER_IMPACTS = {"High", "Medium", "Low"}
# Slither results carry no CWE. Detector-name prefixes mapped to the CWE the
# specimens use for the same weakness.
SLITHER_CWES = {
    "reentrancy": 841,
    "tx-origin": 346,
    "unchecked-lowlevel": 252,
    "unchecked-send": 252,
    "unchecked-transfer": 252,
    "weak-prng": 330,
    "timestamp": 829,
    "divide-before-multiply": 682,
    "arbitrary-send": 284,
    "suicidal": 284,
    "unprotected-upgrade": 284,
    "calls-loop": 400,
}

# Clippy lint groups that claim a defect. The other default groups (style,
# complexity, perf) are advice, so the run allows clippy::all and re-enables
# these two as warnings.
CLIPPY_GROUPS = ["correctness", "suspicious"]

# CWEs that describe the same weakness at different granularity.
CWE_EQUIVALENTS = [
    {77, 78, 88},
    {252, 703, 754},
    {276, 732},
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
    """Attach the enclosing function, drop exact duplicates (a rule loaded from
    two config directories reports twice) and sort into a stable order."""
    out = []
    seen = set()
    for f in raw:
        key = (f["file"], f["line"], f["rule"], f["message"])
        if key in seen:
            continue
        seen.add(key)
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


def parse_gosec(doc: dict, scratch: Path) -> tuple[list[dict], int]:
    findings = []
    for r in doc.get("Issues") or []:
        findings.append({
            "file": _relpath(r["file"], scratch),
            "line": int(str(r["line"]).split("-")[0]),
            "rule": r["rule_id"],
            "severity": str(r.get("severity", "")).lower(),
            "cwe": parse_cwes(r.get("cwe")),
            "message": " ".join(str(r.get("details", "")).split()),
        })
    errors = sum(len(v) if isinstance(v, list) else 1 for v in (doc.get("Golang errors") or {}).values())
    return findings, errors


def slither_cwes(check: str) -> list[int]:
    return sorted({cwe for prefix, cwe in SLITHER_CWES.items() if check.startswith(prefix)})


def parse_slither(doc: dict, scratch: Path) -> tuple[list[dict], int]:
    if not doc.get("success"):
        return [], 1
    findings = []
    for r in (doc.get("results") or {}).get("detectors") or []:
        if r.get("impact") not in SLITHER_IMPACTS:
            continue
        where = next((e["source_mapping"] for e in r.get("elements") or []
                      if (e.get("source_mapping") or {}).get("lines")), None)
        if where is None:
            continue
        findings.append({
            "file": _relpath(where.get("filename_relative") or where["filename_absolute"], scratch),
            "line": int(where["lines"][0]),
            "rule": r["check"],
            "severity": str(r["impact"]).lower(),
            "cwe": slither_cwes(r["check"]),
            "message": " ".join(str(r.get("description", "")).split()),
            # Descriptions quote the flagged source, so category keywords in
            # them say nothing about the check; only the CWE map counts.
            "cwe_only": True,
        })
    return findings, 0


def load_json_lines(text: str) -> list[dict]:
    return [json.loads(ln) for ln in text.splitlines() if ln.startswith("{")]


def parse_clippy(messages: list[dict], scratch: Path) -> tuple[list[dict], int]:
    findings, errors = [], 0
    for m in messages:
        if m.get("reason") != "compiler-message":
            continue
        msg = m.get("message") or {}
        code = (msg.get("code") or {}).get("code") or ""
        if not code.startswith("clippy::"):
            errors += msg.get("level") == "error"
            continue
        span = next((s for s in msg.get("spans") or [] if s.get("is_primary")), None)
        if span is None:
            continue
        findings.append({
            "file": _relpath(span["file_name"], scratch),
            "line": int(span["line_start"]),
            "rule": code,
            "severity": str(msg.get("level", "")).lower(),
            "cwe": [],
            "message": " ".join(str(msg.get("message", "")).split()),
        })
    return findings, errors


def installed_version(binary: str) -> str:
    out = subprocess.run([binary, "--version"], capture_output=True, text=True)
    m = re.search(r"(\d+\.\d+\.\d+)", out.stdout + out.stderr)
    return m.group(1) if m else ""


class Tool:
    def __init__(self, name: str, languages: set[str], version: str,
                 command: Callable[["Tool", Path, str], list[str]],
                 parse: Callable[[object, Path], tuple[list[dict], int]],
                 ok_codes: tuple[int, ...] = (0, 1),
                 cwd: Callable[["Tool", Path], Path | None] = lambda t, scratch: None,
                 load: Callable[[str], object] = json.loads,
                 version_of: Callable[["Tool"], str] = lambda t: installed_version(t.binary),
                 extra_meta: dict | None = None, exe: str | None = None,
                 cached: Callable[[], Path] | None = None):
        self.name, self.languages, self.version = name, languages, version
        self.command, self.parse, self.ok_codes, self.cwd = command, parse, ok_codes, cwd
        self.load, self.version_of, self.extra_meta = load, version_of, extra_meta or {}
        self.exe = exe or name
        self.cached = cached or (lambda: CACHE_DIR / "venv" / "bin" / self.exe)
        self.binary: str | None = None
        self.rules_dir: Path | None = None
        self.solc: str | None = None

    def meta(self) -> dict:
        return {"tool": self.name, "version": self.version, **self.extra_meta}

    def run(self, scratch: Path, language: str, timeout: int) -> tuple[list[dict], int]:
        cmd = self.command(self, scratch, language)
        proc = subprocess.run(cmd, cwd=self.cwd(self, scratch), capture_output=True, text=True,
                              timeout=timeout)
        if proc.returncode not in self.ok_codes:
            raise SystemExit(f"{self.name} failed on {scratch.name} (exit {proc.returncode}):\n"
                             f"{proc.stderr[-2000:]}")
        try:
            doc = self.load(proc.stdout)
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


def _gosec_cmd(tool: Tool, scratch: Path, language: str) -> list[str]:
    return [tool.binary or "gosec", "-fmt=json", "-quiet", "./..."]


def _slither_cmd(tool: Tool, scratch: Path, language: str) -> list[str]:
    return [tool.binary or "slither", "src", "--solc", tool.solc or "solc", "--json", "-",
            "--disable-color"]


def _clippy_cmd(tool: Tool, scratch: Path, language: str) -> list[str]:
    cmd = [tool.binary or "cargo", f"+{RUST_TOOLCHAIN}", "clippy", "--quiet", "--message-format=json",
           "--", "-A", "clippy::all"]
    for group in CLIPPY_GROUPS:
        cmd += ["-W", f"clippy::{group}"]
    return cmd


def gosec_version(tool: Tool) -> str:
    """gosec built with `go install` reports `dev`; read the module version."""
    try:
        out = subprocess.run(["go", "version", "-m", tool.binary], capture_output=True, text=True)
    except OSError:
        raise SystemExit("gosec needs `go` on PATH")
    m = re.search(r"^\s*mod\s+github\.com/securego/gosec/v2\s+v(\d+\.\d+\.\d+)", out.stdout, re.M)
    return m.group(1) if m else ""


def clippy_version(tool: Tool) -> str:
    """The pinned toolchain when `cargo +<toolchain> clippy` works with it."""
    out = subprocess.run([tool.binary, f"+{RUST_TOOLCHAIN}", "clippy", "--version"],
                         capture_output=True, text=True)
    minor = RUST_TOOLCHAIN.split(".")[1]
    if out.returncode == 0 and re.search(rf"clippy 0\.1\.{minor}\b", out.stdout):
        return RUST_TOOLCHAIN
    return ""


def _in_scratch(tool: Tool, scratch: Path) -> Path:
    return scratch


TOOLS: dict[str, Tool] = {
    "semgrep": Tool("semgrep", set(SEMGREP_CONFIGS), SEMGREP_VERSION, _semgrep_cmd, parse_semgrep,
                    cwd=lambda t, scratch: t.rules_dir,
                    extra_meta={"rules_commit": SEMGREP_RULES_COMMIT,
                                "rule_categories": sorted(SEMGREP_CATEGORIES)}),
    "bandit": Tool("bandit", {"python"}, BANDIT_VERSION, _bandit_cmd, parse_bandit),
    "gosec": Tool("gosec", {"go"}, GOSEC_VERSION, _gosec_cmd, parse_gosec, cwd=_in_scratch,
                  version_of=gosec_version, cached=lambda: CACHE_DIR / "gobin" / "gosec"),
    "slither": Tool("slither", {"solidity"}, SLITHER_VERSION, _slither_cmd, parse_slither,
                    ok_codes=(0, 1, 255), cwd=_in_scratch,
                    extra_meta={"solc_version": SOLC_VERSION, "impacts": sorted(SLITHER_IMPACTS)}),
    "clippy": Tool("clippy", {"rust"}, RUST_TOOLCHAIN, _clippy_cmd, parse_clippy, ok_codes=(0, 101),
                   cwd=_in_scratch, load=load_json_lines, version_of=clippy_version,
                   extra_meta={"lint_groups": CLIPPY_GROUPS}, exe="cargo"),
}


def find_binary(name: str, override: str | None, exe: str | None = None,
                cached: Path | None = None) -> str:
    if override:
        return override
    exe = exe or name
    cached = cached or CACHE_DIR / "venv" / "bin" / exe
    if cached.is_file():
        return str(cached)
    found = shutil.which(exe)
    if not found:
        raise SystemExit(f"{exe} not found; run scripts/setup_baselines.sh or pass --{name}-bin")
    return found


def find_solc(override: str | None) -> str:
    """solc for Slither: --solc-bin, else the solc-select artifact in the cache."""
    path = override or str(CACHE_DIR / "venv" / ".solc-select" / "artifacts"
                           / f"solc-{SOLC_VERSION}" / f"solc-{SOLC_VERSION}")
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True)
    except OSError:
        raise SystemExit(f"solc not found at {path}; run scripts/setup_baselines.sh or pass --solc-bin")
    if not re.search(rf"Version: {re.escape(SOLC_VERSION)}\b", out.stdout):
        raise SystemExit(f"{path} is not solc {SOLC_VERSION}; run scripts/setup_baselines.sh")
    return path


def check_rules_dir(rules_dir: Path) -> None:
    if not (rules_dir / ".git").exists():
        raise SystemExit(f"{rules_dir}: no semgrep-rules checkout; run scripts/setup_baselines.sh "
                         "or pass --semgrep-rules")
    head = rsa.git_rev(rules_dir)
    if head != SEMGREP_RULES_COMMIT:
        raise SystemExit(f"{rules_dir}: semgrep-rules is at {head}, expected {SEMGREP_RULES_COMMIT}")
    status = subprocess.run(["git", "-C", str(rules_dir), "status", "--porcelain"],
                            capture_output=True, text=True)
    if status.returncode != 0 or status.stdout.strip():
        raise SystemExit(f"{rules_dir}: semgrep-rules checkout has local changes; "
                         "re-run scripts/setup_baselines.sh on a clean checkout")


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
    if f.get("cwe_only"):
        return False
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
    pinned = tool.meta()
    recorded = {k: previous.get(k) for k in pinned}
    if recorded != pinned:
        raise SystemExit(f"{specimen_dir.name}: {path.name} was produced with {recorded}, "
                         f"but the current pins are {pinned}; run the baselines again")
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


META_KEYS = ("tool", "version", "rules_commit", "rule_categories", "solc_version", "impacts",
             "lint_groups")


def aggregate(records: list[dict]) -> dict:
    """Corpus totals per tool, in the shape run_specimen_audits uses."""
    tools: dict[str, dict] = {}
    for rec in records:
        t = tools.setdefault(rec["tool"], {
            **{k: v for k, v in rec.items() if k in META_KEYS},
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


BASELINES_START = "<!-- baselines:start -->"
BASELINES_END = "<!-- baselines:end -->"


def mumei_coverages(root: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(root.glob("*/*/audit/coverage.json"))]


def _empty_side() -> dict:
    return {"specimens": 0, "counts": {"total": 0, "detected": 0},
            "findings": rsa.empty_finding_counts(), "fixed": {"specimens": 0, "false_alarms": 0}}


def _add_side(side: dict, doc: dict) -> None:
    side["specimens"] += 1
    for k in side["counts"]:
        side["counts"][k] += doc["counts"][k]
    for k, v in doc["finding_counts"].items():
        side["findings"][k] += v
    fx = doc.get("fixed")
    if fx:
        side["fixed"]["specimens"] += 1
        side["fixed"]["false_alarms"] += fx["false_alarms"]


def _detected(doc: dict) -> set[tuple[str, str]]:
    return {(doc["specimen"], d["id"]) for d in doc["defects"] if d["status"] == "detected"}


def mumei_label(coverages: list[dict]) -> str:
    modes = {bool((c.get("meta") or {}).get("llm_configured")) for c in coverages}
    return {frozenset({False}): "Mumei (no LLM)",
            frozenset({True}): "Mumei (with LLM)"}.get(frozenset(modes), "Mumei (mixed LLM runs)")


def comparison(coverages: list[dict], records: list[dict]) -> dict:
    """Mumei's audit next to each baseline, per language and over the corpus.

    The corpus is the specimens with audit output; complement counts split the
    defects by whether Mumei, any baseline, both or neither detected them."""
    langs: dict[str, dict] = {}
    hashes = {}
    for c in coverages:
        lang = langs.setdefault(c["language"], {"language": c["language"], "defects": 0,
                                                "mumei": _empty_side(), "tools": {},
                                                "m": set(), "b": set()})
        lang["defects"] += c["counts"]["total"]
        _add_side(lang["mumei"], c)
        lang["m"] |= _detected(c)
        hashes[c["specimen"]] = c.get("source_hash")
    stale = set()
    for rec in records:
        lang = langs.get(rec["language"])
        if lang is None or rec["specimen"] not in hashes:
            continue
        if rec.get("source_hash") != hashes[rec["specimen"]]:
            stale.add(rec["specimen"])
        _add_side(lang["tools"].setdefault(rec["tool"], _empty_side()), rec)
        lang["b"] |= _detected(rec)
    total = {"language": "total", "defects": 0, "mumei": _empty_side(), "tools": {},
             "m": set(), "b": set()}
    rows = []
    for name in sorted(langs):
        lang = langs[name]
        for side, into in [(lang["mumei"], total["mumei"])] + [
                (t, total["tools"].setdefault(k, _empty_side())) for k, t in lang["tools"].items()]:
            into["specimens"] += side["specimens"]
            for part in ("counts", "findings", "fixed"):
                for k, v in side[part].items():
                    into[part][k] += v
        total["defects"] += lang["defects"]
        total["m"] |= lang["m"]
        total["b"] |= lang["b"]
        rows.append(lang)
    out = []
    for lang in rows + [total]:
        m, b = lang.pop("m"), lang.pop("b")
        lang["tools"] = {k: lang["tools"][k] for k in sorted(lang["tools"])}
        lang["complement"] = {"mumei_only": len(m - b), "baselines_only": len(b - m),
                              "both": len(m & b), "neither": lang["defects"] - len(m | b)}
        out.append(lang)
    return {"mumei": mumei_label(coverages), "languages": out[:-1], "total": out[-1],
            "stale_specimens": sorted(stale)}


def _cmp_row(label: str, side: dict) -> str:
    c = side["counts"]
    return (f"| {label} | {c['detected']}/{c['total']} ({rsa.pct(c['detected'], c['total'])}) "
            f"| {rsa.fmt_precision(side['findings'])} | {rsa.fmt_fixed(side['fixed'])} |")


def _complement_line(row: dict) -> str:
    k = row["complement"]
    return (f"| {row['language']} | {row['defects']} | {k['mumei_only']} | {k['baselines_only']} "
            f"| {k['both']} | {k['neither']} |")


def _stale_note(comp: dict) -> list[str]:
    if not comp["stale_specimens"]:
        return []
    return ["", f"Audit and baseline output come from different specimen sources for "
                f"{', '.join(comp['stale_specimens'])}; re-run both before comparing them."]


def render_comparison(comp: dict) -> list[str]:
    lines = [
        "", f"## {comp['mumei']} compared with the baselines", "",
        "Each analyzer is counted on the specimens in its languages only, so detection rates",
        "with different denominators are not directly comparable; compare within a language.",
        "",
        "| Language | Analyzer | Detected | Precision | Fixed-code false alarms |",
        "|---|---|---|---|---|",
    ]
    for row in comp["languages"]:
        lines.append(f"| {row['language']} |" + _cmp_row(comp["mumei"], row["mumei"])[1:])
        for name, side in row["tools"].items():
            lines.append(f"| {row['language']} |" + _cmp_row(name, side)[1:])
    lines += [
        "", "### Complementarity", "",
        "Defects split by who detects them: Mumei's audit only, at least one baseline only,",
        "both, or neither (function-flagged defects count as not detected).", "",
        "| Language | Defects | Mumei only | Baselines only | Both | Neither |",
        "|---|---|---|---|---|---|",
    ]
    lines += [_complement_line(row) for row in comp["languages"]]
    lines.append(_complement_line(comp["total"]).replace("| total |", "| **Total** |"))
    return lines + _stale_note(comp)


def readme_block(comp: dict) -> str:
    total = comp["total"]
    k = total["complement"]
    lines = [
        "## Compared with baseline analyzers", "",
        "Generated by `scripts/run_baselines.py`. Each analyzer is scored with the audit's",
        "matching rules on the specimens in its languages only; per-language tables and tool",
        "settings are in [BASELINES.md](BASELINES.md). After a new audit run, refresh this block",
        "with `python3 scripts/run_baselines.py --rescore`.", "",
        "| Analyzer | Detected | Precision | Fixed-code false alarms |",
        "|---|---|---|---|",
        _cmp_row(comp["mumei"], total["mumei"]),
    ]
    lines += [_cmp_row(name, side) for name, side in total["tools"].items()]
    lines += ["", f"Of {total['defects']} defects, {k['mumei_only']} are detected only by "
                  f"{comp['mumei']}, {k['baselines_only']} only by a baseline, {k['both']} by both "
                  f"and {k['neither']} by neither."]
    return "\n".join(lines + _stale_note(comp))


def update_readme_block(path: Path, block: str) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if BASELINES_START not in text or BASELINES_END not in text:
        raise SystemExit(f"{path}: missing {BASELINES_START} / {BASELINES_END} markers")
    pre, rest = text.split(BASELINES_START, 1)
    _, post = rest.split(BASELINES_END, 1)
    path.write_text(pre + BASELINES_START + "\n" + block.rstrip() + "\n" + BASELINES_END + post,
                    encoding="utf-8")


def render_summary(summary: dict, stale: list[dict], comp: dict | None = None) -> str:
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
        if t.get("solc_version"):
            lines += ["", f"{t['tool']} settings: solc {t['solc_version']}, "
                          f"impacts {', '.join(t['impacts'])}."]
        if t.get("lint_groups"):
            lines += ["", f"{t['tool']} settings: Rust {t['version']}, "
                          f"lint groups {', '.join(t['lint_groups'])}."]
        if t["tool_errors"]:
            lines += ["", f"{t['tool']} reported {t['tool_errors']} parse or scan errors; "
                          "files it could not parse count as having no findings."]
    if stale:
        lines += ["", f"{len(stale)} baseline review(s) matched no finding; see the run output."]
    if comp and comp["languages"]:
        lines += render_comparison(comp)
    return "\n".join(lines) + "\n"


def stale_reviews(records: list[dict], reviews: list[dict]) -> list[dict]:
    used = {(rec["tool"],) + tuple(k) for rec in records
            for k in rec.get("reviews_used", []) + (rec.get("fixed") or {}).get("reviews_used", [])}
    scored = {(rec["tool"], rec["specimen"]) for rec in records}
    return [r for r in reviews if (r["tool"], r["specimen"]) in scored
            and (r["tool"],) + tuple(rsa.review_key(r)) not in used]


def committed_records(root: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("*/*/baselines/*.json"))]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tools", default=",".join(TOOLS),
                        help=f"comma-separated tools to run (default: {','.join(TOOLS)})")
    parser.add_argument("--semgrep-bin", help="semgrep executable (default: .cache/baselines/venv, then PATH)")
    parser.add_argument("--bandit-bin", help="bandit executable (default: .cache/baselines/venv, then PATH)")
    parser.add_argument("--gosec-bin", help="gosec executable (default: .cache/baselines/gobin, then PATH)")
    parser.add_argument("--slither-bin", help="slither executable (default: .cache/baselines/venv, then PATH)")
    parser.add_argument("--clippy-bin", help="cargo executable used for clippy (default: PATH)")
    parser.add_argument("--solc-bin", help=f"solc {SOLC_VERSION} for slither "
                                           "(default: the solc-select artifact in .cache/baselines/venv)")
    parser.add_argument("--semgrep-rules", default=str(CACHE_DIR / "semgrep-rules"),
                        help="semgrep-rules checkout at the pinned commit")
    parser.add_argument("--timeout", type=int, default=900, help="per-run timeout in seconds")
    parser.add_argument("--summary", default=str(SPECIMENS_ROOT / "BASELINES.md"))
    parser.add_argument("--scoreboard-dir", default=str(SPECIMENS_ROOT / "scoreboard"))
    parser.add_argument("--specimens-readme",
                        help="README whose baselines block gets the Mumei comparison "
                             "(default: specimens/README.md; skipped if the file does not exist)")
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
            tool.binary = find_binary(tool.name, getattr(args, f"{tool.name}_bin"), tool.exe,
                                      tool.cached())
            got = tool.version_of(tool)
            if got != tool.version:
                raise SystemExit(f"{tool.name} {got or '(unknown)'} found, pinned {tool.version}; "
                                 "run scripts/setup_baselines.sh")
            if tool.name == "semgrep":
                tool.rules_dir = Path(args.semgrep_rules).resolve()
                check_rules_dir(tool.rules_dir)
            if tool.name == "slither":
                tool.solc = find_solc(args.solc_bin)
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
    # A run of some tools keeps the committed records of the others in the totals.
    records = committed_records(SPECIMENS_ROOT)
    stale = stale_reviews(records, reviews)
    for r in stale:
        print(f"warning: stale baseline review (matched nothing): {r['tool']} "
              f"{r['specimen']}/{r['file']}: {r['finding_contains'][:80]!r}", file=sys.stderr)
    summary = aggregate(records)
    write_json(Path(args.scoreboard_dir) / "baselines.json", summary)
    comp = comparison(mumei_coverages(SPECIMENS_ROOT), records)
    write_json(Path(args.scoreboard_dir) / "comparison.json", comp)
    Path(args.summary).write_text(render_summary(summary, stale, comp), encoding="utf-8")
    if comp["languages"]:
        update_readme_block(Path(args.specimens_readme or SPECIMENS_ROOT / "README.md"),
                            readme_block(comp))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
