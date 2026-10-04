"""Tests for the Python heredoc embedded in scripts/run_scenario.sh."""
from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_scenario.sh"


def _load_functions(*names: str):
    """Extract `def` blocks from the `<<'PY'` heredoc and exec them."""
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("<<'PY'") + len("<<'PY'")
    end = text.index("\nPY\n", start)
    module = ast.parse(text[start:end])
    wanted = set(names)
    namespace: dict = {"Mapping": Mapping}
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            exec(compile(ast.Module(body=[node], type_ignores=[]), "<test>", "exec"), namespace)
    missing = wanted - namespace.keys()
    assert not missing, f"functions not found in run_scenario.sh heredoc: {missing}"
    return namespace


def test_generated_code_from_spec_has_no_return_statement():
    ns = _load_functions("generated_code_from_spec", "flatten_spec_text")
    spec = {
        "name": "safe_transfer",
        "inputs": [
            {"name": "sender_balance", "type": "i64"},
            {"name": "amount", "type": "i64"},
        ],
        "requires": "sender_balance >= amount",
        "ensures": "result == sender_balance - amount",
        "return_type": "i64",
    }
    code = ns["generated_code_from_spec"](spec)
    assert "return" not in code
    assert "sender_balance - amount" in code
