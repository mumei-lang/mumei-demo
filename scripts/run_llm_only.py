#!/usr/bin/env python3
"""Ask an LLM alone (no Mumei) to review the specimens, and score it like the baselines.

This is the LLM-only arm of the benchmark. For every specimen the model gets
the same files `mumei-agent audit` sees (git-tracked, fixed.patch excluded),
with line numbers, and returns its findings as JSON. The run is repeated with
fixed.patch applied, so false alarms on fixed code are measured too.

Findings are scored by run_baselines.py: a finding belongs to a defect when it
is in the defect's file and in the defect's function or within LINE_SLACK
lines of its line, and it is `detected` when its CWE or text names the
defect's category. Reviewed verdicts come from scoreboard/llm_only_reviews.json.

Model output is untrusted: findings that point at a file the model was not
given, or at a line outside that file, are dropped and counted as invalid.

The provider is any OpenAI-compatible endpoint, configured like mumei-agent:
LLM_API_KEY (or OPENAI_API_KEY), LLM_BASE_URL and LLM_MODEL. The key is only
sent to the endpoint; it is never written or printed. Each specimen is
reviewed `--runs` times (temperature 0, seed = run number) so run-to-run
variance shows. Results go to specimens/<language>/<id>/llm_only/<model>.json,
specimens/scoreboard/llm_only.json and specimens/LLM_ONLY.md. `--rescore`
re-scores the committed findings without calling the model.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import statistics
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

_SPEC = importlib.util.spec_from_file_location(
    "run_baselines", Path(__file__).resolve().parent / "run_baselines.py")
rb = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("run_baselines", rb)
_SPEC.loader.exec_module(rb)
rsa = rb.rsa

SPECIMENS_ROOT = rb.SPECIMENS_ROOT
TOOL = "llm-only"
OUT_DIR = "llm_only"
REVIEWS_FILE = "llm_only_reviews.json"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o"
MAX_TOKENS = 8000
RETRY_STATUSES = {408, 409, 429, 500, 502, 503, 504}
PROMPT_VERSION = 2
# The model sees what mumei-agent's audit sees: product code and its data,
# not the ground truth, the docs or the run/repro harness (which spells the
# defects out). Test files follow mumei-agent's default test-file rule.
EXCLUDED_NAMES = frozenset({"DEFECTS.json"})
EXCLUDED_SUFFIXES = (".md", ".sh")
TEST_SUFFIXES = (
    "_test.go", ".test.ts", ".test.tsx", ".test.js", ".test.jsx", ".spec.ts", ".spec.tsx",
    ".spec.js", ".spec.jsx", "_test.py", ".t.sol",
)
TEST_DIRS = frozenset({"tests", "__tests__", "testdata"})
SYSTEM_PROMPT = """You are a code reviewer. You are given every source file of one small project.
Report each security vulnerability or correctness defect you can point to in the code.
Do not report style, naming, performance tips or missing tests.

Answer with one JSON object and nothing else:
{"findings": [{"file": "<path exactly as given>", "line": <line number>,
  "cwe": "CWE-<n>" or null, "category": "<short kebab-case weakness name>",
  "message": "<one sentence: what is wrong and how it can be triggered>"}]}
