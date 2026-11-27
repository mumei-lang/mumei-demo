#!/usr/bin/env python3
"""Shared syntactic intent-fidelity lint and replay outcome classification.

This module is deliberately independent of the contract benchmark implementation
so the benchmark, the divergence report and the adversarial corpus checker all use
the same detector without importing each other.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from mumei_verify import verify_text

STRING = r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`[^`]*`"""
INDEX = r"(?:\b\w+|\]|\))\s*\["
DIVIDE = r"(?<=[\w\])])\s*(?:/|%)"
NARROW = r"\bas\s+[iu](?:8|16|32)\b|\bu?int(" + "|".join(map(str, range(8, 256, 8))) + r")\s*\("


def scrub(text: str, language: str = "mumei") -> str:
    if language == "python":
        pattern = r"""(?s:"{3}.*?"{3}|'{3}.*?'{3})|\#[^\n]*|""" + STRING
    else:
        pattern = STRING + r"|//[^\n]*|(?s:/\*.*?\*/)"
    return re.sub(pattern, " ", text)


def usable_body(body: object) -> bool:
    if not isinstance(body, str) or not body.strip():
        return False
    tokens = scrub(body)
    if re.search(r"\b(?:atom|import|trusted)\b", tokens):
        return False
    depth = 0
    for char in tokens:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def field_value_paths(body: str, field: str) -> set[tuple]:
    """Collect struct-field expressions with the enclosing if/else predicates."""
    tokens = re.findall(r"\w+|[^\s]", body)
    braces = {}
    stack = []
    for i, token in enumerate(tokens):
        if token == "{":
            stack.append(i)
        elif token == "}" and stack:
            braces[stack.pop()] = i

    flags = set()

    def branch(i: int, end: int, path: tuple) -> int:
        if i >= end:
            return i
        if tokens[i] == "if":
            start = next((j for j in range(i + 1, end) if tokens[j] in ("{", ";")), end)
            if start not in braces:
                return i + 1
            predicate = tuple(tokens[i + 1:start])
            close = braces[start]
            scan(start + 1, close, (*path, (predicate, True)))
            after = close + 1
            if after < end and tokens[after] == "else":
                return branch(after + 1, end, (*path, (predicate, False)))
            return after
        if i in braces:
            scan(i + 1, braces[i], path)
            return braces[i] + 1
        return i + 1

    def scan(i: int, end: int, path: tuple) -> None:
        while i < end:
            if tokens[i:i + 2] == [field, ":"]:
                start = i + 2
                i = start
                depth = 0
                while i < end:
                    token = tokens[i]
                    if (token == "," or token == "}") and depth == 0:
                        break
                    depth += (token in ("(", "[", "{")) - (token in (")", "]", "}"))
                    i += 1
                flags.add((path, tuple(tokens[start:i])))
            else:
                i = branch(i, end, path)

    scan(0, len(tokens), ())
    return flags


def success_flag_paths(body: str) -> set[tuple]:
    """Collect explicit ok expressions with the enclosing if/else predicates."""
    return field_value_paths(body, "ok")


def _path_sensitive_expr(expr: tuple[str, ...], path: tuple) -> tuple[str, ...]:
    """Simplify a boolean expression known from its enclosing branch predicate."""
    for predicate, positive in path:
        if expr == predicate:
            return ("true",) if positive else ("false",)
    return expr


def _struct_fields(text: str) -> set[str]:
    return set(re.findall(r"\b(\w+)\s*:", text)) - {"ok"}


def _has_folded_state_field(reference: str, port: str) -> bool:
    """A branch-dependent non-ok field was collapsed to one branch's value.

    This is intentionally narrow: the port must have one unconditional field
    expression, the reference must have branch-dependent differing expressions,
    and the unconditional expression must exactly match one reference branch.
    That shape is high-confidence meaning loss rather than a style difference.
    """
    for field in _struct_fields(reference) | _struct_fields(port):
        reference_entries = field_value_paths(reference, field)
        port_entries = field_value_paths(port, field)
        if len(port_entries) != 1 or len(reference_entries) < 2:
            continue
        (port_path, port_expr), = port_entries
        reference_exprs = {_path_sensitive_expr(expr, path) for path, expr in reference_entries if path}
        if not port_path and all(path for path, _ in reference_entries):
            if len(reference_exprs) >= 2 and port_expr in reference_exprs:
                return True
    return False


def body_inner(text: str) -> str:
    """Inner statements of a complete port body, or ``text`` when already inner."""
    start = text.find("body:")
    if start < 0:
        return text
    opening = text.find("{", start)
    closing = text.rfind("}")
    if opening < 0 or closing <= opening:
        return text
    return text[opening + 1:closing]


def token_pattern(text: str) -> tuple[str, ...]:
    """Whitespace/comment-insensitive token shape used for conservative comparisons."""
    return tuple(re.findall(r"\w+|[^\s]", scrub(text)))


