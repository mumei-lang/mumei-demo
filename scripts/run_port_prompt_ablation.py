#!/usr/bin/env python3
"""Screen candidate port-generation prompts without touching canonical benchmark artifacts."""
from __future__ import annotations

import argparse
import concurrent.futures
import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import run_contract_bench as cb  # noqa: E402
import run_llm_only as llm_only  # noqa: E402

SCHEMA = "mumei-demo.port-prompt-ablation/v1"
FOCUSED_CASES = ["GO02-D03", "PY02-D04", "PY03-D05", "RS03-D03", "RS03-D04"]
LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def prompt_digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def load_prompts(path: str) -> list[dict]:
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"invalid prompt input: {type(e).__name__}") from None
    rows = doc.get("prompts") if isinstance(doc, dict) else None
    if not isinstance(rows, list) or len(rows) < 2:
        raise SystemExit("invalid prompt input: expected at least two prompts")
    out, baseline = [], 0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("label"), str) or not LABEL.fullmatch(row["label"]):
            raise SystemExit("invalid prompt input: unsafe or missing label")
        if "text" not in row:
            raise SystemExit("invalid prompt input: prompt text key is required")
        text = row.get("text")
        if text is None:
            baseline += 1
            text = cb.PORT_SYSTEM
        elif not isinstance(text, str) or not text.strip():
            raise SystemExit("invalid prompt input: prompt text must be a non-empty string or null baseline")
        is_baseline = row.get("text") is None
        out.append({"label": row["label"], "text": text, "hash": prompt_digest(text), "baseline": is_baseline,
                    "benchmark_hash": cb.prompt_hash("mumei-llm") if is_baseline else None})
    if baseline != 1 or len({r["label"] for r in out}) != len(out):
        raise SystemExit("invalid prompt input: exactly one baseline and unique labels are required")
    return out


def sandbox_cases(cases: list[dict], outdir: Path) -> list[dict]:
    """Deep-copy cases whose replay fixture is available but whose writes cannot reach the repo."""
    root = outdir / "case-sandbox"
    safe = []
    for case in cases:
        copied = copy.deepcopy(case)
        target = (root / case["dir"]).resolve()
        target.mkdir(parents=True, exist_ok=True)
        replay = REPO_ROOT / case["dir"] / "replay.json"
        if replay.is_file():
            (target / "replay.json").write_bytes(replay.read_bytes())
        copied["dir"] = str(target)
        safe.append(copied)
    return safe


def validate_output_dir(raw: str) -> Path:
    path = Path(raw).resolve()
    canonical = (REPO_ROOT / "proofs" / "results").resolve()
    if path == canonical or canonical in path.parents:
        raise SystemExit("output directory must not be the canonical benchmark results directory")
    proofs = (REPO_ROOT / "proofs").resolve()
    if path == proofs or proofs in path.parents:
        raise SystemExit("output directory must not be inside the canonical proofs tree")
    if path.exists() and any(path.iterdir()):
        raise SystemExit("output directory must be empty or not exist")
    path.mkdir(parents=True, exist_ok=True)
    return path


def slim_variant(result: dict) -> dict:
    gate = result.get("fidelity_gate") or {}
    projected = cb.project_fidelity_result(result)
    semantic = gate.get("semantic_replay") or {}
    equivalence = gate.get("output_equivalence") or {}
    usage = result.get("usage") or {}
    return {
        "raw_outcome": result.get("outcome"), "raw_status": result.get("status"),
        "post_gate_outcome": projected.get("outcome"), "post_gate_status": projected.get("status"),
        "gate_decision": gate.get("decision"),
        "lint_kinds": [x.get("kind") for x in gate.get("lint_findings") or []],
        "semantic_replay": {k: semantic.get(k) for k in ("outcome", "status", "failure_kind")},
        "output_equivalence": {k: equivalence.get(k) for k in ("outcome", "status", "failure_kind")},
        "usage": {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "cost_usd", "seconds", "attempts")},
        "certificate_status": (result.get("certificate") or {}).get("status"),
        "diagnostics": result.get("diagnostics") or [],
    }


def run_prompt(label_meta: dict, cases: list[dict], provider, runs: int, jobs: int, timeout: int,
               mumei_bin: str) -> dict:
    old_system = cb.PORT_SYSTEM
    cb.PORT_SYSTEM = label_meta["text"]
    try:
        run_rows = []
        for seed in range(runs):
            with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
                records = list(pool.map(
                    lambda c: cb.run_llm_case(c, provider, "mumei-llm", seed, mumei_bin, timeout,
                                                write_certificates=False), cases))
            records = sorted(records, key=lambda r: r["id"])
            run_rows.append({"seed": seed, "score": cb.score(records), "records": [
                {"id": r["id"], **{v: slim_variant(r[v]) for v in cb.VARIANTS}} for r in records]})
        return {**label_meta, "runs": run_rows}
    finally:
        cb.PORT_SYSTEM = old_system