Use the line numbers shown at the start of each line. Report one finding per defect.
If you find nothing, answer {"findings": []}."""


def prompt_hash() -> str:
    """Pins everything that shapes the model input: version, system prompt,
    the user-prompt layout (rendered on a fixed sample) and the input rules."""
    sample = user_prompt("sample", [("a/b.py", "x = 1\ny = 2\n")])
    rules = json.dumps([sorted(EXCLUDED_NAMES), EXCLUDED_SUFFIXES, TEST_SUFFIXES, sorted(TEST_DIRS)])
    text = "\n".join([str(PROMPT_VERSION), SYSTEM_PROMPT, sample, rules])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def is_review_input(rel: str) -> bool:
    """Whether a specimen file (path relative to the specimen) goes to the model."""
    parts = rel.split("/")
    name = parts[-1].lower()
    if parts[-1] in EXCLUDED_NAMES or name.endswith(EXCLUDED_SUFFIXES):
        return False
    if name.endswith(TEST_SUFFIXES) or (name.startswith("test_") and name.endswith(".py")):
        return False
    return not any(p.lower() in TEST_DIRS for p in parts[:-1])


def model_slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "__", model).strip("_") or "model"


def source_files(scratch: Path) -> list[tuple[str, str]]:
    """(relative path, text) for every file of the scratch copy that is_review_input."""
    out = []
    for p in sorted(scratch.rglob("*")):
        rel = p.relative_to(scratch).as_posix()
        if not p.is_file() or not is_review_input(rel):
            continue
        try:
            out.append((rel, p.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            continue
    return out


def user_prompt(language: str, files: list[tuple[str, str]]) -> str:
    parts = [f"Project language: {language}. Files: {len(files)}."]
    for rel, text in files:
        numbered = "\n".join(f"{i:4d}| {line}" for i, line in enumerate(text.splitlines(), 1))
        parts.append(f"### {rel}\n```\n{numbered}\n```")
    return "\n\n".join(parts)


class Provider:
    """Minimal OpenAI-compatible chat client (stdlib only)."""

    def __init__(self, api_key: str, base_url: str, model: str, timeout: int = 600,
                 retries: int = 4, opener: Callable | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.api_key, self.model, self.timeout, self.retries = api_key, model, timeout, retries
        self.base_url = base_url.rstrip("/")
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleep

    @property
    def openrouter(self) -> bool:
        return (urllib.parse.urlsplit(self.base_url).hostname or "").endswith("openrouter.ai")

    def body(self, messages: list[dict], seed: int) -> dict:
        body = {"model": self.model, "messages": messages, "temperature": 0, "seed": seed,
                "max_tokens": MAX_TOKENS, "response_format": {"type": "json_object"}}
        if self.openrouter:
            body["usage"] = {"include": True}
        return body

    def complete(self, messages: list[dict], seed: int) -> tuple[str, dict]:
        data = json.dumps(self.body(messages, seed)).encode("utf-8")
        last = ""
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=data, method="POST",
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {self.api_key}"})
            started = time.monotonic()
            try:
                with self.opener(req, timeout=self.timeout) as resp:
                    doc = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code in RETRY_STATUSES and attempt < self.retries:
                    self.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"LLM request failed: {last}") from None
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
                last = type(e).__name__
                if attempt < self.retries:
                    self.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"LLM request failed: {last}") from None
            seconds = time.monotonic() - started
            try:
                text = doc["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                raise RuntimeError("LLM response has no message content") from None
            u = doc.get("usage") or {}
            usage = {"prompt_tokens": int(u.get("prompt_tokens") or 0),
                     "completion_tokens": int(u.get("completion_tokens") or 0),
                     "cost_usd": float(u["cost"]) if isinstance(u.get("cost"), (int, float)) else None,
                     "seconds": round(seconds, 2), "attempts": attempt + 1}
            return text, usage
        raise RuntimeError(f"LLM request failed: {last}")


def parse_reply(text: str) -> list | None:
    """The `findings` list of a reply, or None when the reply is not that JSON shape."""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and isinstance(doc.get("findings"), list):
        return doc["findings"]
    return None


def validate(items: list, files: dict[str, int]) -> tuple[list[dict], list[dict]]:
    """Split model findings into baseline-shaped findings and invalid ones."""
    raw, invalid = [], []
    for item in items:
        if not isinstance(item, dict):
            invalid.append({"reason": "not an object", "item": str(item)[:200]})
            continue
        rel = str(item.get("file") or "").strip()
        while rel.startswith("./"):
            rel = rel[2:]
        line = item.get("line")
        if isinstance(line, str) and line.strip().isdigit():
            line = int(line.strip())
        if rel not in files:
            invalid.append({"reason": "unknown file", "file": rel[:200]})
            continue
        if not isinstance(line, int) or isinstance(line, bool) or not 1 <= line <= files[rel]:
            invalid.append({"reason": "line out of range", "file": rel, "line": str(line)[:40]})
            continue
        category = str(item.get("category") or "finding").strip()[:80] or "finding"
        message = " ".join(str(item.get("message") or "").split())[:500]
        raw.append({"file": rel, "line": line, "rule": category, "message": message,
                    "cwe": rb.parse_cwes(item.get("cwe"))})
    return raw, invalid


def review(provider: Provider, scratch: Path, language: str, seed: int) -> dict:
    """One model review of a scratch copy: normalized findings, invalid ones, usage."""
    files = source_files(scratch)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(language, files)}]
    text, usage = provider.complete(messages, seed)
    items = parse_reply(text)
    if items is None:
        return {"raw_findings": [], "invalid_findings": [], "tool_errors": 1, "usage": usage}
    lines = {rel: max(1, len(body.splitlines())) for rel, body in files}
    raw, invalid = validate(items, lines)
    return {"raw_findings": rb.normalize(raw, scratch, language), "invalid_findings": invalid,
            "tool_errors": 0, "usage": usage}


def score_run(defects_doc: dict, run: dict, reviews: list[dict]) -> dict:
    specimen = defects_doc["specimen"]
    out = {k: run[k] for k in ("run", "raw_findings", "invalid_findings", "tool_errors", "usage")}
    out.update(rb.score(defects_doc, run["raw_findings"], specimen, reviews))
    if "fixed_raw_findings" in run:
        for k in ("fixed_raw_findings", "fixed_invalid_findings", "fixed_tool_errors", "fixed_usage"):
            out[k] = run[k]
        out["fixed"] = rb.score_fixed(defects_doc, run["fixed_raw_findings"], specimen, reviews)
    return out


def meta(model: str) -> dict:
    return {"tool": TOOL, "model": model, "prompt_version": PROMPT_VERSION,
            "prompt_hash": prompt_hash(), "temperature": 0}


def build_record(defects_doc: dict, model: str, runs: list[dict], reviews: list[dict],
                 source_hash: str, generated_at: str) -> dict:
    return {"specimen": defects_doc["specimen"], "language": defects_doc["language"],
            **meta(model), "generated_at": generated_at, "source_hash": source_hash,
            "runs": [score_run(defects_doc, r, reviews) for r in sorted(runs, key=lambda r: r["run"])]}


def record_path(specimen_dir: Path, model: str) -> Path:
    return specimen_dir / OUT_DIR / f"{model_slug(model)}.json"


def run_specimen(specimen_dir: Path, provider: Provider, runs: int, reviews: list[dict],
                 generated_at: str, jobs: int = 1) -> dict:
    defects_doc = json.loads((specimen_dir / "DEFECTS.json").read_text(encoding="utf-8"))
    language = defects_doc["language"]
    has_fixed = (specimen_dir / rsa.FIXED_PATCH).is_file()
    with tempfile.TemporaryDirectory(prefix="specimen-llm-") as tmp:
        orig = rb.scratch_copy(specimen_dir, Path(tmp) / "orig", False)
        fixed = rb.scratch_copy(specimen_dir, Path(tmp) / "fixed", True) if has_fixed else None
        tasks = [(i, "orig", orig) for i in range(1, runs + 1)]
        tasks += [(i, "fixed", fixed) for i in range(1, runs + 1) if fixed is not None]
        with concurrent.futures.ThreadPoolExecutor(max(1, jobs)) as pool:
            done = dict(zip([(i, v) for i, v, _ in tasks],
                            pool.map(lambda t: review(provider, t[2], language, t[0]), tasks)))
    out = []
    for i in range(1, runs + 1):
        r = {"run": i, **done[(i, "orig")]}
        if fixed is not None:
            f = done[(i, "fixed")]
            r.update(fixed_raw_findings=f["raw_findings"], fixed_invalid_findings=f["invalid_findings"],
                     fixed_tool_errors=f["tool_errors"], fixed_usage=f["usage"])
        out.append(r)
    return build_record(defects_doc, provider.model, out, reviews, rb.baseline_hash(specimen_dir),
                        generated_at)


def rescore_record(specimen_dir: Path, model: str, reviews: list[dict]) -> dict:
    path = record_path(specimen_dir, model)
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"{specimen_dir.name}: {path.name} missing; run the LLM-only review first")
    pinned = meta(model)
    recorded = {k: previous.get(k) for k in pinned}
    if recorded != pinned:
        raise SystemExit(f"{specimen_dir.name}: {path.name} was produced with {recorded}, "
                         f"but the current settings are {pinned}; run the LLM-only review again")
    current = rb.baseline_hash(specimen_dir)
    if previous.get("source_hash") != current:
        raise SystemExit(f"{specimen_dir.name}: specimen changed since the LLM-only review; "
                         "run it again")
    if (specimen_dir / rsa.FIXED_PATCH).is_file() and any(
            "fixed_raw_findings" not in r for r in previous.get("runs") or []):
        raise SystemExit(f"{specimen_dir.name}: LLM-only review has no fixed-variant findings; "
                         "run it again")
    if not previous.get("runs"):
        raise SystemExit(f"{specimen_dir.name}: {path.name} has no runs; run the LLM-only review again")
    defects_doc = json.loads((specimen_dir / "DEFECTS.json").read_text(encoding="utf-8"))
    return build_record(defects_doc, model, previous["runs"], reviews, current, previous["generated_at"])


def run_views(records: list[dict]) -> list[list[dict]]:
    """Per run number, the specimen records in run_baselines' single-run shape."""
    numbers = sorted({r["run"] for rec in records for r in rec["runs"]})
    views = []
    for n in numbers:
        view = []
        for rec in records:
            run = next((r for r in rec["runs"] if r["run"] == n), None)
            if run is None:
                raise SystemExit(f"{rec['specimen']}: LLM-only review has no run {n}; "
                                 "all specimens need the same runs")
            view.append({"specimen": rec["specimen"], "language": rec["language"], "tool": TOOL,
                         "tool_errors": run["tool_errors"],
                         "fixed_tool_errors": run.get("fixed_tool_errors", 0),
                         **{k: run[k] for k in ("defects", "counts", "finding_counts")},
                         **({"fixed": run["fixed"]} if "fixed" in run else {})})
        views.append(view)
    return views