VARIANTS = ("buggy", "fixed")
DETECTOR_VERSION = 13


def split_port(text: str, atom: str) -> tuple[str, str, str] | None:
    """(prelude, header, body) of a port whose last atom is `atom`; header ends before `body:`."""
    m = re.search(rf"^(?:trusted\s+)?atom\s+{re.escape(atom)}\s*\(", text, re.M)
    if not m:
        return None
    b = text.find("body:", m.start())
    if b < 0:
        return None
    return text[:m.start()], text[m.start():b], text[b:]


def header_ensures(header: str) -> str | None:
    m = re.search(r"^\s*ensures:\s*(.*);\s*$", header, re.M)
    return m.group(1) if m else None


def assemble(case: dict, body: str) -> str:
    return case["prelude"] + case["header"] + "body: {\n" + body.rstrip() + "\n    }\n"


def _reference_inner(case: dict, variant: str) -> str | None:
    text = case.get("ports", {}).get(variant)
    if not isinstance(text, str):
        return None
    parts = split_port(text, case["atom"])
    return body_inner(parts[2]) if parts else None


def _silent_repair(case: dict, body: str, variant: str = "buggy") -> bool:
    """A buggy candidate exactly follows the fixed reference body instead of the buggy one.

    This is deliberately exact after comment/string scrubbing and tokenization.  A
    looser similarity score would make ordinary correct translations noisy; the
    adversarial corpus pins the high-confidence case and future detectors can widen
    it behind the same finding kind.  A fixed candidate copying the fixed reference
    is correct, so the finding exists only for the buggy variant.
    """
    if variant != "buggy":
        return False
    buggy = _reference_inner(case, "buggy")
    fixed = _reference_inner(case, "fixed")
    if buggy is None or fixed is None:
        return False
    buggy_tokens = token_pattern(buggy)
    fixed_tokens = token_pattern(fixed)
    return fixed_tokens != buggy_tokens and token_pattern(body) == fixed_tokens


def _trivial_clause(text: str) -> bool:
    compact = re.sub(r"[\s()]+", "", text).removesuffix(";")
    return compact in {"", "true", "result==result"}


def _top_level_conjuncts(text: str) -> list[str]:
    text = _strip_wrapping_parens(text)
    parts, start, depth = [], 0, 0
    i = 0
    while i < len(text):
        char = text[i]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == "&" and i + 1 < len(text) and text[i + 1] == "&" and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 2
            i += 1
        i += 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def _numeric_bound_contradiction(requires: str) -> bool:
    bounds: dict[str, dict[str, float]] = {}
    integer = r"(?:\d+|\(0\s*-\s*\d+\))"
    for match in re.finditer(rf"\b([A-Za-z_]\w*)\s*(>=|>|<=|<)\s*({integer})", requires):
        name, op, raw = match.groups()
        negative = re.match(r"\(0\s*-\s*(\d+)\)", raw)
        value = -float(negative.group(1)) if negative else float(raw)
        entry = bounds.setdefault(name, {"lower": float("-inf"), "upper": float("inf"),
                                         "lower_strict": False, "upper_strict": False})
        if op in (">", ">="):
            if value > entry["lower"] or (value == entry["lower"] and op == ">"):
                entry["lower"] = value
                entry["lower_strict"] = op == ">"
        else:
            if value < entry["upper"] or (value == entry["upper"] and op == "<"):
                entry["upper"] = value
                entry["upper_strict"] = op == "<"
    return any(
        entry["lower"] > entry["upper"]
        or (entry["lower"] == entry["upper"] and (entry["lower_strict"] or entry["upper_strict"]))
        for entry in bounds.values()
    )


def _strip_wrapping_parens(text: str) -> str:
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        wraps = True
        for index, char in enumerate(text):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(text) - 1:
                    wraps = False
                    break
        if not wraps:
            break
        text = text[1:-1].strip()
    return text


def _compact_clause(text: str) -> str:
    return "".join(_strip_wrapping_parens(text).split())


def _has_direct_complement(parts: list[str]) -> bool:
    compact = {_compact_clause(part) for part in parts if _compact_clause(part)}
    for part in compact:
        positive = part[1:] if part.startswith("!") else part
        positive = _compact_clause(positive)
        complements = {f"!{positive}", f"!({positive})"}
        if positive in compact and compact.intersection(complements):
            return True
    return False


def _references_result(text: str) -> bool:
    return re.search(r"\bresult\b", text) is not None


