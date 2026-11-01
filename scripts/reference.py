from __future__ import annotations

import argparse
import ast
import importlib
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DASHBOARD_DIR = REPO_ROOT / "dashboard"
CLI_SCRIPTS = (
    ("scripts/generate_report.py", "generate_report"),
    ("scripts/run_specimen_audits.py", "run_specimen_audits"),
    ("scripts/run_baselines.py", "run_baselines"),
    ("scripts/record_scenario.py", "record_scenario"),
    ("scripts/record_model_evidence.py", "record_model_evidence"),
    ("scripts/check_specimens.py", "check_specimens"),
    ("scripts/check_evidence_regressions.py", "check_evidence_regressions"),
    ("scripts/review_charter_baseline.py", "review_charter_baseline"),
    ("dashboard/cli_report.py", "cli_report"),
)
ENVIRONMENT_VARIABLES = (
    (
        "CI_FIXTURE_MODE",
        "Make default: `1`; direct runner: unset",
        "Enables recorded fixtures when exactly `1`; `make demo-ci` always selects fixture mode.",
    ),
    (
        "MUMEI_REPO",
        "`../mumei` sibling checkout",
        "Read from repos.env, then the process environment; otherwise resolves the sibling checkout.",
    ),
    (
        "MUMEI_AGENT_REPO",
        "`../mumei-agent` sibling checkout",
        "Read from repos.env, then the process environment; otherwise resolves the sibling checkout.",
    ),
    (
        "MUMEI_LEAN_REPO",
        "`../mumei-lean` sibling checkout",
        "Read from repos.env, then the process environment; otherwise resolves the sibling checkout.",
    ),
    (
        "MUMEI_BIN",
        "release binary, otherwise debug binary under MUMEI_REPO",
        "Read from repos.env, then the process environment; direct audit options can override it.",
    ),
    (
        "MUMEI_AGENT_PYTHON",
        "agent .venv/bin/python, otherwise python on PATH or the current interpreter",
        "Read from repos.env, then the process environment, before choosing an available Python.",
    ),
    (
        "NL_REQUIREMENTS_FILE",
        "`spec_text.md`",
        "Read from repos.env, then the process environment; selects the natural-language requirements input.",
    ),
)
TEST_STUB_ENVIRONMENT_VARIABLES = (
    "MUMEI_STUB_CHARTER_EXIT",
    "MUMEI_STUB_CHARTER_STDOUT",
    "MUMEI_STUB_CLAIMS_EXIT",
    "MUMEI_STUB_CLAIMS_MARKER",
    "MUMEI_STUB_CLAIMS_MODE",
    "MUMEI_STUB_CLAIMS_STDERR",
    "MUMEI_STUB_CONTROLS_EXIT",
    "MUMEI_STUB_CONTROLS_STDOUT",
    "MUMEI_STUB_FIXTURE_DIR",
    "MUMEI_STUB_OBSERVE_EXIT",
    "MUMEI_STUB_OBSERVE_REPORT",
    "MUMEI_STUB_VERIFY_EXIT",
)
INTERNAL_ENV_ALLOWLIST = {
    **{
        name: "Test-only child-process controls; not user configuration."
        for name in TEST_STUB_ENVIRONMENT_VARIABLES
    },
    "LLM_API_KEY": "Credential presence is checked for audit metadata; the value is not reported.",
    "MUMEI_STD_PATH": "Internal child-process override for the Mumei standard-library path.",
    "OPENAI_API_KEY": "Credential presence is checked for audit metadata; the value is not reported.",
}


@contextmanager
def _neutralized_environment():
    names = {name for name, _, _ in ENVIRONMENT_VARIABLES} | set(INTERNAL_ENV_ALLOWLIST)
    saved = {name: os.environ[name] for name in names if name in os.environ}
    for name in names:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        for name in names:
            os.environ.pop(name, None)
        os.environ.update(saved)


MAKE_VARIABLES = (
    "MUMEI_REPO",
    "MUMEI_AGENT_REPO",
    "SCENARIOS",
    "SCALE_SCENARIOS",
    "OPTIONAL_SCENARIOS",
    "NO_MM_AUDIT_LANGUAGES",
)
SCENARIO_LISTS = {
    "SCENARIOS": "Default sequence used by `demo` and `demo-ci`.",
    "SCALE_SCENARIOS": "Large-scale scenarios, separate from the default CI sequence.",
    "OPTIONAL_SCENARIOS": "Optional scenarios kept outside the default sequence.",
}
MAKE_VARIABLE_DESCRIPTIONS = {
    "MUMEI_REPO": "Default sibling Mumei checkout; a Make command-line assignment can override it.",
    "MUMEI_AGENT_REPO": "Default sibling mumei-agent checkout; a Make command-line assignment can override it.",
    "NO_MM_AUDIT_LANGUAGES": "Languages included by the no-.mm audit target.",
}
EXCLUDED_SOURCE_PARTS = {
    ".cache",
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "specimens",
    "target",
    "venv",
}