def _usage_sum(records: list[dict], n: int) -> dict:
    total = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0,
             "cost_usd": 0.0, "cost_unknown_calls": 0, "invalid_findings": 0}
    for rec in records:
        for run in rec["runs"]:
            if run["run"] != n:
                continue
            for u, inv in ((run["usage"], run["invalid_findings"]),
                           (run.get("fixed_usage"), run.get("fixed_invalid_findings") or [])):
                if not u:
                    continue
                total["calls"] += 1
                total["prompt_tokens"] += u["prompt_tokens"]
                total["completion_tokens"] += u["completion_tokens"]
                total["seconds"] += u["seconds"]
                total["invalid_findings"] += len(inv)
                if u.get("cost_usd") is None:
                    total["cost_unknown_calls"] += 1
                else:
                    total["cost_usd"] += u["cost_usd"]
    total["seconds"] = round(total["seconds"], 1)
    total["cost_usd"] = round(total["cost_usd"], 6)
    return total


def _spread(values: list[float]) -> dict:
    return {"mean": round(statistics.mean(values), 2), "min": min(values), "max": max(values)}


def aggregate(records: list[dict], model: str) -> dict:
    views = run_views(records)
    numbers = sorted({r["run"] for rec in records for r in rec["runs"]})
    runs = []
    for n, view in zip(numbers, views):
        totals = rb.aggregate(view)["tools"][0]
        runs.append({"run": n, **{k: totals[k] for k in ("counts", "findings", "fixed", "tool_errors")},
                     "usage": _usage_sum(records, n)})
    detected = [{(v["specimen"], d["id"]) for v in view for d in v["defects"] if d["status"] == "detected"}
                for view in views]
    total = sum(len(rec["runs"][0]["defects"]) for rec in records) if records else 0
    return {
        **meta(model),
        "specimens": len(records),
        "languages": sorted({rec["language"] for rec in records}),
        "defects": total,
        "runs": runs,
        "detected": _spread([r["counts"]["detected"] for r in runs]) if runs else None,
        "fixed_false_alarms": _spread([r["fixed"]["false_alarms"] for r in runs]) if runs else None,
        "detected_in_any_run": len(set().union(*detected)) if detected else 0,
        "detected_in_every_run": len(set.intersection(*detected)) if detected else 0,
        "cost_usd": round(sum(r["usage"]["cost_usd"] for r in runs), 6),
        "cost_unknown_calls": sum(r["usage"]["cost_unknown_calls"] for r in runs),
    }


