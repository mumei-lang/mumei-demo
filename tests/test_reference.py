from __future__ import annotations

import argparse
import shutil
import subprocess

import pytest

from scripts.gen_reference import main as generate_main
from scripts.reference import (
    CLI_SCRIPTS,
    ENVIRONMENT_VARIABLES,
    INTERNAL_ENV_ALLOWLIST,
    REPO_ROOT,
    TEST_STUB_ENVIRONMENT_VARIABLES,
    _option_action_count,
    argparse_scripts,
    capture_parsers,
    environment_reads,
    make_targets,
    python_source_texts,
    render_reference,
)


def test_committed_reference_matches_render() -> None:
    assert (REPO_ROOT / "docs/REFERENCE.md").read_text(encoding="utf-8") == render_reference()


def test_render_is_independent_of_environment_defaults(monkeypatch) -> None:
    monkeypatch.setenv("MUMEI_BIN", "/tmp/x/mumei")
    monkeypatch.setenv("MUMEI_REPO", "/tmp/y")
    committed = (REPO_ROOT / "docs/REFERENCE.md").read_text(encoding="utf-8")
    assert render_reference() == committed


def test_generate_report_format_choices_are_rendered() -> None:
    assert "| `--format` | `{table, json, markdown}` |" in render_reference()


def test_check_rejects_tampered_copy(tmp_path, capsys) -> None:
    copy = tmp_path / "REFERENCE.md"
    copy.write_text("tampered", encoding="utf-8")
    assert generate_main(["--check"], reference_path=copy) == 1
    assert "out of date" in capsys.readouterr().err
    assert copy.read_text(encoding="utf-8") == "tampered"


def test_every_make_target_has_a_description() -> None:
    targets = make_targets()
    undocumented = [name for name, description in targets if not description]
    assert undocumented == []


def test_make_help_lists_every_described_target() -> None:
    make = shutil.which("make")
    if make is None:
        pytest.skip("make is not installed")
    result = subprocess.run(
        [make, "help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    output = result.stdout
    for name, description in make_targets():
        if description:
            assert name in output


def test_make_without_target_uses_demo_as_default() -> None:
    make = shutil.which("make")
    if make is None:
        pytest.skip("make is not installed")
    default = subprocess.run(
        [make, "-n", "SHELL=/bin/echo"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    explicit = subprocess.run(
        [make, "-n", "SHELL=/bin/echo", "demo"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert default.stdout == explicit.stdout
    assert "ownership_transfer" in default.stdout


def test_every_argparse_script_is_referenced() -> None:
    assert argparse_scripts() == {script_path for script_path, _ in CLI_SCRIPTS}


def test_environment_reads_are_documented_or_internal() -> None:
    registered = {name for name, _, _ in ENVIRONMENT_VARIABLES}
    _assert_environment_coverage(
        environment_reads(),
        registered,
        set(INTERNAL_ENV_ALLOWLIST),
    )
    assert set(TEST_STUB_ENVIRONMENT_VARIABLES) <= set(INTERNAL_ENV_ALLOWLIST)
    assert all(INTERNAL_ENV_ALLOWLIST[name] for name in TEST_STUB_ENVIRONMENT_VARIABLES)
    assert not any(
        name in render_reference()
        for name in TEST_STUB_ENVIRONMENT_VARIABLES
    )
    assert all(
        "specimens" not in path.relative_to(REPO_ROOT).parts
        for path, _ in python_source_texts()
    )


def _assert_environment_coverage(
    reads: set[str],
    registered: set[str],
    internal: set[str],
) -> None:
    classified = registered | internal
    assert reads <= classified, f"Unclassified environment reads: {sorted(reads - classified)}"
    assert classified <= reads, f"Stale environment declarations: {sorted(classified - reads)}"


def test_environment_coverage_rejects_stale_allowlist_entries() -> None:
    with pytest.raises(AssertionError, match="Stale environment declarations"):
        _assert_environment_coverage(
            {"CI_FIXTURE_MODE"},
            {"CI_FIXTURE_MODE"},
            {"FAKE_INTERNAL"},
        )


def test_option_count_counts_actions_not_aliases() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--quiet", action="store_true")
    assert _option_action_count(parser) == 1


def test_parser_option_strings_match_golden_lists() -> None:
    expected = {
        "scripts/generate_report.py": [
            "--format",
            "--summary",
            "--highlights",
            "--reports-dir",
            "--output",
            "--highlights-output",
            "--report-output",
            "--scenarios",
            "--require-all",
        ],
        "scripts/run_specimen_audits.py": [
            "--mumei-agent-repo",
            "--mumei-repo",
            "--mumei-bin",
            "--timeout",
            "--summary",
            "--scoreboard-dir",
            "--specimens-readme",
            "--top-readme",
            "--render-only",
            "--rescore",
        ],
        "scripts/run_baselines.py": [
            "--tools",
            "--semgrep-bin",
            "--bandit-bin",
            "--gosec-bin",
            "--slither-bin",
            "--clippy-bin",
            "--solc-bin",
            "--semgrep-rules",
            "--timeout",
            "--summary",
            "--scoreboard-dir",
        "--specimens-readme",
            "--rescore",
        ],
        "scripts/run_llm_only.py": [
            "--model",
            "--runs",
            "--jobs",
            "--only",
            "--timeout",
            "--summary",
            "--scoreboard-dir",
            "--rescore",
        ],
        "scripts/compare_arms.py": ["--model", "--check"],
        "scripts/run_contract_bench.py": ["--arm", "--only", "--runs", "--jobs", "--timeout", "--mumei-bin", "--check", "--render-only"],
        "scripts/run_native_replay.py": ["--check", "--mumei-bin", "--jobs", "--timeout"],
        "scripts/record_scenario.py": ["--variant", "--output"],
        "scripts/record_model_evidence.py": ["--repo", "--output"],
        "scripts/check_specimens.py": ["--root", "--run-fixed"],
        "scripts/check_evidence_regressions.py": ["--out-dir"],
        "scripts/review_charter_baseline.py": ["--base", "--out-dir"],
        "dashboard/cli_report.py": ["--all"],
    }
    for script_path, parser in capture_parsers():
        option_strings = [
            option
            for action in parser._actions
            if action.dest != "help"
            for option in action.option_strings
        ]
        assert option_strings == expected[script_path]