def _markdown_cell(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())


def _makefile_text() -> str:
    return (REPO_ROOT / "Makefile").read_text(encoding="utf-8")


def make_targets() -> list[tuple[str, str | None]]:
    targets = []
    for line in _makefile_text().splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*:(.*)$", line)
        if not match or match.group(1).startswith("."):
            continue
        rest = match.group(2)
        if rest.startswith(("=", "?", "+", "!")):
            continue
        description = re.search(r"##\s*(.*)$", rest)
        targets.append(
            (match.group(1), description.group(1).strip() if description else None)
        )
    return targets


def make_variables() -> dict[str, str]:
    variables = {}
    assignment = re.compile(r"^([A-Z][A-Z0-9_]*)\s*(?::=|\?=)\s*(.*?)\s*$")
    for line in _makefile_text().splitlines():
        match = assignment.match(line)
        if match:
            variables[match.group(1)] = match.group(2)
    return variables


def _visible_actions(parser: argparse.ArgumentParser):
    return [
        action
        for action in parser._actions
        if action.dest != "help" and action.help != argparse.SUPPRESS
    ]


def _option_strings(action: argparse.Action) -> str:
    options = action.option_strings or [action.dest]
    return ", ".join(f"`{_markdown_cell(option)}`" for option in options)


def _value_placeholder(action: argparse.Action) -> str:
    if action.choices is not None:
        choices = action.choices
        if isinstance(choices, (set, frozenset)):
            choices = sorted(choices, key=str)
        label = "{" + ", ".join(str(choice) for choice in choices) + "}"
        return f"`{_markdown_cell(label)}`"
    if action.option_strings and action.nargs == 0:
        return "—"
    name = action.metavar or action.dest.upper()
    if isinstance(name, tuple):
        name = " ".join(str(item) for item in name)
    placeholder = f"<{name}>"
    if action.nargs in {"*", "+"}:
        placeholder += "..."
    elif isinstance(action.nargs, int) and action.nargs > 1:
        placeholder += f" × {action.nargs}"
    return f"`{_markdown_cell(placeholder)}`"


def _required(action: argparse.Action) -> str:
    if action.option_strings:
        return "yes" if action.required else "no"
    return "no" if action.nargs in {"?", "*"} else "yes"


def _format_default(action: argparse.Action) -> str:
    value = action.default
    if value is None or value is argparse.SUPPRESS:
        return "—"
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    if isinstance(value, (list, tuple)):
        if action.dest == "scenarios":
            return f"`SCENARIO_ORDER` ({len(value)} names)"
        return f"`{_markdown_cell(', '.join(str(item) for item in value))}`"
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str) and Path(value).is_absolute():
        value = os.path.relpath(value, REPO_ROOT)
    return f"`{_markdown_cell(str(value))}`"


def capture_parsers() -> list[tuple[str, argparse.ArgumentParser]]:
    for directory in (REPO_ROOT, SCRIPTS_DIR, DASHBOARD_DIR):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    with _neutralized_environment():
        captured = []
        for script_path, module_name in CLI_SCRIPTS:
            module = importlib.import_module(module_name)
            captured.append((script_path, module.build_parser()))
        return captured


def _parser_description(parser: argparse.ArgumentParser) -> str:
    return _markdown_cell(parser.description or "—")


def _option_action_count(parser: argparse.ArgumentParser) -> int:
    return sum(bool(action.option_strings) for action in _visible_actions(parser))


def _render_cli() -> list[str]:
    lines = [
        "| Script | Option count | Description |",
        "|---|---:|---|",
    ]
    parsers = capture_parsers()
    for script_path, parser in parsers:
        option_count = _option_action_count(parser)
        lines.append(
            f"| `{script_path}` | {option_count} | "
            f"{_parser_description(parser)} |"
        )
    for script_path, parser in parsers:
        lines.extend(
            [
                "",
                f"### `{script_path}`",
                "",
                _parser_description(parser),
                "",
                "| Option | Value | Required | Default | Description |",
                "|---|---|---|---|---|",
            ]
        )
        for action in _visible_actions(parser):
            help_text = _markdown_cell(action.help or "—")
            lines.append(
                f"| {_option_strings(action)} | {_value_placeholder(action)} | "
                f"{_required(action)} | {_format_default(action)} | {help_text} |"
            )
    return lines


def _render_make_targets() -> list[str]:
    lines = [
        "| Target | Description |",
        "|---|---|",
    ]
    for target, description in make_targets():
        lines.append(
            f"| `{target}` | {_markdown_cell(description or '—')} |"
        )
    return lines


