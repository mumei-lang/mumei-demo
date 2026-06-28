#!/usr/bin/env python3
"""Validate scenario JSON contract vocabulary."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_FILES = [
    REPO_ROOT / "scenarios" / "spec_code_verification_suite" / "scenario.json",
    REPO_ROOT / "scenarios" / "no_mm_audit" / "scenario.json",
]
FIXED_ARTIFACT_KEYS = [
    "spec_health_issues",
    "verification_violations",
    "cross_validation_gaps",
    "next_steps",
    "migration_hints",
    "healed_files",
    "heal_errors",
]
FIXED_DEMO_PHRASES = [
    "既存コードを渡すだけでバグ箇所を指摘",
    "仕様から既存コードとの差分を指摘",
    "仕様単独でおかしい場合を指摘",
]
FORBIDDEN_ALIASES = [
    "recommendations",
    "actions",
    "audit_issues",
    "verification_gaps",
    "repair_hints",
    "review_actions",
    "human_review",
]
FORBIDDEN_ALIAS_PATTERNS = {
    alias: re.compile(rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])")
    for alias in FORBIDDEN_ALIASES
}


def _walk(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    items = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            items.extend(_walk(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            items.extend(_walk(child, f"{path}[{index}]"))
    return items


def _collect_named(value: Any, wanted_key: str, path: str = "$") -> list[tuple[str, Any]]:
    matches: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == wanted_key:
                matches.append((child_path, child))
            matches.extend(_collect_named(child, wanted_key, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(_collect_named(child, wanted_key, f"{path}[{index}]"))
    return matches


def _check_file(path: Path) -> list[str]:
    rel = path.relative_to(REPO_ROOT)
    data = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []

    if data.get("canonical_demo_phrases") != FIXED_DEMO_PHRASES:
        failures.append(f"{rel}: $.canonical_demo_phrases must match the fixed three public phrases")

    exact_artifact_key_fields = [
        ("$.artifact_keys", data.get("artifact_keys")),
        ("$.harness_contract.artifact_keys", data.get("harness_contract", {}).get("artifact_keys")),
    ]
    for key_path, value in exact_artifact_key_fields:
        if value != FIXED_ARTIFACT_KEYS:
            failures.append(f"{rel}: {key_path} must match the fixed no-.mm artifact key list")

    for key_path, value in _collect_named(data, "artifact_keys"):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            failures.append(f"{rel}: {key_path} must be a list of strings")
            continue
        for item in value:
            for alias, pattern in FORBIDDEN_ALIAS_PATTERNS.items():
                if pattern.search(item):
                    failures.append(f"{rel}: {key_path} contains forbidden alias `{alias}`")

    for json_path, value in _walk(data):
        if isinstance(value, dict):
            for key in value:
                for alias in FORBIDDEN_ALIASES:
                    if alias in key:
                        failures.append(f"{rel}: {json_path}.{key} contains forbidden alias `{alias}`")
        elif isinstance(value, str):
            for alias in FORBIDDEN_ALIASES:
                if alias in value:
                    failures.append(f"{rel}: {json_path} contains forbidden alias `{alias}`")
    return failures


def main() -> int:
    failures: list[str] = []
    for path in SCENARIO_FILES:
        failures.extend(_check_file(path))
    if failures:
        print("Scenario contract check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    checked = ", ".join(path.relative_to(REPO_ROOT).as_posix() for path in SCENARIO_FILES)
    print(f"Scenario contract check passed: {checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