def render_summary(summary: dict, stale: list[dict]) -> str:
    lines = [
        "# LLM-only review",
        "",
        "Generated by `scripts/run_llm_only.py`. The model reviews each specimen's source on its own",
        "(no Mumei), and its findings are scored with the baselines' matcher (see `BASELINES.md`).",
        "",
        f"- Model: `{summary['model']}` (temperature 0, prompt v{summary['prompt_version']} "
        f"`{summary['prompt_hash']}`)",
        f"- Specimens: {summary['specimens']} ({', '.join(summary['languages'])}), "
        f"defects: {summary['defects']}",
        f"- Runs: {len(summary['runs'])}; detected in any run: {summary['detected_in_any_run']}, "
        f"in every run: {summary['detected_in_every_run']}",
        f"- Cost: ${summary['cost_usd']:.4f}"
        + (f" ({summary['cost_unknown_calls']} calls without a reported cost)"
           if summary["cost_unknown_calls"] else ""),
        "",
        "| Run | Detected | Detected or flagged | Precision | Findings (unreviewed) | Fixed false alarms "
        "| Invalid findings | Errors | Tokens in / out | Seconds | Cost |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in summary["runs"]:
        c, f, u = r["counts"], r["findings"], r["usage"]
        lines.append(
            f"| {r['run']} | {c['detected']}/{c['total']} ({rsa.pct(c['detected'], c['total'])}) | "
            f"{c['detected'] + c['function_flagged']}/{c['total']} | {rsa.fmt_precision(f)} | "
            f"{f['total']} ({f['unreviewed']}) | {r['fixed']['false_alarms']} | "
            f"{u['invalid_findings']} | {r['tool_errors']} | "
            f"{u['prompt_tokens']} / {u['completion_tokens']} | {u['seconds']} | ${u['cost_usd']:.4f} |")
    if stale:
        lines += ["", "Stale reviews (matched no finding):", ""]
        lines += [f"- {r['specimen']}/{r['file']}: `{r['finding_contains'][:80]}`" for r in stale]
    return "\n".join(lines) + "\n"


def stale_reviews(records: list[dict], reviews: list[dict]) -> list[dict]:
    used = {tuple(k) for rec in records for run in rec["runs"]
            for part in (run, run.get("fixed") or {}) for k in part.get("reviews_used") or []}
    return [r for r in reviews if rsa.review_key(r) not in used]


def load_reviews(root: Path) -> list[dict]:
    return rsa.load_finding_reviews(root, REVIEWS_FILE)


def provider_from_env(timeout: int) -> Provider:
    key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    if not key:
        raise SystemExit("LLM_API_KEY (or OPENAI_API_KEY) is not set")
    return Provider(key, os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL,
                    os.environ.get("LLM_MODEL") or DEFAULT_MODEL, timeout=timeout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", help="model to re-score with --rescore (default: LLM_MODEL, then "
                                        f"{DEFAULT_MODEL}); a review always uses LLM_MODEL")
    parser.add_argument("--runs", type=int, default=3, help="reviews per specimen and variant")
    parser.add_argument("--jobs", type=int, default=4, help="concurrent model calls per specimen")
    parser.add_argument("--only", help="comma-separated specimen ids to review; the others keep "
                                       "their committed findings, re-scored")
    parser.add_argument("--timeout", type=int, default=600, help="per-request timeout in seconds")
    parser.add_argument("--summary", default=str(SPECIMENS_ROOT / "LLM_ONLY.md"))
    parser.add_argument("--scoreboard-dir", default=str(SPECIMENS_ROOT / "scoreboard"))
    parser.add_argument("--rescore", action="store_true",
                        help="re-score the committed llm_only/<model>.json findings with the current "
                             "llm_only_reviews.json, without calling the model")
    return parser


def main(argv: list[str], provider: Provider | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    specimens = rsa.discover(SPECIMENS_ROOT)
    only = {s.strip() for s in (args.only or "").split(",") if s.strip()}
    unknown = only - {d.name for d in specimens}
    if unknown:
        raise SystemExit(f"unknown specimen(s): {', '.join(sorted(unknown))}")
    if args.rescore:
        model = args.model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
    else:
        provider = provider or provider_from_env(args.timeout)
        model = provider.model
        if args.model and args.model != model:
            raise SystemExit(f"--model {args.model} differs from LLM_MODEL {model}")
    if not args.rescore:
        for d in specimens:
            if only and d.name not in only and record_path(d, model).is_file():
                kept = json.loads(record_path(d, model).read_text(encoding="utf-8")).get("runs") or []
                if len(kept) != args.runs:
                    raise SystemExit(f"{d.name}: committed review has {len(kept)} runs, not "
                                     f"--runs {args.runs}; all specimens need the same runs")
    reviews = load_reviews(SPECIMENS_ROOT)
    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    records = []
    for d in specimens:
        fresh = not args.rescore and (not only or d.name in only)
        if not fresh and not record_path(d, model).is_file():
            continue
        rec = (run_specimen(d, provider, args.runs, reviews, generated_at, args.jobs) if fresh
               else rescore_record(d, model, reviews))
        records.append(rec)
        for run in rec["runs"]:
            c, fx = run["counts"], run.get("fixed")
            print(f"{rec['specimen']} [{model} run {run['run']}]: {c['detected']}/{c['total']} detected, "
                  f"{c['function_flagged']} function-flagged, {run['finding_counts']['total']} findings, "
                  f"{len(run['invalid_findings'])} invalid"
                  + (f"; fixed: {fx['false_alarms']} false alarms" if fx else ""))
    if not records:
        raise SystemExit(f"no LLM-only reviews for {model}; run without --rescore first")
    for rec in records:
        rb.write_json(record_path(SPECIMENS_ROOT / rec["language"] / rec["specimen"], model), rec)
    stale = stale_reviews(records, reviews)
    for r in stale:
        print(f"warning: stale LLM-only review (matched nothing): {r['specimen']}/{r['file']}: "
              f"{r['finding_contains'][:80]!r}", file=sys.stderr)
    summary = aggregate(records, model)
    rb.write_json(Path(args.scoreboard_dir) / "llm_only.json", summary)
    Path(args.summary).write_text(render_summary(summary, stale), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