def render_report(doc: dict) -> str:
    lines = ["# Port prompt ablation", "",
             f"Model `{doc['model']}`. Screening only; results are noncanonical unless the model exactly matches the canonical benchmark model.",
             "Certificates: not collected / screening only; do not compare with canonical proof coverage.", ""]
    for p in doc["prompts"]:
        lines.append(f"## {p['label']} (`{p['hash']}`)")
        for run in p["runs"]:
            s = run["score"]
            lines.append(f"- seed {run['seed']}: both {s['both']}, false acceptance {s['false_acceptance']}, "
                         f"false positive {s['false_positive']}, fidelity blocked {s['fidelity_blocked']}")
            lines += ["", "| Case | Variant | Raw | Post-gate | Gate | Lint evidence | Usage |",
                      "|---|---|---|---|---|---|---|"]
            for record in run["records"]:
                for variant in ("buggy", "fixed"):
                    r = record[variant]
                    usage = r["usage"]
                    tokens = f"{usage.get('prompt_tokens') or 0}+{usage.get('completion_tokens') or 0} tok"
                    cost = f", ${usage['cost_usd']:.6f}" if isinstance(usage.get("cost_usd"), (int, float)) else ""
                    seconds = f", {usage.get('seconds')}s" if usage.get("seconds") is not None else ""
                    lines.append("| {} | {} | {} | {} | {} | {} | {}{}{} |".format(
                        record["id"], variant, r["raw_outcome"], r["post_gate_outcome"], r["gate_decision"] or "—",
                        ",".join(r["lint_kinds"]) or "—", tokens, cost, seconds))
            lines.append("")
        lines.append("")
    return "\n".join(lines)


def run(args, provider) -> dict:
    prompts = load_prompts(args.prompts)
    outdir = validate_output_dir(args.output_dir)
    if args.runs < 1 or args.jobs < 1:
        raise SystemExit("runs and jobs must be positive")
    ids = args.cases.split(",") if args.cases else FOCUSED_CASES
    cases = [c for c in cb.load_cases()[0] if c["id"] in ids]
    missing = sorted(set(ids) - {c["id"] for c in cases})
    if missing or len(cases) != len(ids):
        raise SystemExit("unknown case ids: " + ",".join(missing))
    sandbox_root = outdir / "case-sandbox"
    try:
        safe_cases = sandbox_cases(cases, outdir)
        rows = [run_prompt(p, safe_cases, provider, args.runs, args.jobs, args.timeout, args.mumei_bin) for p in prompts]
    finally:
        shutil.rmtree(sandbox_root, ignore_errors=True)
    doc = {"schema": SCHEMA, "recorded_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
           "screening_only": True, "canonical_note": "noncanonical unless model matches canonical benchmark model",
           "certificate_collection": "not collected / screening only",
           "model": args.model, "case_ids": ids, "runs_per_prompt": args.runs,
           "timeout_seconds": args.timeout, "jobs": args.jobs,
           "mumei_verifier": cb.verifier_identity(args.mumei_bin), "prompts": rows}
    (outdir / "results.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    (outdir / "report.md").write_text(render_report(doc))
    return doc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prompts", required=True, help="JSON file: {'prompts': [{'label':..., 'text': null-or-string}, ...]}")
    p.add_argument("--model", required=True, help="explicit model name; no canonical default is implied")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--cases", help="comma-separated case ids (default: focused five-case set)")
    p.add_argument("--runs", type=int, default=3, help="seeds/runs per prompt")
    p.add_argument("--jobs", type=int, default=4, help="cases run in parallel")
    p.add_argument("--timeout", type=int, default=120, help="per-verification timeout in seconds")
    p.add_argument("--mumei-bin", default=os.environ.get("MUMEI_BIN") or "mumei",
                   help="mumei binary (default: $MUMEI_BIN, then mumei on PATH)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    provider = llm_only.provider_from_env(timeout=600)
    provider.model = args.model
    provider.retries = max(provider.retries, cb.RATE_LIMIT_RETRIES)
    doc = run(args, provider)
    print(f"prompt ablation: {len(doc['prompts'])} prompt(s), {len(doc['case_ids'])} case(s) -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
