from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER_DIR = REPO_ROOT / "templates" / "payment-ledger-starter"
WORKFLOW_PATH = STARTER_DIR / ".github" / "workflows" / "mumei-audit.yml"
README_PATH = STARTER_DIR / "README.md"
PIN = "a81df80072acf2ed5739b7e4c2f09bfb4129e60d"


def _audit_uses_match(line: str) -> re.Match[str] | None:
    return re.match(
        r"^(\s*)(?:-\s+)?uses:\s*mumei-lang/mumei-agent/\.github/actions/mumei-audit@([^\s#]+)(?:\s+#.*)?\s*$",
        line,
    )


def _audit_action_ref(text: str) -> re.Match[str] | None:
    for line in text.splitlines():
        match = _audit_uses_match(line)
        if match:
            return match
    return None


def _audit_action_inputs(text: str) -> dict[str, str]:
    """Return inputs scoped to the audit action step's `with` block."""
    lines = text.splitlines()
    for uses_index, line in enumerate(lines):
        uses_match = _audit_uses_match(line)
        if not uses_match:
            continue

        key_indent = len(uses_match.group(1))
        inline_step = line[key_indent:].startswith("- ")
        if inline_step:
            key_indent += 2
            step_start = uses_index
            step_indent = len(uses_match.group(1))
        else:
            step_start = uses_index
            step_indent = key_indent
            for position in range(uses_index - 1, -1, -1):
                stripped = lines[position].strip()
                if not stripped or stripped.startswith("#"):
                    continue
                indent = len(lines[position]) - len(lines[position].lstrip())
                if indent < key_indent and stripped.startswith("-"):
                    step_start = position
                    step_indent = indent
                    break
                if indent < key_indent:
                    break

        step_end = len(lines)
        for position in range(uses_index + 1, len(lines)):
            stripped = lines[position].strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(lines[position]) - len(lines[position].lstrip())
            if indent <= step_indent:
                step_end = position
                break

        inputs: dict[str, str] = {}
        for position in range(step_start, step_end):
            stripped = lines[position].strip()
            if stripped != "with:":
                continue
            indent = len(lines[position]) - len(lines[position].lstrip())
            if indent != key_indent:
                continue
            for input_line in lines[position + 1 : step_end]:
                stripped_input = input_line.strip()
                if not stripped_input or stripped_input.startswith("#"):
                    continue
                input_indent = len(input_line) - len(input_line.lstrip())
                if input_indent <= key_indent:
                    break
                match = re.match(r"([A-Za-z0-9_-]+):\s*(.*)$", stripped_input)
                if match:
                    inputs[match.group(1)] = match.group(2).strip()
            break
        return inputs
    return {}


def _workflow_input(text: str, key: str) -> str | None:
    return _audit_action_inputs(text).get(key)


def _copied_files(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())


def _copy_starter(destination: Path) -> None:
    shutil.copytree(STARTER_DIR, destination, dirs_exist_ok=True)


def validate_starter_copy(root: Path) -> None:
    """Validate the copied starter shape and targeted consumer-input contract.

    This is intentionally targeted text/shape validation, not YAML semantic
    equivalence or GitHub Actions emulation.
    """
    assert _copied_files(root) == [
        ".github/workflows/mumei-audit.yml",
        "README.md",
        "audit-baseline.json",
        "src/payment_ledger.py",
    ]

    baseline = json.loads((root / "audit-baseline.json").read_text(encoding="utf-8"))
    assert baseline == {"version": "mumei.audit-baseline/v1", "fingerprints": []}

    workflow_path = root / ".github" / "workflows" / "mumei-audit.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    action_ref = _audit_action_ref(workflow)
    verifier_pin = re.search(
        r"raw\.githubusercontent\.com/mumei-lang/mumei-agent/([0-9a-f]{40})/"
        r"\.github/actions/mumei-audit/scripts/verify_audit_evidence_artifact\.py",
        workflow,
    )
    assert action_ref is not None
    assert verifier_pin is not None
    assert re.fullmatch(r"[0-9a-f]{40}", action_ref.group(2)), "action pin must be immutable"
    assert action_ref.group(2) == verifier_pin.group(1), "action and verifier pins diverged"
    assert action_ref.group(2) == PIN

    consumer = (REPO_ROOT / ".github" / "workflows" / "audit-action-consumer.yml").read_text(encoding="utf-8")
    for key in (
        "code-file",
        "language",
        "mumei-version",
        "audit-args",
        "migration-execution-output",
        "artifact-name",
        "upload-sarif",
    ):
        starter_value = _workflow_input(workflow, key)
        consumer_value = _workflow_input(consumer, key)
        assert starter_value is not None, f"starter audit input missing: {key}"
        assert consumer_value is not None, f"canonical consumer input missing: {key}"
        assert starter_value == consumer_value, f"consumer input drift: {key}"

    assert 'LLM_API_KEY: ""' in workflow
    assert 'OPENAI_API_KEY: ""' in workflow
    assert "contents: read" in workflow
    assert "actions: read" in workflow
    assert re.search(r"^\s*security-events:", workflow, re.M) is None
    for fragment in (
        "--require-hidden-companion",
        "--require-blocked-candidate",
        "--require-generated-mm",
        "Fixture smoke only",
        "zero candidates",
        "--allow-zero-candidates",
        "instead of dropping artifact verification",
    ):
        assert fragment in workflow

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file()
    )
    assert "fake-unused-llm-key" not in combined
    assert re.search(r"(?i)(?:password|secret|token|api[_-]?key)[\w-]*\s*[:=]\s*[\"'][^\"'\s]{8,}", combined) is None


