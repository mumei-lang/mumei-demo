#!/usr/bin/env python3
"""Re-run committed contract-bench proof certificates through the current Lean dual checker.

After updating the default results file, run `python3 scripts/run_contract_bench.py --render-only`
to regenerate the Markdown summary."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_contract_bench as cb  # noqa: E402

SCHEMA = "mumei-demo.lean-dual-check-recheck/v1"


def certificate_outcome(case: dict, fixed: dict, cert_text: str) -> dict | None:
    certificate = fixed.get("certificate")
    if not isinstance(certificate, dict) or certificate.get("file") != cb.CERT_FILE:
        return {"status": "stale", "reason": "missing recorded fixed proof certificate summary"}
    if certificate.get("sha256") != cb.sha256(cert_text):
        return {"status": "stale", "reason": "committed proof certificate hash does not match the recorded result"}
    if certificate.get("port_sha256") != cb.sha256(case["ports"]["fixed"]):
        return {"status": "stale", "reason": "recorded proof certificate does not match the current fixed port"}
    return None


def refresh_results(lean_dir: Path, timeout: int, results_path: Path = cb.RESULTS_DIR / "mumei.json") -> dict:
    if not cb.lake_on_path():
        raise ValueError("environment_failure: lake is not on PATH; no dual-check result was measured")
    if not (lean_dir / "scripts" / "bridge.py").is_file():
        raise ValueError(f"environment_failure: mumei-lean bridge is not available at {lean_dir}")
    cases, errors = cb.load_cases()
    if errors:
        raise ValueError("invalid contract benchmark cases: " + "; ".join(errors))
    doc = json.loads(results_path.read_text())
    if doc.get("arm") != "mumei":
        raise ValueError("unsupported_input: --results must be the reference-port mumei arm")
    runs = doc.get("runs") or []
    if len(runs) != 1:
        raise ValueError("expected exactly one recorded mumei-arm run")
    records = {record.get("id"): record for record in runs[0] if isinstance(record, dict)}
    missing = sorted({case["id"] for case in cases} - set(records))
    if missing:
        raise ValueError("recorded run is missing cases: " + ", ".join(missing))

    checked = []
    for case in cases:
        cert_path = cb.REPO_ROOT / case["dir"] / cb.CERT_FILE
        record = records[case["id"]]
        fixed = record.setdefault("fixed", {})
        if not cert_path.is_file():
            outcome = {"status": "unsupported", "reason": "missing committed proof certificate"}
        else:
            cert_text = cert_path.read_text()
            outcome = certificate_outcome(case, fixed, cert_text) or cb.lean_dual_check(
                str(lean_dir), case, cert_text, timeout)
        checked.append({"id": case["id"], "atom": case["atom"], **outcome})
        fixed["lean_dual_check"] = outcome

    doc["lean_bridge"] = cb.git_identity(str(lean_dir))
    doc["lean_dual_recheck"] = {
        "schema_version": SCHEMA,
        "recorded_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "counts": dict(sorted(Counter(item["status"] for item in checked).items())),
        "total": len(checked),
    }
    results_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"document": doc, "checks": checked}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lean_dir", type=Path, help="mumei-lean checkout to measure")
    parser.add_argument("--timeout", type=int, default=120, help="per-certificate timeout in seconds")
    parser.add_argument("--results", type=Path, default=cb.RESULTS_DIR / "mumei.json")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout < 1:
        raise SystemExit("--timeout must be positive")
    try:
        refreshed = refresh_results(args.lean_dir.resolve(), args.timeout, args.results)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"lean dual-check recheck failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(refreshed["document"]["lean_dual_recheck"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
