#!/usr/bin/env python3
"""Shared syntactic intent-fidelity lint and replay outcome classification.

This module is deliberately independent of the contract benchmark implementation
so the benchmark, the divergence report and the adversarial corpus checker all use
the same detector without importing each other.
"""
from __future__ import annotations

import json
import re
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
        if (not port_path and len(reference_exprs) >= 2 and port_expr in reference_exprs
                and all(path for path, _ in reference_entries)):
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
DETECTOR_VERSION = 5


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
