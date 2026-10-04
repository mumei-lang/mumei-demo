#!/usr/bin/env python3
"""Validate specimen directories under specimens/.

Usage: python3 scripts/check_specimens.py [--root specimens] [SPECIMEN_DIR ...]

With no specimen arguments, discovers every <root>/<language>/<id>/DEFECTS.json.
Exits 0 when everything checks out (including when no specimens exist),
1 otherwise, printing one error line per problem.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "specimens" / "DEFECTS.schema.json"

LANG_PREFIX = {
    "python": "py",
    "typescript": "ts",
    "go": "go",
    "rust": "rs",
    "solidity": "sol",
}
PREFIX_TO_LANG = {v: k for k, v in LANG_PREFIX.items()}

SOURCE_EXTENSIONS = {".py", ".ts", ".go", ".rs", ".sol"}
EXEMPT_FILES = {"run.sh", "repro.sh"}

FORBIDDEN_HINTS = [
    r"\bbug\b",
    r"\bvuln",
    r"intentional",
    r"deliberate",
    r"planted",
    r"\bexploit",
    r"\bCWE-",
    r"\binsecure\b",
    r"\bunsafe on purpose",
    r"\bfixme\b",
    r"\bxxx\b",
]
FORBIDDEN_RE = re.compile("|".join(FORBIDDEN_HINTS), re.IGNORECASE)

PORT_RE = re.compile(r"^Default port: (\d+)$", re.MULTILINE)


def load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _check_type(value, expected, path, errors):
    types = expected if isinstance(expected, list) else [expected]
    type_map = {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
        "null": lambda v: v is None,
        "boolean": lambda v: isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    }
    if not any(type_map[t](value) for t in types):
        errors.append(f"{path}: expected type {'/'.join(types)}, got {type(value).__name__}")
        return False
    return True


def validate_value(value, spec: dict, path: str, errors: list) -> None:
    """Hand-rolled validation of the subset of JSON Schema used by DEFECTS.schema.json."""
    if "enum" in spec:
        if value not in spec["enum"]:
            errors.append(f"{path}: {value!r} is not one of {spec['enum']}")
        return

    if "type" in spec and not _check_type(value, spec["type"], path, errors):
        return

    if isinstance(value, dict):
        required = spec.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required key {key!r}")
        props = spec.get("properties", {})
        if spec.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: unexpected key {key!r}")
        for key, sub in props.items():
            if key in value:
                validate_value(value[key], sub, f"{path}.{key}", errors)
        return

    if isinstance(value, list):
        if "minItems" in spec and len(value) < spec["minItems"]:
            errors.append(f"{path}: expected at least {spec['minItems']} items, got {len(value)}")
        if "items" in spec:
            for i, item in enumerate(value):
                validate_value(item, spec["items"], f"{path}[{i}]", errors)
        return

    if isinstance(value, str):
        if "minLength" in spec and len(value) < spec["minLength"]:
            errors.append(f"{path}: shorter than minLength {spec['minLength']}")
        if "pattern" in spec:
            # JSON Schema patterns are unanchored (search semantics).
            if not re.search(spec["pattern"], value):
                errors.append(f"{path}: {value!r} does not match pattern {spec['pattern']}")
        return

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in spec and value < spec["minimum"]:
            errors.append(f"{path}: {value!r} is below minimum {spec['minimum']}")


def is_executable(path: Path) -> bool:
    return os.access(path, os.X_OK)


def bash_syntax_ok(path: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        ["bash", "-n", str(path)], capture_output=True, text=True
    )
    return proc.returncode == 0, proc.stderr.strip()


def scan_forbidden_hints(specimen_dir: Path, errors: list) -> None:
    for path in sorted(specimen_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in EXEMPT_FILES:
            continue
        if path.suffix not in SOURCE_EXTENSIONS:
            continue
        rel = path.relative_to(specimen_dir)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"{specimen_dir}: cannot read {rel}: {exc}")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            m = FORBIDDEN_RE.search(line)
            if m:
                errors.append(
                    f"{specimen_dir}: {rel}:{lineno}: forbidden hint word {m.group(0)!r}"
                )


def check_specimen(specimen_dir: Path, schema: dict, errors: list) -> int:
    """Check one specimen dir; return number of defects counted."""
    prefix = str(specimen_dir)
    readme = specimen_dir / "README.md"
    defects_json = specimen_dir / "DEFECTS.json"
    run_sh = specimen_dir / "run.sh"
    repro_sh = specimen_dir / "repro.sh"

    for required_file in (readme, defects_json, run_sh, repro_sh):
        if not required_file.is_file():
            errors.append(f"{prefix}: missing {required_file.name}")

    for script in (run_sh, repro_sh):
        if not script.is_file():
            continue
        if not is_executable(script):
            errors.append(f"{prefix}: {script.name} is not executable")
        ok, stderr = bash_syntax_ok(script)
        if not ok:
            errors.append(f"{prefix}: bash -n {script.name} failed: {stderr}")

    if not defects_json.is_file():
        return 0

    try:
        data = json.loads(defects_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{prefix}: DEFECTS.json is not valid JSON: {exc}")
        return 0

    validate_value(data, schema, f"{prefix}: DEFECTS.json", errors)

    if not isinstance(data, dict):
        return 0

    specimen_name = specimen_dir.name
    language_dir = specimen_dir.parent.name

    if data.get("specimen") != specimen_name:
        errors.append(
            f"{prefix}: specimen {data.get('specimen')!r} != directory name {specimen_name!r}"
        )
    if data.get("language") != language_dir:
        errors.append(
            f"{prefix}: language {data.get('language')!r} != parent directory {language_dir!r}"
        )

    expected_prefix = LANG_PREFIX.get(data.get("language", ""), None)
    if expected_prefix and isinstance(data.get("specimen"), str):
        if not data["specimen"].startswith(expected_prefix + "-"):
            errors.append(
                f"{prefix}: specimen id {data['specimen']!r} does not start with "
                f"{expected_prefix}- for language {data.get('language')!r}"
            )

    # Expected defect-id prefix from specimen id: py-03-x -> PY03
    defect_id_prefix = None
    if isinstance(data.get("specimen"), str):
        m = re.match(r"^(py|ts|go|rs|sol)-(\d{2})-", data["specimen"])
        if m:
            defect_id_prefix = m.group(1).upper() + m.group(2)

    defects = data.get("defects")
    if not isinstance(defects, list):
        return 0

    seen_ids: set[str] = set()
    seen_repros: set[str] = set()
    file_lines_cache: dict[str, list[str]] = {}

    for defect in defects:
        if not isinstance(defect, dict):
            continue
        did = defect.get("id", "<no id>")
        dpath = f"{prefix}: defect {did}"

        if defect_id_prefix and isinstance(did, str):
            if not did.startswith(defect_id_prefix + "-D"):
                errors.append(
                    f"{dpath}: id does not start with {defect_id_prefix}-D"
                )
        if isinstance(did, str):
            if did in seen_ids:
                errors.append(f"{dpath}: duplicate defect id")
            seen_ids.add(did)

        repro = defect.get("repro")
        if isinstance(repro, str):
            if repro in seen_repros:
                errors.append(f"{dpath}: duplicate repro name {repro!r}")
            seen_repros.add(repro)

        rel_file = defect.get("file")
        if not isinstance(rel_file, str) or not rel_file:
            continue
        target = (specimen_dir / rel_file).resolve()
        try:
            target.relative_to(specimen_dir.resolve())
        except ValueError:
            errors.append(f"{dpath}: file {rel_file!r} escapes specimen directory")
            continue
        if not target.is_file():
            errors.append(f"{dpath}: file {rel_file!r} does not exist")
            continue

        if rel_file not in file_lines_cache:
            file_lines_cache[rel_file] = target.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        lines = file_lines_cache[rel_file]

        line = defect.get("line")
        if isinstance(line, int) and not isinstance(line, bool):
            if line > len(lines):
                errors.append(
                    f"{dpath}: line {line} beyond end of {rel_file} ({len(lines)} lines)"
                )
            else:
                anchor = defect.get("anchor")
                if isinstance(anchor, str) and anchor not in lines[line - 1]:
                    errors.append(
                        f"{dpath}: anchor {anchor!r} not found on {rel_file}:{line}"
                    )

        func = defect.get("function")
        if isinstance(func, str) and func:
            if func not in "\n".join(lines):
                errors.append(f"{dpath}: function {func!r} not found in {rel_file}")

    scan_forbidden_hints(specimen_dir, errors)

    # Web specimens must declare a unique default port.
    if data.get("kind") == "web" and readme.is_file():
        text = readme.read_text(encoding="utf-8", errors="replace")
        if not PORT_RE.search(text):
            errors.append(
                f"{prefix}: web specimen README.md lacks a 'Default port: NNNN' line"
            )

    return len(defects)


def collect_ports(specimen_dir: Path) -> list[int]:
    readme = specimen_dir / "README.md"
    defects_json = specimen_dir / "DEFECTS.json"
    if not readme.is_file() or not defects_json.is_file():
        return []
    try:
        data = json.loads(defects_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict) or data.get("kind") != "web":
        return []
    text = readme.read_text(encoding="utf-8", errors="replace")
    m = PORT_RE.search(text)
    return [int(m.group(1))] if m else []


def discover_specimens(root: Path) -> list[Path]:
    """Every <lang>/<id>/ directory, with or without DEFECTS.json — a missing
    manifest must surface as a validation error, not hide the specimen."""
    return sorted(
        p for p in root.glob("*/*")
        if p.is_dir()
        and not p.name.startswith(".")
        and not p.parent.name.startswith(".")
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate specimen directories.")
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT / "specimens"),
        help="specimens root directory (default: %(default)s)",
    )
    parser.add_argument("specimens", nargs="*", help="specimen directories to check")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if args.specimens:
        dirs = [Path(d) for d in args.specimens]
    else:
        if not root.is_dir():
            print(f"note: specimens root {root} does not exist")
            dirs = []
        else:
            dirs = discover_specimens(root)

    if not dirs:
        print(f"note: no specimens found under {root}")

    schema = load_schema()
    errors: list[str] = []
    total_defects = 0
    port_owners: dict[int, str] = {}

    for d in dirs:
        total_defects += check_specimen(d, schema, errors)
        for port in collect_ports(d):
            if port in port_owners:
                errors.append(
                    f"{d}: default port {port} also used by {port_owners[port]}"
                )
            else:
                port_owners[port] = str(d)

    for e in errors:
        print(f"error: {e}")
    print(f"checked {len(dirs)} specimens, {total_defects} defects")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