def lint_contract(requires: str, ensures: str) -> list[dict]:
    """Static adversarial contract warnings for generated `requires`/`ensures` clauses.

    The checker is intentionally conservative and syntactic: it catches empty-domain
    contracts and contracts whose postcondition carries no result constraint without
    trying to prove general satisfiability.  Mumei/Z3 remains the semantic checker.
    """
    findings = []
    requires_text = scrub(requires, "mumei")
    requires_parts = _top_level_conjuncts(requires_text)
    numeric_contradiction = "||" not in requires_text and _numeric_bound_contradiction(requires_text)
    if (any(re.sub(r"[\s()]+", "", part) == "false" for part in requires_parts)
            or _has_direct_complement(requires_parts) or numeric_contradiction):
        findings.append({"kind": "vacuous_spec",
                         "message": "requires clause is trivially unsatisfiable"})
    ensures_parts = _top_level_conjuncts(scrub(ensures, "mumei"))
    if not ensures_parts or all(_trivial_clause(part) or not _references_result(part) for part in ensures_parts):
        findings.append({"kind": "weak_spec",
                         "message": "ensures clause carries no result constraint"})
    return findings


def lint_findings(case: dict, body: str, variant: str = "buggy") -> list[dict]:
    """Structured fidelity warnings for an accepted LLM port of one source variant.

    The comparison is variant-aware: a buggy candidate is checked against the
    buggy source/reference and a fixed candidate against the fixed source/reference.
    `lint()` keeps the human-readable strings for compatibility; these records
    make the mechanism machine-countable instead of requiring prose parsing.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown port variant {variant!r}")
    source = scrub(case["functions"][variant] or "", case["language"])
    _, _, reference_body = split_port(case["ports"][variant], case["atom"])
    reference = scrub(body_inner(reference_body))
    port = scrub(body)
    findings = []
    silent_repair = _silent_repair(case, body, variant)
    if silent_repair:
        findings.append({"kind": "silent_repair",
                         "message": "candidate body matches the fixed reference instead of the buggy source"})
    # Only compare source operations represented by the hand-written model.
    rules = (
        ("index/slice", INDEX, INDEX + r"|\bslice_to\s*\("),
        ("division/modulo", DIVIDE, DIVIDE),
        ("dereference", r"(?:[\w\])])\s*\.|" + INDEX if case["category"] == "null-dereference"
         else r"\*\s*\w+", r"\bderef\s*\("),
        ("narrow cast", NARROW, NARROW),
    )
    findings.extend(
        {"kind": "missing_modeled_operation", "operation": name,
         "message": f"missing modeled {name}"}
        for name, native, modeled in rules
        if re.search(native, source) and re.search(modeled, reference) and not re.search(modeled, port)
    )
    if not silent_repair:
        reference_guards = len(re.findall(r"\bif\b", reference))
        port_guards = len(re.findall(r"\bif\b", port))
        if port_guards > reference_guards:
            findings.append({"kind": "added_guard", "message": "possible added guard"})
        elif port_guards < reference_guards:
            findings.append({"kind": "removed_guard", "message": "possible removed guard"})
    ensures = header_ensures(case["header"]) or ""
    if re.match(r"^\(*\s*result\.ok\s*=>", ensures):
        reference_flags = success_flag_paths(reference)
        port_flags = success_flag_paths(port)
        new_flags = port_flags - reference_flags
        reference_exprs = {expr for _, expr in reference_flags}
        port_exprs = {expr for _, expr in port_flags}
        if (any(expr != ("true",) for expr in reference_exprs) and port_flags
                and port_exprs == {("true",)}):
            findings.append({"kind": "guard_folding",
                             "message": "failure branch is folded into unconditional success"})
        if reference_flags and any(expr != ("true",) for _, expr in new_flags):
            findings.append({"kind": "success_flag_rewrite",
                             "message": "success flag can mask a postcondition clause"})
    if _has_folded_state_field(reference, port):
        findings.append({"kind": "guard_folding",
                         "message": "conditional result state is folded into one unconditional branch value"})
    if re.search(rf"\b{re.escape(case['atom'])}\s*\(", port):
        findings.append({"kind": "self_call", "message": "target atom calls itself"})
    return findings


def lint(case: dict, body: str, variant: str = "buggy") -> list[str]:
    return [finding["message"] for finding in lint_findings(case, body, variant)]


def outcome(inputs: list[dict]) -> str:
    if any(i["reference"]["verdict"] == "breaks" and i["llm"]["verdict"] == "holds" for i in inputs):
        return "diverged"
    if not inputs or any(i["reference"]["verdict"] != "breaks" or i["llm"]["verdict"] != "breaks"
                         for i in inputs):
        return "inconclusive"
    return "still_refutes"


def fixed_variant_outcome(inputs: list[dict]) -> str:
    """Replay outcome for a fixed candidate against the fixed reference port.

    ``diverged`` means the candidate breaks an input that the fixed reference
    satisfies. ``still_holds`` requires both sides to hold every supplied input;
    missing or unresolved verification is explicit non-evidence.
    """
    if any(i["reference"]["verdict"] == "holds" and i["llm"]["verdict"] == "breaks" for i in inputs):
        return "diverged"
    if not inputs or any(i["reference"]["verdict"] != "holds" or i["llm"]["verdict"] != "holds"
                         for i in inputs):
        return "inconclusive"
    return "still_holds"




PARAM_RE = re.compile(r"(\w+)\s*:\s*(\[i64\]|i64|bool)")
REPO_ROOT = Path(__file__).resolve().parent.parent


def atom_params(header: str) -> list[tuple[str, str]]:
    """(name, type) of the target atom's parameters."""
    sig = header[header.index("(") + 1:header.index(")")]
    return PARAM_RE.findall(sig)


