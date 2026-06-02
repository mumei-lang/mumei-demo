#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(cases: list[dict]) -> dict:
    total = len(cases)
    converged = [case for case in cases if case.get("converged")]
    average_repairs = sum(int(case["repair_attempts"]) for case in cases) / total
    baseline_tokens = sum(int(case["baseline_tokens"]) for case in cases)
    self_correction_tokens = sum(int(case["self_correction_tokens"]) for case in cases)
    token_efficiency_gain = 1 - (self_correction_tokens / baseline_tokens)
    return {
        "total_cases": total,
        "converged_cases": len(converged),
        "convergence_rate": round(len(converged) / total, 3),
        "average_repair_attempts": round(average_repairs, 3),
        "baseline_tokens": baseline_tokens,
        "self_correction_tokens": self_correction_tokens,
        "token_efficiency_gain": round(token_efficiency_gain, 3),
        "thresholds": {
            "convergence_rate": 0.70,
            "average_repair_attempts_max": 5.0,
            "token_efficiency_gain": 0.20
        },
        "passed": (
            len(converged) / total >= 0.70
            and average_repairs <= 5.0
            and token_efficiency_gain >= 0.20
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate P9-F self-correction benchmark cases.")
    parser.add_argument(
        "--cases",
        default=str(Path(__file__).with_name("buggy_cases.json")),
        help="Buggy benchmark case JSON",
    )
    parser.add_argument("--output", required=True, help="Benchmark metrics JSON output")
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    metrics = evaluate(cases)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return 0 if metrics["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
