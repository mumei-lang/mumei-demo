from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import report_output_equivalence_coverage as coverage_report  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_output_equivalence_coverage_buckets_are_mutually_exclusive() -> None:
    gate = {"output_equivalence": {"outcome": "inconclusive", "status": "error",
                                   "failure_kind": "environment_failure"}}
    assert coverage_report.bucket(gate, {"outcome": "proven"}) == "operational"

    gate = {"output_equivalence": {"outcome": "inconclusive", "status": "timeout",
                                   "failure_kind": "budget_exhausted"}}
    assert coverage_report.bucket(gate, {"outcome": "proven"}) == "timeout"

    gate = {"output_equivalence": {"outcome": "inconclusive", "status": "success",
                                   "reason": "bounded_interactions_matched"}}
    assert coverage_report.bucket(gate, {"outcome": "proven"}) == "bounded_finite_agreement"

    gate = {"output_equivalence": {"outcome": "inconclusive", "status": "success",
                                   "reason": "helper_body_valid_domain_matched"}}
    assert coverage_report.bucket(gate, {"outcome": "proven"}) == "helper_valid_domain_agreement"

    assert coverage_report.bucket(None, {"outcome": "refuted"}) == "not_applicable_not_proven"
    assert coverage_report.bucket(None, {"outcome": "proven"}) == "unavailable_other"


def test_committed_output_equivalence_coverage_report_is_up_to_date() -> None:
    doc = json.loads((REPO_ROOT / "proofs/results/mumei-llm-openai__gpt-6-luna.json").read_text(encoding="utf-8"))
    expected = coverage_report.render(coverage_report.coverage(doc))

    assert (REPO_ROOT / "proofs/OUTPUT_EQUIVALENCE_COVERAGE.md").read_text(encoding="utf-8") == expected


def test_output_equivalence_coverage_counts_every_recorded_row() -> None:
    doc = json.loads((REPO_ROOT / "proofs/results/mumei-llm-openai__gpt-6-luna.json").read_text(encoding="utf-8"))
    result = coverage_report.coverage(doc)

    assert len(result["rows"]) == 6
    for row in result["rows"]:
        assert sum(row["counts"].values()) == 71


def test_helper_inventory_classifies_recorded_helper_atoms() -> None:
    inventory = coverage_report.helper_definitions()
    pairs = [entry for entries in inventory.values() for entry in entries]

    assert len(inventory) == 12
    assert len(pairs) == 12
    assert {entry["shape"] for entry in pairs} == {"pure_nonrecursive_inlineable"}
    assert all(entry["body_available"] and entry["inline_eligible"] for entry in pairs)