def mm_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value) if value >= 0 else f"(0 - {-value})"
    if isinstance(value, list):
        if not value or any(isinstance(item, bool) or not isinstance(item, int) for item in value):
            raise ValueError("array literals must be non-empty integer lists")
        return "[" + ", ".join(mm_literal(item) for item in value) + "]"
    raise ValueError(f"unsupported input value {value!r}")


def pin_requires(header: str, values: dict) -> str:
    """The `requires` clause that fixes every parameter to `values`."""
    clauses = []
    for name, typ in atom_params(header):
        if name not in values:
            raise ValueError(f"input has no value for parameter {name!r}")
        v = values[name]
        if typ == "[i64]":
            if not isinstance(v, list):
                raise ValueError(f"{name} must be a list")
            clauses.append(f"len({name}) == {len(v)}")
            clauses += [f"{name}[{i}] == {mm_literal(x)}" for i, x in enumerate(v)]
        elif typ == "bool":
            if not isinstance(v, bool):
                raise ValueError(f"{name} must be a bool")
            clauses.append(name if v else f"!{name}")
        else:
            if isinstance(v, bool) or not isinstance(v, int):
                raise ValueError(f"{name} must be an integer")
            clauses.append(f"{name} == {mm_literal(v)}")
    extra = set(values) - {n for n, _ in atom_params(header)}
    if extra:
        raise ValueError(f"input names unknown parameters: {sorted(extra)}")
    return " && ".join(clauses) or "true"


def pinned_port(port_text: str, atom: str, values: dict) -> str:
    """The port with its target atom's `requires` narrowed to the pinned input."""
    parts = split_port(port_text, atom)
    if parts is None:
        raise ValueError(f"atom {atom!r} not found in port")
    prelude, header, body = parts
    pins = pin_requires(header, values)
    pinned, found = re.subn(r"^(\s*requires:\s*)(.*?)\s*;\s*$",
                            lambda m: f"{m.group(1)}({m.group(2)}) && {pins};", header, count=1, flags=re.M)
    if not found:
        raise ValueError(f"atom {atom!r} has no single-line requires")
    return prelude + pinned + body



def atom_return_type(header: str) -> str:
    match = re.search(r"->\s*(\w+)", header)
    if not match:
        raise ValueError("atom header has no return type")
    return match.group(1)


def atom_requires(header: str) -> str:
    match = re.search(r"^\s*requires:\s*(.*?)\s*;\s*$", header, re.M)
    if not match:
        raise ValueError("atom header has no single-line requires")
    return match.group(1)


def atom_param_text(header: str) -> str:
    return header[header.index("(") + 1:header.index(")")]


def struct_field_types(prelude: str, struct_name: str) -> list[tuple[str, str]]:
    match = re.search(rf"\bstruct\s+{re.escape(struct_name)}\s*\{{(.*?)\n\}}", prelude, re.S)
    if not match:
        raise ValueError(f"struct {struct_name!r} not found")
    fields = re.findall(r"\b(\w+)\s*:\s*(\[i64\]|i64|bool)", match.group(1))
    if not fields:
        raise ValueError(f"struct {struct_name!r} has no supported scalar fields")
    return fields


