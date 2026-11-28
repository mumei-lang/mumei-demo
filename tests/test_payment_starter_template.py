from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER_DIR = REPO_ROOT / "templates" / "payment-ledger-starter"
WORKFLOW_PATH = STARTER_DIR / ".github" / "workflows" / "mumei-audit.yml"
README_PATH = STARTER_DIR / "README.md"
PIN = "b128577526c3540f5f307c0ddf169e1720389d15"


def test_payment_starter_has_repo_root_layout() -> None:
    assert WORKFLOW_PATH.is_file()
    assert (STARTER_DIR / "audit-baseline.json").is_file()
    assert (STARTER_DIR / "src" / "payment_ledger.py").is_file()
    assert README_PATH.is_file()

    baseline = json.loads((STARTER_DIR / "audit-baseline.json").read_text(encoding="utf-8"))
    assert baseline == {"version": "mumei.audit-baseline/v1", "fingerprints": []}

    # The template is meaningful when its contents are copied to a consumer
    # repository root: workflow path, source path, and baseline path are all
    # already in their final locations.
    actual_files = sorted(str(path.relative_to(STARTER_DIR)) for path in STARTER_DIR.rglob("*") if path.is_file())
    assert actual_files == [
        ".github/workflows/mumei-audit.yml",
        "README.md",
        "audit-baseline.json",
        "src/payment_ledger.py",
    ]

    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "code-file: src/" in workflow
    assert "--baseline audit-baseline.json" in workflow
    assert "cp templates/payment-ledger-starter" not in workflow


def test_payment_starter_workflow_pins_and_fixture_smoke_are_explicit() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    action_pin = re.search(r"mumei-audit@(?<![0-9a-f])([0-9a-f]{40})(?![0-9a-f])", workflow)
    verifier_pin = re.search(
        r"raw\.githubusercontent\.com/mumei-lang/mumei-agent/([0-9a-f]{40})/"
        r"\.github/actions/mumei-audit/scripts/verify_audit_evidence_artifact\.py",
        workflow,
    )
    assert action_pin is not None
    assert verifier_pin is not None
    assert action_pin.group(1) == PIN
    assert verifier_pin.group(1) == PIN
    assert action_pin.group(1) == verifier_pin.group(1)
    assert "Keep this commit identical to the action pin above." in workflow
    job_names = re.findall(r"^  ([A-Za-z0-9_-]+):$", workflow.split("jobs:\n", 1)[1], re.M)
    assert job_names == ["audit", "verify-downloaded-evidence"]

    assert 'LLM_API_KEY: ""' in workflow
    assert 'OPENAI_API_KEY: ""' in workflow
    assert "migration-execution-output: .mumei-audit/migration_execution.json" in workflow
    assert "artifact-name: mumei-audit-evidence" in workflow
    assert "upload-sarif: false" in workflow
    assert re.search(r"^\s*security-events:", workflow, re.M) is None
    assert "actions: read" in workflow
    assert "contents: read" in workflow

    for flag in ("--require-hidden-companion", "--require-blocked-candidate", "--require-generated-mm"):
        assert flag in workflow
    assert "Fixture smoke only" in workflow
    assert "zero candidates" in workflow
    assert "outside the current verifier contract" in workflow
    assert 'candidates[0].get("function_name") == "split_cents"' in workflow
    assert 'candidates[0].get("execution_state") == "blocked"' in workflow
    assert 'execution.get("summary", {}).get("review_required") is True' in workflow
    assert "fake-unused-llm-key" not in workflow


def test_payment_starter_readme_preserves_review_and_evidence_boundaries() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert "evidence generation and review-handoff confirmation" in readme
    assert "does not mean the human migration review is complete" in readme
    assert "generated `.mm` acceptance evidence only" in readme
    assert "not proof that the host-language Python implements the same behavior" in readme
    assert "not a malicious-tamper trust anchor" in readme
    assert "does not independently re-run proof certificates" in readme
    assert "produced with migration execution output and baseline generation enabled" in readme
    assert "offline corruption/consistency check" in readme
    assert "permissions:\n  contents: read\n  security-events: write" in readme
    assert "keeps checkout access while adding code-scanning access" in readme
    assert "CI policy, not evidence" in readme
    assert "zero-candidate real-repository artifact is outside that verifier contract" in readme
    assert "removing only the strict flags is not enough" in readme
    assert "remove or gate the entire downloaded-artifact verification job" in readme
    assert "recipient_count > 0" in readme
    assert "integer-split remainder policy" in readme
    assert "account-existence, negative-amount, and non-negative-balance requirements" in readme
    assert "Exact bundle layout and trusted build-ID validation intentionally are not part of this starter" in readme


def test_payment_fixture_is_canonical_in_starter_and_docs_reference_it() -> None:
    old_fixture = REPO_ROOT / "scenarios" / "ci_evidence_pack" / "reference" / "payment_ledger.py"
    assert not old_fixture.exists()

    doc = (REPO_ROOT / "docs" / "CI_REFERENCE.md").read_text(encoding="utf-8")
    assert "templates/payment-ledger-starter/src/payment_ledger.py" in doc
    assert "templates/payment-ledger-starter/.github/workflows/mumei-audit.yml" in doc
    assert "evidence generation and review-handoff confirmation" in doc
    assert "Human migration review is not included" in doc
    assert "verification job also needs `actions: read`" in doc
    assert f"mumei-audit@{PIN}" in doc

    consumer = (REPO_ROOT / ".github" / "workflows" / "audit-action-consumer.yml").read_text(encoding="utf-8")
    assert "templates/payment-ledger-starter/src/payment_ledger.py" in consumer
    assert "- templates/payment-ledger-starter/**" in consumer