def test_payment_starter_copy_shape_and_targeted_inputs_survive_repo_root_copy(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _copy_starter(consumer)
    validate_starter_copy(consumer)


def test_payment_starter_copy_harness_tolerates_step_key_order_and_pin_comment(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _copy_starter(consumer)
    workflow_path = consumer / ".github" / "workflows" / "mumei-audit.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    lines = workflow.splitlines()
    uses_index = next(index for index, line in enumerate(lines) if f"uses: mumei-lang/mumei-agent/.github/actions/mumei-audit@{PIN}" in line)
    key_indent = len(lines[uses_index]) - len(lines[uses_index].lstrip())
    id_index = next(index for index in range(uses_index - 1, -1, -1) if lines[index].strip() == "id: audit")
    with_index = next(index for index in range(uses_index + 1, len(lines)) if lines[index].strip() == "with:")
    with_end = len(lines)
    for position in range(with_index + 1, len(lines)):
        stripped = lines[position].strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(lines[position]) - len(lines[position].lstrip())
        if indent <= key_indent:
            with_end = position
            break

    uses_line = lines[uses_index] + "  # immutable reference"
    mutated_lines = (
        lines[:id_index]
        + lines[with_index:with_end]
        + [uses_line]
        + lines[id_index:uses_index]
        + lines[uses_index + 1 : with_index]
        + lines[with_end:]
    )
    workflow_path.write_text("\n".join(mutated_lines) + "\n", encoding="utf-8")

    validate_starter_copy(consumer)


def test_payment_starter_copy_harness_rejects_pin_mismatch(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _copy_starter(consumer)
    workflow_path = consumer / ".github" / "workflows" / "mumei-audit.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    workflow_path.write_text(workflow.replace(f"mumei-audit@{PIN}", "mumei-audit@0123456789abcdef0123456789abcdef01234567"), encoding="utf-8")

    with pytest.raises(AssertionError, match="pins diverged"):
        validate_starter_copy(consumer)


def test_payment_starter_copy_harness_rejects_hidden_github_loss(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _copy_starter(consumer)
    shutil.rmtree(consumer / ".github")

    with pytest.raises(AssertionError):
        validate_starter_copy(consumer)


def test_payment_starter_copy_harness_rejects_audit_args_drift(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _copy_starter(consumer)
    workflow_path = consumer / ".github" / "workflows" / "mumei-audit.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    workflow_path.write_text(workflow.replace("--fail-on high-confidence", "--fail-on medium"), encoding="utf-8")

    with pytest.raises(AssertionError, match="consumer input drift: audit-args"):
        validate_starter_copy(consumer)


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
    assert "--allow-zero-candidates" in workflow
    assert "instead of dropping artifact verification" in workflow
    assert 'candidates[0].get("function_name") == "split_cents"' in workflow
    assert 'candidates[0].get("execution_state") == "blocked"' in workflow
    assert 'execution.get("summary", {}).get("review_required") is True' in workflow
    assert "fake-unused-llm-key" not in workflow


def test_payment_starter_readme_preserves_review_and_evidence_boundaries() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert "evidence generation and review-handoff confirmation" in readme
    assert "does not mean the human migration review is complete" in readme
    assert "cp -a templates/payment-ledger-starter/. /path/to/consumer-repo/" in readme
    assert ".github/workflows/mumei-audit.yml" in readme
    assert "hidden by default" in readme
    assert "canonical detailed reference" in readme
    assert "consumer workstation does not need Rust, Z3, LLVM, or sibling `mumei` repositories" in readme
    assert "`make setup` in `mumei-demo` is maintainer setup" in readme
    assert "no non-suppressed high-confidence code evidence failed the gate" in readme
    assert "Audit exit `1` is finding-policy failure" in readme
    assert "positive-path fixture smoke" in readme
    assert "root `generated-baseline.json` entry" in readme
    assert "does not update the committed input baseline automatically" in readme
    assert "runner/workspace provenance, not portable links" in readme
    assert "generated `.mm` acceptance evidence only" in readme
    assert "not proof that the host-language Python implements the same behavior" in readme
    assert "not a malicious-tamper trust anchor" in readme
    assert "does not establish artifact producer authenticity" in readme
    assert "does not prove host-language semantic equivalence" in readme
    assert "does not independently re-run proof certificates" in readme
    assert "otherwise guarantee proof correctness" in readme
    assert "produced with migration execution output and baseline generation enabled" in readme
    assert "offline corruption/consistency check" in readme
    assert "permissions:\n  contents: read\n  security-events: write" in readme
    assert "keeps checkout access while adding code-scanning access" in readme
    assert "CI policy, not evidence" in readme
    assert "add `--allow-zero-candidates`" in readme
    assert "preserves artifact envelope, zero-count, schema, boundary, provenance, companion, hidden-file, and configured forbidden-literal validation" in readme
    assert "an empty candidate list has no generated `.mm` candidate claims" in readme
    assert "nonzero candidate claims remain path/hash validated" in readme
    assert "Do not interpret zero candidates as proof failure or proof success" in readme
    assert "recipient_count > 0" in readme
    assert "integer-split remainder policy" in readme
    assert "account-existence, negative-amount, and non-negative-balance requirements" in readme
    assert "Exact bundle layout and trusted build-ID validation intentionally are not part of this starter" in readme
    assert "fresh consumer pilot runbook" in readme
    assert "dedicated private throwaway repository" in readme
    assert "does not run on the initial `main` push alone" in readme


def test_payment_fixture_is_canonical_in_starter_and_docs_reference_it() -> None:
    old_fixture = REPO_ROOT / "scenarios" / "ci_evidence_pack" / "reference" / "payment_ledger.py"
    assert not old_fixture.exists()

    doc = (REPO_ROOT / "docs" / "CI_REFERENCE.md").read_text(encoding="utf-8")
    assert "templates/payment-ledger-starter/src/payment_ledger.py" in doc
    assert "templates/payment-ledger-starter/.github/workflows/mumei-audit.yml" in doc
    assert "evidence generation and review-handoff confirmation" in doc
    assert "Human migration review is not included" in doc
    assert "verification job also needs `actions: read`" in doc
    assert "cp -a templates/payment-ledger-starter/. /path/to/consumer-repo/" in doc
    assert "consumer workstation does not need Rust, Z3, LLVM, or sibling `mumei` repositories" in doc
    assert "not a consumer prerequisite" in doc
    assert "positive-path fixture smoke" in doc
    assert "does not establish artifact producer authenticity" in doc
    assert "otherwise guarantee proof correctness" in doc
    assert "does not update the committed input baseline automatically" in doc
    assert f"mumei-audit@{PIN}" in doc
    for fragment in (
        "## Fresh consumer pilot runbook",
        "pushing the starter to `main` alone does not trigger",
        "listens only to `pull_request`",
        "empty private throwaway repository",
        "sandbox owner controlled by the pilot operator",
        "actions/setup-python@v7",
        "astral-sh/setup-uv@v5",
        "actions/upload-artifact@v4",
        "github/codeql-action/upload-sarif@v3",
        "strict allowlist policies may therefore need those entries too",
        "does not run when `upload-sarif` is false",
        "no secrets",
        "Branch protection is not required",
        "exactly the starter shape",
        "setup/audit/total seconds",
        "artifact entries and size",
        "generated-baseline entry count",
        "cold or a rerun",
        "`audit_exit_code=0`",
        "not skipped and succeeds",
        "candidate `operational_error` count is zero",
        "does not mean there were no findings",
        "passing `--allow-zero-candidates` together with `--require-hidden-companion`",
        "zero count consistency, companion copy count, hidden companion round trip",
        "omit `--allow-zero-candidates`",
        "delete or archive the throwaway repository",
        "host-language semantic equivalence",
        "artifact producer authenticity",
        "proof correctness",
        "SARIF/code scanning upload",
        "ten-minute completion guarantee",
        "`workflow_dispatch`",
    ):
        assert fragment in doc

    consumer = (REPO_ROOT / ".github" / "workflows" / "audit-action-consumer.yml").read_text(encoding="utf-8")
    assert "templates/payment-ledger-starter/src/payment_ledger.py" in consumer
    assert "- templates/payment-ledger-starter/**" in consumer


def test_payment_starter_copy_harness_rejects_mutable_action_ref(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _copy_starter(consumer)
    workflow_path = consumer / ".github" / "workflows" / "mumei-audit.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    workflow_path.write_text(
        workflow.replace(
            f"uses: mumei-lang/mumei-agent/.github/actions/mumei-audit@{PIN}",
            f"# stale comment mumei-audit@{PIN}\n"
            "        uses: mumei-lang/mumei-agent/.github/actions/mumei-audit@develop",
        ),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="immutable"):
        validate_starter_copy(consumer)


def test_payment_starter_copy_harness_rejects_input_moved_outside_audit_step(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _copy_starter(consumer)
    workflow_path = consumer / ".github" / "workflows" / "mumei-audit.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    mutated = workflow.replace("          language: python\n", "")
    mutated = mutated.replace("  verify-downloaded-evidence:", "    language: python\n\n  verify-downloaded-evidence:")
    workflow_path.write_text(mutated, encoding="utf-8")

    with pytest.raises(AssertionError, match="starter audit input missing: language"):
        validate_starter_copy(consumer)


def test_payment_starter_copy_harness_rejects_secret_looking_literal(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _copy_starter(consumer)
    readme = consumer / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + '\nexample_token = "not-a-real-token"\n', encoding="utf-8")

    with pytest.raises(AssertionError):
        validate_starter_copy(consumer)