def output_policy_hash() -> str | None:
    """Hash of the committed output-equivalence adjudication input."""
    path = REPO_ROOT / "proofs/output-equivalence-policy.json"
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output_policy(case: dict) -> dict:
    """Committed adjudications for abstraction boundaries in output comparison."""
    path = REPO_ROOT / "proofs/output-equivalence-policy.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if data.get("schema") != "mumei-demo.output-equivalence-policy/v1":
        raise ValueError("unsupported output-equivalence policy schema")
    cases = data.get("cases", {})
    if not isinstance(cases, dict):
        raise ValueError("output-equivalence policy cases must be an object")
    entry = cases.get(case.get("id"), {})
    if not isinstance(entry, dict):
        raise ValueError("output-equivalence policy case entry must be an object")
    allowed = {"rationale", "field_relevance", "failure_state_fields",
               "rounding_tolerance_fields", "canonical_integer_arithmetic",
               "bounded_interaction_inputs"}
    unknown_keys = set(entry) - allowed
    if unknown_keys:
        raise ValueError(f"unsupported output-equivalence policy keys: {sorted(unknown_keys)}")
    if "canonical_integer_arithmetic" in entry and entry["canonical_integer_arithmetic"] is not True:
        raise ValueError("canonical_integer_arithmetic must be true when present")
    for key in ("field_relevance", "rounding_tolerance_fields"):
        if key in entry and not isinstance(entry[key], dict):
            raise ValueError(f"output-equivalence policy {key} must be an object")
    if "failure_state_fields" in entry and not isinstance(entry["failure_state_fields"], list):
        raise ValueError("output-equivalence policy failure_state_fields must be a list")
    if "bounded_interaction_inputs" in entry:
        inputs = entry["bounded_interaction_inputs"]
        if not isinstance(inputs, list) or not inputs:
            raise ValueError("bounded_interaction_inputs must be a non-empty list")
        for input_index, interaction_input in enumerate(inputs):
            if (not isinstance(interaction_input, dict)
                    or set(interaction_input) != {"name", "values"}
                    or not isinstance(interaction_input.get("name"), str)
                    or not interaction_input["name"]
                    or not isinstance(interaction_input.get("values"), dict)):
                raise ValueError(f"bounded_interaction_inputs[{input_index}] must have exactly name and values")
    return entry


def field_comparison(name: str, policy: dict) -> str:
    tolerance = (policy.get("rounding_tolerance_fields") or {}).get(name)
    if tolerance is None:
        relation = f"(reference.{name} == candidate.{name})"
    else:
        if isinstance(tolerance, bool) or not isinstance(tolerance, int) or tolerance < 1:
            raise ValueError("rounding tolerance must be a positive integer")
        forward = f"((reference.{name} - candidate.{name}) <= {tolerance})"
        backward = f"((candidate.{name} - reference.{name}) <= {tolerance})"
        relation = f"({forward} && {backward})"
    relevance = (policy.get("field_relevance") or {}).get(name)
    if relevance is not None:
        if not isinstance(relevance, str) or not relevance.strip():
            raise ValueError("field relevance must be a non-empty Mumei boolean expression")
        relation = f"(!({relevance}) || {relation})"
    return relation


def output_comparison_expression(case: dict, policy: dict, use_policy: bool = True) -> str:
    """Output relation used by solver comparison and bounded native interaction."""
    return_type = atom_return_type(case["header"])
    if return_type in {"i64", "bool"}:
        return "reference == candidate"
    fields = struct_field_types(case["prelude"], return_type)
    names = [name for name, _ in fields]
    non_ok = [name for name in names if name != "ok"]
    for key in ("field_relevance", "rounding_tolerance_fields"):
        unknown = set((policy.get(key) or {})) - set(names)
        if unknown:
            raise ValueError(f"output-equivalence policy names unknown fields: {sorted(unknown)}")
    unknown_failure = set(policy.get("failure_state_fields") or []) - set(non_ok)
    if unknown_failure:
        raise ValueError(f"failure-state fields are unknown or not payload fields: {sorted(unknown_failure)}")
    payload = " && ".join(field_comparison(name, policy) for name in non_ok)
    if "ok" not in names:
        return payload
    comparison = "(reference.ok == candidate.ok)"
    if use_policy:
        if payload:
            comparison += f" && (!(reference.ok && candidate.ok) || ({payload}))"
        failure = [f"(reference.{name} == candidate.{name})"
                   for name in (policy.get("failure_state_fields") or [])]
        if failure:
            comparison += " && " + " && ".join(failure)
    elif payload:
        comparison += f" && ({payload})"
    return comparison


def output_compare_text(case: dict, candidate_body: str, variant: str = "buggy",
                        use_policy: bool = True) -> str:
    """A solver harness comparing reference and candidate output values.

    Struct payload fields other than ``ok`` are compared on jointly successful
    outputs unless the committed output-equivalence policy marks them as
    meaningful failure-path state. Field relevance and rounding tolerances are
    explicit per-case abstraction adjudications, not inferred verdicts.
    """
    parts = split_port(case["ports"][variant], case["atom"])
    if parts is None:
        raise ValueError("reference port not found")
    _, _, reference_body = parts
    reference = body_inner(reference_body).strip()
    candidate = candidate_body.strip()
    if not reference or not candidate:
        raise ValueError("empty reference or candidate body")
    policy = output_policy(case) if use_policy else {}
    comparison = output_comparison_expression(case, policy, use_policy)
    params = atom_param_text(case["header"])
    requires = atom_requires(case["header"])
    return (case["prelude"]
            + f"atom compare_{case['atom']}({params}) -> bool\n"
            + f"    requires: {requires};\n"
            + "    ensures: result == true;\n"
            + "    body: {\n"
            + "        let reference = {\n"
            + textwrap_indent(reference, "            ") + "\n"
            + "        };\n"
            + "        let candidate = {\n"
            + textwrap_indent(candidate, "            ") + "\n"
            + "        };\n"
            + f"        {comparison}\n"
            + "    }\n")


