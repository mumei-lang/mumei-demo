"""Unit tests for scripts/run_native_replay.py.

Nothing here runs a native toolchain or mumei: the tests cover witness parsing, input pinning,
classification and the offline check of the committed results."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("run_native_replay", REPO_ROOT / "scripts" / "run_native_replay.py")
nr = importlib.util.module_from_spec(spec)
sys.modules["run_native_replay"] = nr
spec.loader.exec_module(nr)

HEADER = ("atom take(parts: [i64], n: i64, strict: bool) -> i64\n"
          "    requires: n >= 0;\n    ensures: result >= 0;\n    ")
PARAMS = [("parts", "[i64]"), ("n", "i64"), ("strict", "bool")]


@pytest.fixture(scope="module")
def cases():
    loaded, errors = nr.rb.load_cases()
    assert not errors
    return loaded


@pytest.fixture(scope="module")
def committed():
    return json.loads(nr.RESULT_PATH.read_text())


# ---- witness parsing

@pytest.mark.parametrize("text, expected", [
    ("parts=[0], n=1, strict=true", {"parts": [0], "n": 1, "strict": True}),
    ("n = -3, strict = False, parts = []", {"parts": [], "n": -3, "strict": False}),
    ("parts: [1, -2, 3] n: 1_000 strict: TRUE", {"parts": [1, -2, 3], "n": 1000, "strict": True}),
    ("With n=2 (and later n=5), parts=[7] and strict=false", {"parts": [7], "n": 2, "strict": False}),
    ("label=x, parts=[1], other=9, n=0, strict=true", {"parts": [1], "n": 0, "strict": True}),
    ("n=9223372036854775807, parts=[-9223372036854775808], strict=true",
     {"parts": [-(2**63)], "n": 2**63 - 1, "strict": True}),
])
def test_parse_witness_reads_name_value_pairs(text, expected):
    values, why = nr.parse_witness(text, PARAMS)
    assert why == ""
    assert values == expected
    assert list(values) == [name for name, _ in PARAMS]


@pytest.mark.parametrize("text, reason", [
    ("", "no value for parts, n, strict"),
    ("n=1, strict=true", "no value for parts"),
    ("parts=[1], n=1", "no value for strict"),
    ('parts=["a", "b"], n=1, strict=true', "is not an integer"),
    ("parts=[1], n=9223372036854775808, strict=true", "outside i64"),
    ("parts=[1], n=true, strict=true", "is not an integer"),
    ("parts=[1], n=1, strict=1", "is not a bool"),
    ("parts=3, n=1, strict=true", "is not a list"),
    ("A four-column row such as worker, not-a-date", "no value"),
])
def test_parse_witness_rejects_what_it_cannot_read(text, reason):
    values, why = nr.parse_witness(text, PARAMS)
    assert values is None
    assert reason in why


def test_parse_witness_never_evaluates_the_text(tmp_path):
    marker = tmp_path / "pwned"
    text = f"__import__('pathlib').Path({str(marker)!r}).touch(); parts=[1], n=1, strict=true"
    values, _ = nr.parse_witness(text, PARAMS)
    assert values == {"parts": [1], "n": 1, "strict": True}
    assert not marker.exists()


def test_parse_witness_ignores_decimals_and_identifier_suffixes():
    values, why = nr.parse_witness("n=1.5, parts=[1], strict=true", PARAMS)
    assert values is None and "no value for n" in why
    values, why = nr.parse_witness("n=1abc, parts=[1], strict=true", PARAMS)
    assert values is None


@pytest.mark.parametrize("values, problem", [
    ({"n": 100_000}, ""),
    ({"n": 100_001}, "n = 100001"),
    ({"locations": -200_000}, "locations"),
    ({"total": 10**18}, ""),
    ({"rows": 1_000, "cols": 1_000}, "rows * cols"),
    ({"rows": 10, "cols": 10}, ""),
])
def test_size_problem(values, problem):
    got = nr.size_problem(values)
    assert (problem in got) if problem else got == ""


# ---- pinning

def test_atom_params():
    assert nr.atom_params(HEADER) == PARAMS


def test_pin_requires_pins_every_parameter():
    pinned = nr.pin_requires(HEADER, {"parts": [2, -1], "n": -3, "strict": False})
    assert pinned == "len(parts) == 2 && parts[0] == 2 && parts[1] == (0 - 1) && n == (0 - 3) && !strict"


@pytest.mark.parametrize("values, message", [
    ({"parts": [], "n": 1}, "no value for parameter 'strict'"),
    ({"parts": 1, "n": 1, "strict": True}, "must be a list"),
    ({"parts": [], "n": True, "strict": True}, "must be an integer"),
    ({"parts": [], "n": 1, "strict": 1}, "must be a bool"),
    ({"parts": [], "n": 1, "strict": True, "extra": 2}, "unknown parameters"),
])
def test_pin_requires_rejects_bad_inputs(values, message):
    with pytest.raises(ValueError, match=message):
        nr.pin_requires(HEADER, values)


PORT = "atom take(parts: [i64], n: i64, strict: bool) -> i64\n    requires: n >= 0;\n    ensures: result >= 0;\n    body: n;\n"


def test_pinned_port_keeps_the_original_requires():
    pinned = nr.pinned_port(PORT, "take", {"parts": [], "n": 1, "strict": True})
    assert "requires: (n >= 0) && len(parts) == 0 && n == 1 && strict;" in pinned
    assert "ensures: result >= 0;" in pinned


@pytest.mark.parametrize("port, message", [
    (PORT.replace("take", "other"), "not found"),
    (PORT.replace("    requires: n >= 0;\n", ""), "no single-line requires"),
])
def test_pinned_port_rejects_ports_it_cannot_pin(port, message):
    with pytest.raises(ValueError, match=message):
        nr.pinned_port(port, "take", {"parts": [], "n": 1, "strict": True})


@pytest.mark.parametrize("outcome, message, expected", [
    ("refuted", "Verification Error: Postcondition (ensures) is not satisfied", "breaks"),
    ("proven", "", "holds"),
    ("inconclusive", "Verification Error: Spec contradiction in atom 'take': requires clauses conflict",
     "outside requires"),
    ("inconclusive", "Verification Error: Spec contradiction in atom 'take': ensures clauses conflict",
     "inconclusive"),
    ("inconclusive", "timeout", "inconclusive"),
    ("refuted", "Verification Error: Spec contradiction in atom 'take': requires clauses conflict", "breaks"),
])
def test_port_verdict_tells_an_input_outside_requires_apart(monkeypatch, outcome, message, expected):
    seen = []

    def fake(_bin, text, _timeout):
        seen.append(text)
        return {"outcome": outcome, "status": "s", "diagnostics": [{"message": message}] if message else []}

    monkeypatch.setattr(nr.rb, "verify_text", fake)
    got = nr.port_verdict("mumei", PORT, "take", {"parts": [], "n": 1, "strict": True})
    assert got["verdict"] == expected
    assert len(seen) == 1 and "requires: (n >= 0) && len(parts) == 0" in seen[0]


@pytest.mark.parametrize("value, literal", [(True, "true"), (0, "0"), (5, "5"), (2**255, str(2**255))])
def test_sol_literal(value, literal):
    assert nr.sol_literal(value) == literal


@pytest.mark.parametrize("value", [-1, [1], "1", 1.0])
def test_sol_literal_rejects(value):
    with pytest.raises(ValueError):
        nr.sol_literal(value)


def test_run_solidity_marks_unencodable_inputs_without_running_forge(monkeypatch, tmp_path):
    monkeypatch.setattr(nr.subprocess, "run", lambda *a, **k: pytest.fail("forge must not run"))
    rows = nr.run_solidity("sol-01-token-vault", tmp_path, [{"case": "SOL01-D02", "values": {"a": -1}}])
    assert rows["SOL01-D02"]["unexpressible"] is True
    assert rows["SOL01-D02"]["violates"] is False


def test_every_case_has_a_native_check(cases):
    drivers = "\n".join(p.read_text() for p in nr.driver_files())
    for case in cases:
        token = case["id"].replace("-", "_") if case["language"] == "solidity" else case["id"]
        assert token in drivers, case["id"]


# ---- classification

def native(violates, unexpressible=False):
    row = {"violates": violates, "observed": "x"}
    if unexpressible:
        row["unexpressible"] = True
    return row


def verdict(v):
    return {"verdict": v, "status": "s", "diagnostics": []}


def small_doc():
    return {
        "reference": [{"case": "A", "input": "i", "native": {"buggy": native(True), "fixed": native(False)},
                       "port": {"buggy": verdict("breaks"), "fixed": verdict("holds")}},
                      {"case": "B", "input": "i", "native": {"buggy": native(True), "fixed": native(False)},
                       "port": {"buggy": verdict("holds"), "fixed": verdict("holds")}},
                      {"case": "C", "input": "i", "native": {"buggy": native(False, True), "fixed": native(False)},
                       "port": {"buggy": verdict("breaks"), "fixed": verdict("holds")}}],
        "witnesses": [{"case": "A", "run": 0, "variant": "fixed", "native": {"result": native(True)}},
                      {"case": "A", "run": 1, "variant": "fixed", "native": {"result": native(False)}},
                      {"case": "A", "run": 2, "variant": "fixed",
                       "native": {"result": native(False, True)}},
                      {"case": "B", "run": 0, "variant": "buggy", "classification": "unexpressible",
                       "reason": "no value for n"}],
        "ports": [{"case": "A", "variant": "buggy", "port": {"llm": verdict("breaks")}},
                  {"case": "A", "variant": "buggy", "port": {"llm": verdict("holds")}},
                  {"case": "A", "variant": "fixed", "port": {"llm": verdict("inconclusive")}},
                  {"case": "C", "variant": "buggy", "port": {"llm": verdict("breaks")}},
                  {"case": "Z", "variant": "buggy", "port": {"llm": verdict("breaks")}},
                  {"case": "A", "variant": "fixed", "port": {}, "status": "no port"},
                  {"case": "A", "variant": "buggy", "port": {"llm": verdict("outside requires")}}],
    }


def test_finish_classifies_reference_witnesses_and_ports():
    doc = nr.finish(small_doc(), [{"id": "A", "case_hash": "h"}])
    assert [r["agree"] for r in doc["reference"]] == [True, False, False]
    assert [w["classification"] for w in doc["witnesses"]] == [
        "reproduced", "not reproduced", "unexpressible", "unexpressible"]
    assert doc["witnesses"][2]["reason"] == "x"
    assert [p["status"] for p in doc["ports"]] == [
        "matches", "behaviour changed", "inconclusive", "inconclusive", "inconclusive", "no port",
        "outside requires"]
    assert doc["summary"]["reference"] == {"inputs": 3, "agree": 1, "cases": 3}
    assert doc["summary"]["witnesses"]["fixed/reproduced"] == 1
    assert doc["summary"]["ports"]["buggy/behaviour changed"] == 1
    assert doc["case_hashes"] == {"A": "h"}


def test_finish_is_idempotent():
    once = nr.finish(small_doc(), [{"id": "A", "case_hash": "h"}])
    twice = nr.finish(copy.deepcopy(once), [{"id": "A", "case_hash": "h"}])
    assert once == twice


def test_render_markdown_lists_mismatches_and_fixed_witnesses():
    doc = nr.finish(small_doc(), [{"id": "A", "case_hash": "h"}])
    md = nr.render_markdown(doc)
    assert "1 of 3 inputs" in md
    assert "- B `i`: native buggy breaks, fixed holds; port buggy holds, fixed holds" in md
    assert "- A (run 1): reproduced" in md
    assert "Behaviour changed in: A (buggy)." in md
    assert "| fixed | 1 | 1 | 1 |" in md


# ---- committed results

def test_committed_results_pass_the_check(committed, cases):
    assert nr.check(committed, cases) == []


def test_committed_results_cover_every_case(committed, cases):
    assert {r["case"] for r in committed["reference"]} == {c["id"] for c in cases}
    assert committed["summary"]["reference"]["agree"] == committed["summary"]["reference"]["inputs"]


def test_committed_results_have_no_local_paths(committed):
    text = json.dumps(committed) + nr.REPLAY_MD.read_text()
    assert "/home/" not in text and "/tmp/" not in text


def test_check_reports_a_missing_file(cases):
    assert nr.check(None, cases) == ["proofs/native_replay.json is missing"]


@pytest.mark.parametrize("tamper, message", [
    (lambda d: d["witnesses"][0].update(classification="reproduced" if d["witnesses"][0]["classification"]
                                        != "reproduced" else "not reproduced"), "do not follow"),
    (lambda d: d["witnesses"].pop(), "witness records"),
    (lambda d: d["ports"].append(dict(d["ports"][0])), "port records"),
    (lambda d: d["reference"].append(dict(d["reference"][0])), "missing or duplicated"),
    (lambda d: d["reference"][0].update(replay_hash="0"), "replay.json changed"),
    (lambda d: d["case_hashes"].update({d["reference"][0]["case"]: "0"}), "case changed"),
    (lambda d: d.update(drivers_hash="0"), "native drivers changed"),
    (lambda d: d["specimen_hashes"].update({next(iter(d["specimen_hashes"])): "0"}), "native code changed"),
    (lambda d: d["specimen_hashes"].pop(next(iter(d["specimen_hashes"]))), "native code changed"),
    (lambda d: d.pop("specimen_hashes"), "native code changed"),
    (lambda d: d["input_hashes"].update({next(iter(d["input_hashes"])): "0"}), "changed since the replay"),
    (lambda d: d.pop("input_hashes"), "changed since the replay"),
    (lambda d: d["summary"]["reference"].update(agree=0), "do not follow"),
])
def test_check_catches_tampering(committed, cases, tamper, message):
    doc = copy.deepcopy(committed)
    tamper(doc)
    problems = nr.check(doc, cases)
    assert any(message in p for p in problems), problems


def test_check_catches_an_outdated_markdown(committed, cases, monkeypatch, tmp_path):
    stale = tmp_path / "REPLAY.md"
    stale.write_text("old\n")
    monkeypatch.setattr(nr, "REPLAY_MD", stale)
    assert any("out of date" in p for p in nr.check(committed, cases))


def test_main_check_exit_codes(capsys):
    assert nr.main(["--check"]) == 0
    assert "ok:" in capsys.readouterr().out


def test_main_without_mumei_binary_fails(monkeypatch):
    monkeypatch.delenv("MUMEI_BIN", raising=False)
    monkeypatch.setattr(nr.shutil, "which", lambda _name: None)
    with pytest.raises(SystemExit):
        nr.main([])


def test_check_notices_edited_llm_results(committed, cases, monkeypatch, tmp_path):
    for attr in ("LLM_RESULT", "PORT_RESULT"):
        original = getattr(nr, attr)
        edited = tmp_path / original.name
        edited.write_text(original.read_text() + "\n")
        monkeypatch.setattr(nr, attr, edited)
        stored = copy.deepcopy(committed)
        stored["input_hashes"] = {nr.rel(edited) if k == nr.rel(original) else k: v
                                  for k, v in stored["input_hashes"].items()}
        assert any(f"{nr.rel(edited)} changed" in p for p in nr.check(stored, cases))
        monkeypatch.setattr(nr, attr, original)


def git_specimen(tmp_path, monkeypatch):
    import subprocess
    root = tmp_path / "specimens"
    spec_dir = root / "python" / "py-x"
    (spec_dir / "audit").mkdir(parents=True)
    (spec_dir / "app.py").write_text("x = 1\n")
    (spec_dir / "fixed.patch").write_text("patch\n")
    (spec_dir / "audit" / "result.json").write_text("{}\n")
    (spec_dir / "untracked.py").write_text("y = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "python/py-x/app.py", "python/py-x/fixed.patch", "python/py-x/audit"],
                   cwd=root, check=True)
    monkeypatch.setattr(nr.rb, "SPECIMENS_ROOT", root)
    return spec_dir


@pytest.mark.parametrize("edit, changes", [
    (lambda d: (d / "app.py").write_text("x = 2\n"), True),
    (lambda d: (d / "fixed.patch").write_text("other\n"), True),
    (lambda d: (d / "audit" / "result.json").write_text("[]\n"), False),
    (lambda d: (d / "untracked.py").write_text("y = 2\n"), False),
])
def test_specimen_hash_covers_the_code_and_the_fix(tmp_path, monkeypatch, edit, changes):
    spec_dir = git_specimen(tmp_path, monkeypatch)
    before = nr.specimen_hash("python", "py-x")
    edit(spec_dir)
    assert (nr.specimen_hash("python", "py-x") != before) is changes


def test_specimen_hashes_cover_every_specimen_once(cases):
    hashes = nr.specimen_hashes(cases)
    assert sorted(hashes) == sorted({f"{c['language']}/{c['specimen']}" for c in cases})