def _render_make_variables() -> list[str]:
    variables = make_variables()
    lines = [
        "| Variable | Default or values | Description |",
        "|---|---|---|",
    ]
    for name in MAKE_VARIABLES:
        value = variables.get(name, "")
        if name in SCENARIO_LISTS:
            entries = value.split()
            rendered_value = (
                f"{len(entries)} scenarios: "
                + ", ".join(f"`{entry}`" for entry in entries)
            )
            description = SCENARIO_LISTS[name]
        elif name == "NO_MM_AUDIT_LANGUAGES":
            entries = value.split()
            rendered_value = ", ".join(f"`{entry}`" for entry in entries)
            description = MAKE_VARIABLE_DESCRIPTIONS[name]
        else:
            rendered_value = f"`{value}`"
            description = MAKE_VARIABLE_DESCRIPTIONS[name]
        lines.append(
            f"| `{name}` | {rendered_value} | {_markdown_cell(description)} |"
        )
    return lines


def _render_environment() -> list[str]:
    lines = [
        "| Variable | Default or fallback | Description |",
        "|---|---|---|",
    ]
    for name, default, description in ENVIRONMENT_VARIABLES:
        lines.append(
            f"| `{name}` | {_markdown_cell(default)} | "
            f"{_markdown_cell(description)} |"
        )
    return lines


def render_reference() -> str:
    lines = [
        "<!-- Generated by `./scripts/gen_reference.py`; do not edit by hand. -->",
        "",
        "# Repository Reference",
        "",
        "Generated from the Makefile, argparse definitions, and environment registry.",
        "",
        "## Make targets",
        "",
        *_render_make_targets(),
        "",
        "## Make variables",
        "",
        *_render_make_variables(),
        "",
        "Scenario names and counts reflect the Makefile lists; optional and large-scale "
        "scenarios remain outside the default sequence.",
        "",
        "## CLI options",
        "",
        *_render_cli(),
        "",
        "## Environment variables",
        "",
        *_render_environment(),
        "",
    ]
    return "\n".join(lines)


def python_source_texts() -> list[tuple[Path, str]]:
    sources = []
    for path in REPO_ROOT.rglob("*.py"):
        relative = path.relative_to(REPO_ROOT)
        if EXCLUDED_SOURCE_PARTS.intersection(relative.parts):
            continue
        source = path.read_text(encoding="utf-8")
        sources.append((path, source))
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "write_text"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and "os.environ" in node.args[0].value
            ):
                sources.append((path, node.args[0].value))

    runner = SCRIPTS_DIR / "run_scenario.sh"
    shell_text = runner.read_text(encoding="utf-8")
    embedded = re.search(
        r"(?ms)^python3 - .*?<<'PY'\n(.*?)^PY\s*$",
        shell_text,
    )
    if embedded:
        sources.append((runner, embedded.group(1)))
    return sources


def _is_os_environ(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _literal_strings(node: ast.AST) -> set[str]:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return set()
    return {
        item.value
        for item in node.elts
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }


def environment_reads() -> set[str]:
    names = set()
    for path, source in python_source_texts():
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        literal_bindings = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                values = _literal_strings(value)
                for target in targets:
                    if isinstance(target, ast.Name) and values:
                        literal_bindings[target.id] = values
            elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                values = _literal_strings(node.iter)
                if isinstance(node.iter, ast.Name):
                    values.update(literal_bindings.get(node.iter.id, set()))
                if values:
                    literal_bindings[node.target.id] = values

        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and _is_os_environ(node.value):
                index = node.slice
                if isinstance(index, ast.Constant) and isinstance(index.value, str):
                    names.add(index.value)
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            is_environment_get = (
                isinstance(function, ast.Attribute)
                and function.attr in {"get", "getenv"}
                and (
                    _is_os_environ(function.value)
                    or isinstance(function.value, ast.Name)
                    and function.value.id == "os"
                    and function.attr == "getenv"
                )
            ) or isinstance(function, ast.Name) and function.id == "getenv"
            if not is_environment_get or not node.args:
                continue
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                names.add(argument.value)
            elif isinstance(argument, ast.Name):
                names.update(literal_bindings.get(argument.id, set()))
    return names


def argparse_scripts() -> set[str]:
    discovered = set()
    roots = (SCRIPTS_DIR, DASHBOARD_DIR)
    for root in roots:
        for path in root.rglob("*.py"):
            relative = path.relative_to(REPO_ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            if any(
                isinstance(node, ast.Call)
                and (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "ArgumentParser"
                    or isinstance(node.func, ast.Attribute)
                    and node.func.attr == "ArgumentParser"
                )
                for node in ast.walk(tree)
            ):
                discovered.add(relative)
    return discovered
