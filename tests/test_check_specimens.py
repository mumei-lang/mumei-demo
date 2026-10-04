"""Tests for scripts/check_specimens.py — all fixtures built under tmp_path."""

import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_specimens.py"

spec = importlib.util.spec_from_file_location("check_specimens", SCRIPT)
check_specimens = importlib.util.module_from_spec(spec)
sys.modules["check_specimens"] = check_specimens
spec.loader.exec_module(check_specimens)


def valid_defects(specimen="py-01-demo", language="python", kind="cli", port=None):
    return {
        "specimen": specimen,
        "language": language,
        "kind": kind,
        "summary": "A demo specimen.",
        "defects": [
            {
                "id": "PY01-D01",
                "file": "app.py",
                "function": "add",
                "line": 2,
                "anchor": "return a - b",
                "class": "bug",
                "category": "logic-error",
                "cwe": None,
                "title": "add subtracts",
                "description": "add() subtracts instead of adding.",
                "trigger": "add(1, 2)",
                "observed": "returns -1",
                "repro": "add_subtracts",
            }
        ],
    }


def make_specimen(root, name="py-01-demo", language_dir="python", defects=None,
                  source=None, readme_extra="", executable=True):
    if defects is None:
        defects = valid_defects()
    if source is None:
        source = "def add(a, b):\n    return a - b\n"
    d = root / language_dir / name
    d.mkdir(parents=True)
    (d / "README.md").write_text(f"# demo\n{readme_extra}")
    (d / "DEFECTS.json").write_text(json.dumps(defects))
    (d / "app.py").write_text(source)
    for sh in ("run.sh", "repro.sh"):
        p = d / sh
        p.write_text("#!/usr/bin/env bash\necho ok\n")
        if executable:
            p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return d


def run(root, *dirs, capsys):
    argv = ["--root", str(root)] + [str(d) for d in dirs]
    rc = check_specimens.main(argv)
    out = capsys.readouterr().out
    return rc, out


def test_valid_specimen_passes(tmp_path, capsys):
    make_specimen(tmp_path)
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 0, out
    assert "checked 1 specimens, 1 defects" in out


def test_empty_root_ok(tmp_path, capsys):
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 0
    assert "no specimens" in out
    assert "checked 0 specimens, 0 defects" in out


def test_anchor_not_on_line(tmp_path, capsys):
    defects = valid_defects()
    defects["defects"][0]["anchor"] = "return a + b"
    make_specimen(tmp_path, defects=defects)
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 1
    assert "anchor" in out and "not found" in out


def test_wrong_id_prefix(tmp_path, capsys):
    defects = valid_defects()
    defects["defects"][0]["id"] = "TS01-D01"
    make_specimen(tmp_path, defects=defects)
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 1
    assert "does not match pattern" in out or "PY01-D" in out


def test_bad_category_enum(tmp_path, capsys):
    defects = valid_defects()
    defects["defects"][0]["category"] = "not-a-category"
    make_specimen(tmp_path, defects=defects)
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 1
    assert "not-a-category" in out


def test_extra_property_rejected(tmp_path, capsys):
    defects = valid_defects()
    defects["defects"][0]["surprise"] = "nope"
    make_specimen(tmp_path, defects=defects)
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 1
    assert "unexpected key 'surprise'" in out


def test_forbidden_hint_word(tmp_path, capsys):
    make_specimen(tmp_path, source="def add(a, b):\n    # BUG: subtracts\n    return a - b\n")
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 1
    assert "forbidden hint word" in out
    assert "app.py:2" in out


def test_rust_unsafe_not_flagged(tmp_path, capsys):
    defects = valid_defects(specimen="rs-01-demo", language="rust")
    defects["defects"][0].update(
        id="RS01-D01", file="main.rs", function="get",
        anchor="unsafe { *p }", cwe="CWE-119",
    )
    # cwe in DEFECTS.json is fine; only source files are scanned.
    d = make_specimen(tmp_path, name="rs-01-demo", language_dir="rust", defects=defects)
    (d / "app.py").unlink()
    (d / "main.rs").write_text(
        "fn get(p: *const i32) -> i32 {\n    unsafe { *p }\n}\n"
    )
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 0, out


def test_duplicate_web_port(tmp_path, capsys):
    defects = valid_defects(kind="web")
    make_specimen(tmp_path, name="py-01-web", defects=defects,
                  readme_extra="Default port: 8080\n")
    defects2 = valid_defects(specimen="py-02-web", kind="web")
    defects2["defects"][0]["id"] = "PY02-D01"
    make_specimen(tmp_path, name="py-02-web", defects=defects2,
                  readme_extra="Default port: 8080\n")
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 1
    assert "default port 8080" in out


def test_web_specimen_requires_port_line(tmp_path, capsys):
    make_specimen(tmp_path, defects=valid_defects(kind="web"))
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 1
    assert "Default port" in out


def test_non_executable_repro(tmp_path, capsys):
    d = make_specimen(tmp_path)
    (d / "repro.sh").chmod(0o644)
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 1
    assert "repro.sh is not executable" in out


def test_file_escape_rejected(tmp_path, capsys):
    defects = valid_defects()
    defects["defects"][0]["file"] = "../outside.py"
    make_specimen(tmp_path, defects=defects)
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 1
    assert "escapes specimen directory" in out


def test_specimen_dirname_mismatch(tmp_path, capsys):
    defects = valid_defects(specimen="py-99-other")
    defects["defects"][0]["id"] = "PY99-D01"
    make_specimen(tmp_path, name="py-01-demo", defects=defects)
    rc, out = run(tmp_path, capsys=capsys)
    assert rc == 1
    assert "directory name" in out