def textwrap_indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line.strip() else line for line in text.splitlines())


def bounded_interaction_inputs(case: dict, policy: dict) -> list[dict]:
    """Validated committed concrete inputs for native loop/state interaction evidence."""
    inputs = policy.get("bounded_interaction_inputs") or []
    validated = []
    for interaction_input in inputs:
        values = interaction_input["values"]
        pin_requires(case["header"], values)
        validated.append({"name": interaction_input["name"], "values": values})
    return validated


def bounded_interaction_text(case: dict, candidate_body: str, values: dict,
                             variant: str = "buggy") -> str:
    """A native executable comparing reference and candidate on one concrete input.

    Exit code 0 means the committed adjudicated outputs agree, 42 means they
    observably diverge, and 43 means the input violates the target atom's
    ``requires`` clause. Other nonzero exits are tool/build failures and are
    not semantic evidence.
    """
    parts = split_port(case["ports"][variant], case["atom"])
    if parts is None:
        raise ValueError("reference port not found")
    _, _, reference_body = parts
    reference = body_inner(reference_body).strip()
    candidate = candidate_body.strip()
    if not reference or not candidate:
        raise ValueError("empty reference or candidate body")
    params = atom_params(case["header"])
    if any(name in {"reference", "candidate"} for name, _ in params):
        raise ValueError("parameter names collide with comparison bindings")
    assignments = [f"let {name} = {mm_literal(values[name])};" for name, _ in params]
    policy = output_policy(case)
    comparison = output_comparison_expression(case, policy, use_policy=True)
    requires = atom_requires(case["header"])
    return (case["prelude"]
            + "atom main() -> i64\n"
            + "    requires: true;\n"
            + "    ensures: true;\n"
            + "    body: {\n"
            + "".join("        " + assignment + "\n" for assignment in assignments)
            + "        let reference = {\n"
            + "".join("            " + assignment + "\n" for assignment in assignments)
            + textwrap_indent(reference, "            ") + "\n"
            + "        };\n"
            + "        let candidate = {\n"
            + "".join("            " + assignment + "\n" for assignment in assignments)
            + textwrap_indent(candidate, "            ") + "\n"
            + "        };\n"
            + f"        if !({requires}) {{ 43 }} else {{ if {comparison} {{ 0 }} else {{ 42 }} }}\n"
            + "    }\n")


def run_bounded_interaction_text(mumei_bin: str, text: str, timeout: int) -> dict:
    """Compile and execute one bounded-interaction harness without trusting stdout."""
    with tempfile.TemporaryDirectory(prefix="mumei-bounded-interaction-") as tmp:
        path = Path(tmp) / "interaction.mm"
        path.write_text(text)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [mumei_bin, "run", str(path)], cwd=tmp, capture_output=True, text=True,
                timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"result": "error", "error": type(error).__name__,
                    "timeout": isinstance(error, subprocess.TimeoutExpired),
                    "seconds": time.monotonic() - started, "budget_seconds": timeout}
        return {"exit_code": completed.returncode,
                "seconds": time.monotonic() - started, "budget_seconds": timeout}


