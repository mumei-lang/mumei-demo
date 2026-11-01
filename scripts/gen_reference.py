#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
for directory in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from reference import render_reference


DEFAULT_OUTPUT = REPO_ROOT / "docs" / "REFERENCE.md"


def main(argv: list[str] | None = None, *, reference_path: Path | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in ([], ["--check"]):
        print("usage: gen_reference.py [--check]", file=sys.stderr)
        return 2

    output = reference_path or DEFAULT_OUTPUT
    expected = render_reference()
    if arguments == ["--check"]:
        if not output.exists() or output.read_text(encoding="utf-8") != expected:
            print(f"{output} is out of date; run ./scripts/gen_reference.py", file=sys.stderr)
            return 1
        print(f"{output} is up to date")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
