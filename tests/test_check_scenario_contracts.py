"""Tests for scripts/check_scenario_contracts.py docs alias checking."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_scenario_contracts import (
    FORBIDDEN_ALIAS_PATTERNS,
    _check_docs_forbidden_aliases,
    _in_code_fence,
    _is_key_context,
)


def test_is_key_context_backtick():
    assert _is_key_context("`recommendations`", "recommendations")
    assert _is_key_context("Use `audit_issues` key", "audit_issues")


def test_is_key_context_json_key():
    assert _is_key_context('"recommendations": [', "recommendations")
    assert _is_key_context("'actions': []", "actions")


def test_is_key_context_yaml_key():
    assert _is_key_context("- recommendations:", "recommendations")
    assert _is_key_context("  actions:", "actions")


def test_is_key_context_plain_prose_rejected():
    assert not _is_key_context(
        "We have some recommendations for improvement.", "recommendations"
    )
    assert not _is_key_context(
        "The next actions should be taken.", "actions"
    )


def test_is_key_context_array_notation():
    assert _is_key_context("recommendations[]", "recommendations")


def test_in_code_fence_detection():
    lines = [
        "normal text",
        "```json",
        '  "actions": []',
        "```",
        "normal again",
    ]
    assert not _in_code_fence(lines, 0)
    assert not _in_code_fence(lines, 1)
    assert _in_code_fence(lines, 2)
    assert _in_code_fence(lines, 3)
    assert not _in_code_fence(lines, 4)


def test_docs_check_detects_alias_in_code_fence(tmp_path, monkeypatch):
    doc = tmp_path / "test.md"
    doc.write_text(
        "# Title\n\n```json\n\"recommendations\": []\n```\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "check_scenario_contracts.DOCS_UNDER_CONTRACT", [doc]
    )
    monkeypatch.setattr("check_scenario_contracts.REPO_ROOT", tmp_path)
    failures = _check_docs_forbidden_aliases()
    assert len(failures) == 1
    assert "recommendations" in failures[0]


def test_docs_check_ignores_plain_prose(tmp_path, monkeypatch):
    doc = tmp_path / "test.md"
    doc.write_text(
        "# Title\n\nWe have some recommendations for the team.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "check_scenario_contracts.DOCS_UNDER_CONTRACT", [doc]
    )
    monkeypatch.setattr("check_scenario_contracts.REPO_ROOT", tmp_path)
    failures = _check_docs_forbidden_aliases()
    assert failures == []


def test_docs_check_detects_backtick_alias(tmp_path, monkeypatch):
    doc = tmp_path / "test.md"
    doc.write_text(
        "# Title\n\nUse `verification_gaps` for issues.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "check_scenario_contracts.DOCS_UNDER_CONTRACT", [doc]
    )
    monkeypatch.setattr("check_scenario_contracts.REPO_ROOT", tmp_path)
    failures = _check_docs_forbidden_aliases()
    assert len(failures) == 1
    assert "verification_gaps" in failures[0]