def bounded_interaction_equivalence(case: dict, candidate_body: str, mumei_bin: str,
                                    timeout: int, variant: str = "buggy") -> dict | None:
    """Concrete native input/state interaction evidence for loop-containing ports.

    A 42 exit is an observed output divergence on an input that satisfies the
    target contract. Agreement is finite evidence only, so it remains
    ``inconclusive`` rather than ``matched``; it never claims universal equality.
    """
    policy = output_policy(case)
    inputs = bounded_interaction_inputs(case, policy)
    if not inputs:
        return None
    if re.search(r"\b(?:extern|effect)\b", case["prelude"]):
        return {"outcome": "unavailable", "reason": "bounded_interaction_effectful_prelude",
                "method": "bounded_native_interaction"}
    attempts = []
    errors = []
    invalid = []
    diverged = []
    for interaction_input in inputs:
        attempt = {"name": interaction_input["name"], "values": interaction_input["values"]}
        try:
            text = bounded_interaction_text(case, candidate_body, interaction_input["values"], variant)
            run = run_bounded_interaction_text(mumei_bin, text, timeout)
        except (KeyError, ValueError, IndexError) as error:
            run = {"result": "error", "error": str(error), "seconds": 0.0, "budget_seconds": timeout}
        if run.get("exit_code") == 0:
            attempt["result"] = "matched"
        elif run.get("exit_code") == 42:
            attempt["result"] = "diverged"
            diverged.append(attempt)
        elif run.get("exit_code") == 43:
            attempt["result"] = "outside_requires"
            invalid.append(attempt)
        else:
            attempt["result"] = "error"
            errors.append({**attempt, "error": run.get("error"), "exit_code": run.get("exit_code"),
                           "timeout": bool(run.get("timeout"))})
        for key in ("seconds", "budget_seconds"):
            if key in run:
                attempt[key] = run[key]
        attempts.append(attempt)
    evidence = {"method": "bounded_native_interaction", "inputs": attempts,
                "interaction": {
                    "expected_executions": len(attempts),
                    "timed_executions": sum("seconds" in attempt for attempt in attempts),
                    "seconds": sum(attempt.get("seconds", 0.0) for attempt in attempts),
                    "budgeted_executions": sum("budget_seconds" in attempt for attempt in attempts),
                    "budget_seconds": sum(attempt.get("budget_seconds", 0.0) for attempt in attempts),
                }}
    if diverged:
        first = diverged[0]
        evidence.update({"outcome": "diverged", "status": "failed",
                         "divergence_input": {"name": first["name"], "values": first["values"]},
                         "diagnostics": [{"atom": "main", "code": "bounded-divergence",
                                          "message": f"bounded native interaction diverged on {first['name']}"}]})
    elif invalid:
        evidence.update({"outcome": "inconclusive", "status": "error",
                         "reason": "bounded_interaction_input_outside_requires",
                         "failure_kind": "unsupported",
                         "diagnostics": [{"atom": "main", "code": "outside-requires",
                                          "message": "a committed bounded input violates the target requires clause"}]})
    elif errors:
        timed_out = any(error.get("timeout") for error in errors)
        evidence.update({"outcome": "inconclusive",
                         "status": "timeout" if timed_out else "error",
                         "reason": "bounded_interaction_timeout" if timed_out else "bounded_interaction_tool_failure",
                         "failure_kind": "budget_exhausted" if timed_out else "environment_failure",
                         "diagnostics": [{"atom": "main", "code": "timeout" if timed_out else "tool-failure",
                                          "message": str(errors[0].get("error")
                                                         or f"native interaction exited {errors[0].get('exit_code')}")[:200]}]})
    else:
        evidence.update({"outcome": "inconclusive", "status": "success",
                         "reason": "bounded_interactions_matched",
                         "diagnostics": []})
    return evidence


def output_equivalence(case: dict, candidate_body: str, mumei_bin: str, timeout: int,
                       variant: str = "buggy") -> dict:
    """Diagnostic reference-vs-candidate output equality evidence.

    ``matched`` is exact solver equality. ``diverged`` means a separating input
    remains after the committed relevance/rounding/failure-state adjudication;
    a difference confined to those boundary regions is explicitly inconclusive
    rather than blocking evidence. Loop-containing bodies do not use solver
    equality because loop-invariant abstraction can manufacture spurious
    differences even between two copies of the same reference body. Cases with
    committed concrete inputs instead use bounded native interaction: observed
    divergence is evidence, while finite agreement remains inconclusive.
    """
    try:
        parts = split_port(case["ports"][variant], case["atom"])
        reference = body_inner(parts[2]) if parts else ""
        if re.search(r"\bwhile\b", reference) or re.search(r"\bwhile\b", candidate_body):
            bounded = bounded_interaction_equivalence(case, candidate_body, mumei_bin, timeout, variant)
            if bounded is not None:
                return bounded
            return {"outcome": "unavailable", "reason": "loop_equivalence_unverified",
                    "method": "solver_output_compare"}
        text = output_compare_text(case, candidate_body, variant, use_policy=False)
        policy = output_policy(case)
        if any(finding.get("kind") == "vacuous_spec"
               for finding in lint_contract(atom_requires(case["header"]), "result == result")):
            return {"outcome": "unavailable", "reason": "vacuous_compare_domain",
                    "method": "solver_output_compare"}
    except (KeyError, ValueError, IndexError) as error:
        return {"outcome": "unavailable", "reason": str(error), "method": "solver_output_compare"}
    helpers = re.findall(r"\batom\s+(\w+)\s*\(", case["prelude"])
    opaque_calls = sorted({name for name in helpers
                           if re.search(rf"\b{re.escape(name)}\s*\(", reference)
                           or re.search(rf"\b{re.escape(name)}\s*\(", candidate_body)})

    def classify(result: dict) -> str:
        postcondition_failure = any("Postcondition" in diagnostic["message"]
                                    for diagnostic in result["diagnostics"])
        if result["outcome"] == "proven":
            return "matched"
        if result["outcome"] == "refuted" and postcondition_failure and not opaque_calls:
            return "diverged"
        return "inconclusive"

    verifications = []
    exact_verification = verify_text(mumei_bin, text, timeout)
    verifications.append(exact_verification)
    exact_outcome = classify(exact_verification)
    outcome = exact_outcome
    verification = exact_verification
    boundary_only = False
    operational_policy = any(key in policy for key in
                             ("field_relevance", "failure_state_fields", "rounding_tolerance_fields"))
    return_type = atom_return_type(case["header"])
    failure_payload_boundary = False
    if return_type not in {"i64", "bool"}:
        names = [name for name, _ in struct_field_types(case["prelude"], return_type)]
        failure_payload_boundary = "ok" in names
    if exact_outcome == "diverged" and (operational_policy or failure_payload_boundary):
        adjusted_text = output_compare_text(case, candidate_body, variant, use_policy=True)
        adjusted_verification = verify_text(mumei_bin, adjusted_text, timeout)
        verifications.append(adjusted_verification)
        adjusted_outcome = classify(adjusted_verification)
        verification = adjusted_verification
        if adjusted_outcome == "matched":
            outcome = "inconclusive"
            boundary_only = True
        else:
            outcome = adjusted_outcome
    evidence = {"outcome": outcome, "method": "solver_output_compare",
                "status": verification["status"],
                "diagnostics": verification["diagnostics"][:2]}
    if boundary_only:
        evidence["reason"] = "abstraction_boundary_only"
        evidence["exact_output"] = {"outcome": exact_outcome, "status": exact_verification["status"],
                                    "diagnostics": exact_verification["diagnostics"][:2]}
    if policy:
        evidence["comparison_policy"] = policy
    if opaque_calls:
        evidence["opaque_atom_calls"] = opaque_calls
        final_postcondition_failure = any("Postcondition" in diagnostic["message"]
                                          for diagnostic in verification["diagnostics"])
        if verification["outcome"] == "refuted" and final_postcondition_failure and not boundary_only:
            evidence["reason"] = "opaque_atom_call_counterexample"
    measured = [result for result in verifications
                if any(isinstance(result.get(key), (int, float)) and not isinstance(result.get(key), bool)
                       for key in ("seconds", "budget_seconds"))]
    if measured:
        evidence["verification"] = {
            "expected_calls": len(verifications),
            "timed_calls": sum(isinstance(result.get("seconds"), (int, float))
                               and not isinstance(result.get("seconds"), bool) for result in verifications),
            "seconds": sum(result.get("seconds", 0.0) for result in verifications
                           if isinstance(result.get("seconds"), (int, float))
                           and not isinstance(result.get("seconds"), bool)),
            "budgeted_calls": sum(isinstance(result.get("budget_seconds"), (int, float))
                                  and not isinstance(result.get("budget_seconds"), bool) for result in verifications),
            "budget_seconds": sum(result.get("budget_seconds", 0.0) for result in verifications
                                  if isinstance(result.get("budget_seconds"), (int, float))
                                  and not isinstance(result.get("budget_seconds"), bool)),
        }
    for key in ("failure_kind", "seconds", "budget_seconds"):
        if key in verification:
            evidence[key] = verification[key]
    return evidence


REQUIRES_CONTRADICTION = re.compile(r"Spec contradiction in atom '[^']*': requires")


def port_verdict(mumei_bin: str, port_text: str, atom: str, values: dict, timeout: int = 120) -> dict:
    """breaks / holds / outside requires / inconclusive for a port on one concrete input."""
    res = verify_text(mumei_bin, pinned_port(port_text, atom, values), timeout)
    verdict = {"refuted": "breaks", "proven": "holds"}.get(res["outcome"], "inconclusive")
    if verdict == "inconclusive" and any(REQUIRES_CONTRADICTION.search(d["message"]) for d in res["diagnostics"]):
        verdict = "outside requires"
    measured = {k: res[k] for k in ("failure_kind", "seconds", "budget_seconds") if k in res}
    return {"verdict": verdict, "status": res["status"],
            "diagnostics": [d["message"][:200] for d in res["diagnostics"]][:2], **measured}


def replay_inputs(case: dict) -> tuple[list[dict], str]:
    """Concrete replay inputs for one benchmark case and their fixture hash."""
    import hashlib

    path = REPO_ROOT / case["dir"] / "replay.json"
    text = path.read_text()
    return json.loads(text)["inputs"], hashlib.sha256(text.encode()).hexdigest()


GATE_LINT_KINDS = frozenset({
    "silent_repair", "missing_modeled_operation", "guard_folding", "self_call", "success_flag_rewrite",
})


def blocking_lint_findings(findings: list[dict]) -> list[dict]:
    """High-confidence lint findings that can block fidelity acceptance by themselves.

    Guard-count differences remain recorded warnings, but `added_guard` or
    `removed_guard` alone does not block: fixed-side translations can carry a
    legitimate guard shape that differs from the hand-written reference.
    """
    return [finding for finding in findings if finding.get("kind") in GATE_LINT_KINDS]
