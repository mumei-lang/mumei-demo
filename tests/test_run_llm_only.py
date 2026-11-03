"""Unit tests for scripts/run_llm_only.py.

No model is called: the provider is a stub, and HTTP is faked at the opener."""

import importlib.util
import io
import json
import sys
import http.client
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "run_llm_only.py"

spec = importlib.util.spec_from_file_location("run_llm_only", SCRIPT)
rl = importlib.util.module_from_spec(spec)
sys.modules["run_llm_only"] = rl
spec.loader.exec_module(rl)
rb, rsa = rl.rb, rl.rsa

SENTINEL_KEY = "sk-test-sentinel-not-a-real-key"
APP = "def list_expenses(user):\n    q = \"SELECT * WHERE user = '%s'\" % user\n    return q\n\n\ndef export(name):\n    return open(name).read()\n"
FIXED_APP = APP.replace("\"SELECT * WHERE user = '%s'\" % user", "(\"SELECT * WHERE user = ?\", user)")
PATCH = """--- a/app.py
+++ b/app.py
@@ -1,3 +1,3 @@
 def list_expenses(user):
-    q = "SELECT * WHERE user = '%s'" % user
+    q = ("SELECT * WHERE user = ?", user)
     return q
"""
DOC = {"specimen": "py-01-x", "language": "python", "defects": [
    {"id": "PY01-D01", "file": "app.py", "function": "list_expenses", "line": 2,
     "category": "sql-injection", "cwe": "CWE-89", "class": "vulnerability"},
    {"id": "PY01-D02", "file": "app.py", "function": "export", "line": 7,
     "category": "path-traversal", "cwe": "CWE-22", "class": "vulnerability"},
]}


def _finding(file="app.py", line=2, cwe="CWE-89", category="sql-injection", message="query built with %"):
    return {"file": file, "line": line, "cwe": cwe, "category": category, "message": message}


class StubProvider:
    def __init__(self, model="vendor/model-a", orig=None, fixed=None, reply=None):
        self.model = model
        self.orig = [_finding()] if orig is None else orig
        self.fixed = [_finding(line=3, cwe=None, category="style", message="unused")] if fixed is None else fixed
        self.reply = reply
        self.calls = []

    def complete(self, messages, seed):
        user = messages[1]["content"]
        variant = "fixed" if "user = ?" in user else "orig"
        self.calls.append((variant, seed))
        if self.reply is not None:
            return self.reply, self._usage()
        items = self.fixed if variant == "fixed" else self.orig
        return json.dumps({"findings": items}), self._usage()

    @staticmethod
    def _usage(cost=0.001):
        return {"prompt_tokens": 100, "completion_tokens": 20, "cost_usd": cost, "seconds": 1.5,
                "attempts": 1}


def _tree(tmp_path, specimens=("py-01-x",), fixed=True):
    root = tmp_path / "specimens"
    dirs = []
    for name in specimens:
        d = root / "python" / name
        d.mkdir(parents=True)
        (d / "DEFECTS.json").write_text(json.dumps(dict(DOC, specimen=name)))
        (d / "app.py").write_text(APP)
        if fixed:
            (d / "fixed.patch").write_text(PATCH)
        dirs.append(d)
    return root, dirs


@pytest.fixture
def tree(tmp_path, monkeypatch):
    root, dirs = _tree(tmp_path)
    _patch_root(monkeypatch, root)
    return root, dirs[0]


def _patch_root(monkeypatch, root):
    monkeypatch.setattr(rl, "SPECIMENS_ROOT", root)
    monkeypatch.setattr(rsa, "audit_files", lambda d: sorted(
        p for p in d.rglob("*") if p.is_file() and p.name != "fixed.patch"
        and rl.OUT_DIR not in p.relative_to(d).parts))
    monkeypatch.setattr(rb, "baseline_hash", lambda d: "hash-" + d.name)


def _main(root, *args, provider=None):
    return rl.main(["--summary", str(root / "LLM_ONLY.md"), "--scoreboard-dir", str(root / "scoreboard"),
                    *args], provider=provider)


# --- names and prompt --------------------------------------------------------

@pytest.mark.parametrize("model,slug", [
    ("openai/gpt-6-luna", "openai__gpt-6-luna"),
    ("qwen/qwen3-coder:free", "qwen__qwen3-coder__free"),
    ("gpt-4o", "gpt-4o"),
    ("a b/c", "a__b__c"),
    ("///", "model"),
])
def test_model_slug(model, slug):
    assert rl.model_slug(model) == slug


def test_prompt_hash_is_stable_and_tracks_the_prompt(monkeypatch):
    first = rl.prompt_hash()
    assert first == rl.prompt_hash() and len(first) == 16
    monkeypatch.setattr(rl, "SYSTEM_PROMPT", rl.SYSTEM_PROMPT + " ")
    assert rl.prompt_hash() != first
    monkeypatch.undo()
    monkeypatch.setattr(rl, "PROMPT_VERSION", rl.PROMPT_VERSION + 1)
    assert rl.prompt_hash() != first


def test_source_files_skip_ground_truth_and_binary(tmp_path):
    (tmp_path / "DEFECTS.json").write_text("{}")
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.go").write_text("package b\n")
    (tmp_path / "blob.bin").write_bytes(b"\xff\xfe\x00")
    assert [rel for rel, _ in rl.source_files(tmp_path)] == ["app.py", "sub/b.go"]


def test_user_prompt_numbers_lines():
    text = rl.user_prompt("go", [("main.go", "package main\nfunc f() {}\n"), ("b.go", "")])
    assert "Project language: go. Files: 2." in text
    assert "### main.go" in text and "   1| package main" in text and "   2| func f() {}" in text
    assert "### b.go" in text


def test_system_prompt_gives_no_category_hints():
    for word in ("sql-injection", "path-traversal", "reentrancy"):
        assert word not in rl.SYSTEM_PROMPT


# --- parse_reply / validate ----------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ('{"findings": []}', []),
    ('{"findings": [{"file": "a"}]}', [{"file": "a"}]),
    ('[{"file": "a"}]', [{"file": "a"}]),
    ('```json\n{"findings": [1]}\n```', [1]),
    ('```\n[]\n```', []),
    ("  {\"findings\": []}  \n", []),
    ("not json", None),
    ('{"issues": []}', None),
    ('{"findings": "none"}', None),
    ('"text"', None),
    ("", None),
])
def test_parse_reply(text, expected):
    assert rl.parse_reply(text) == expected


FILES = {"app.py": 7, "pkg/util.py": 3}


@pytest.mark.parametrize("item,ok,reason", [
    (_finding(), True, None),
    (_finding(file="./app.py"), True, None),
    (_finding(file="././pkg/util.py", line=3), True, None),
    (_finding(line="2"), True, None),
    (_finding(line=" 7 "), True, None),
    (_finding(file="other.py"), False, "unknown file"),
    (_finding(file="/etc/passwd"), False, "unknown file"),
    (_finding(file="../app.py"), False, "unknown file"),
    (_finding(file=None), False, "unknown file"),
    (_finding(line=0), False, "line out of range"),
    (_finding(line=8), False, "line out of range"),
    (_finding(line=-1), False, "line out of range"),
    (_finding(line=2.5), False, "line out of range"),
    (_finding(line=True), False, "line out of range"),
    (_finding(line=None), False, "line out of range"),
    (_finding(line="two"), False, "line out of range"),
    ("app.py:2", False, "not an object"),
    (None, False, "not an object"),
])
def test_validate(item, ok, reason):
    raw, invalid = rl.validate([item], FILES)
    assert (len(raw), len(invalid)) == ((1, 0) if ok else (0, 1))
    if not ok:
        assert invalid[0]["reason"] == reason


@pytest.mark.parametrize("cwe,expected", [
    ("CWE-89", [89]), ("CWE-89: SQL injection", [89]), (89, [89]), (None, []),
    (["CWE-22", "CWE-23"], [22, 23]), ("none", []),
])
def test_validate_parses_cwe(cwe, expected):
    raw, _ = rl.validate([_finding(cwe=cwe)], FILES)
    assert raw[0]["cwe"] == expected


def test_validate_normalizes_category_and_message():
    raw, _ = rl.validate([_finding(category=None, message="  two\n  lines  " + "x" * 600)], FILES)
    assert raw[0]["rule"] == "finding"
    assert raw[0]["message"].startswith("two lines ") and len(raw[0]["message"]) == 500
    raw, _ = rl.validate([_finding(category="   ")], FILES)
    assert raw[0]["rule"] == "finding"


def test_validate_keeps_order_and_counts_each_invalid():
    items = [_finding(), _finding(file="x.py"), _finding(line=5, category="b"), 3]
    raw, invalid = rl.validate(items, FILES)
    assert [r["rule"] for r in raw] == ["sql-injection", "b"]
    assert [i["reason"] for i in invalid] == ["unknown file", "not an object"]


# --- Provider -------------------------------------------------------------------

class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _reply(content='{"findings": []}', usage=None):
    doc = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        doc["usage"] = usage
    return FakeResponse(json.dumps(doc).encode())


def _http_error(code):
    return urllib.error.HTTPError("https://example.invalid", code, "err", {}, io.BytesIO(b"{}"))


class Opener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def _provider(opener, base_url="https://openrouter.ai/api/v1", **kw):
    sleeps = []
    p = rl.Provider(SENTINEL_KEY, base_url, "vendor/model-a", opener=opener, sleep=sleeps.append, **kw)
    return p, sleeps


@pytest.mark.parametrize("base_url,openrouter", [
    ("https://openrouter.ai/api/v1", True),
    ("https://openrouter.ai/api/v1/", True),
    ("https://api.openai.com/v1", False),
    ("http://localhost:11434/v1", False),
    ("https://openrouter.ai.example.invalid/v1", False),
])
def test_provider_body(base_url, openrouter):
    p, _ = _provider(Opener(), base_url)
    body = p.body([{"role": "user", "content": "x"}], seed=3)
    assert body["temperature"] == 0 and body["seed"] == 3 and body["model"] == "vendor/model-a"
    assert body["response_format"] == {"type": "json_object"}
    assert ("usage" in body) is openrouter


def test_provider_complete_reads_usage_and_sends_key_only_in_header():
    opener = Opener(_reply('{"findings": []}', {"prompt_tokens": 10, "completion_tokens": 4, "cost": 0.0021}))
    p, sleeps = _provider(opener)
    text, usage = p.complete([{"role": "user", "content": "x"}], seed=1)
    assert text == '{"findings": []}' and sleeps == []
    assert usage["prompt_tokens"] == 10 and usage["completion_tokens"] == 4
    assert usage["cost_usd"] == 0.0021 and usage["attempts"] == 1
    req = opener.requests[0]
    assert req.full_url == "https://openrouter.ai/api/v1/chat/completions"
    assert req.get_header("Authorization") == f"Bearer {SENTINEL_KEY}"
    assert SENTINEL_KEY not in req.data.decode()


@pytest.mark.parametrize("usage,cost", [(None, None), ({}, None), ({"cost": "1"}, None), ({"cost": 0}, 0.0)])
def test_provider_cost_unknown(usage, cost):
    p, _ = _provider(Opener(_reply(usage=usage)))
    assert p.complete([], seed=1)[1]["cost_usd"] == cost


@pytest.mark.parametrize("first", [_http_error(429), _http_error(503), _http_error(500),
                                   urllib.error.URLError("down"), TimeoutError(),
                                   http.client.RemoteDisconnected("closed"),
                                   ConnectionResetError(), json.JSONDecodeError("x", "", 0)])
def test_provider_retries_transient_errors(first):
    p, sleeps = _provider(Opener(first, _reply()))
    _, usage = p.complete([], seed=1)
    assert sleeps == [1] and usage["attempts"] == 2


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_provider_does_not_retry_client_errors(code):
    p, sleeps = _provider(Opener(_http_error(code)))
    with pytest.raises(RuntimeError, match=f"HTTP {code}") as e:
        p.complete([], seed=1)
    assert sleeps == [] and SENTINEL_KEY not in str(e.value)


def test_provider_gives_up_after_retries():
    p, sleeps = _provider(Opener(*[_http_error(429)] * 3), retries=2)
    with pytest.raises(RuntimeError, match="HTTP 429") as e:
        p.complete([], seed=1)
    assert sleeps == [1, 2] and SENTINEL_KEY not in str(e.value)


@pytest.mark.parametrize("doc", [{}, {"choices": []}, {"choices": [{}]}])
def test_provider_rejects_reply_without_content(doc):
    p, _ = _provider(Opener(FakeResponse(json.dumps(doc).encode())))
    with pytest.raises(RuntimeError, match="no message content"):
        p.complete([], seed=1)


def test_provider_null_content_is_empty_text():
    p, _ = _provider(Opener(_reply(content=None)))
    assert p.complete([], seed=1)[0] == ""


# --- review / run_specimen -------------------------------------------------------

def test_review_counts_unparseable_reply_as_error(tmp_path):
    (tmp_path / "app.py").write_text(APP)
    out = rl.review(StubProvider(reply="sorry, no JSON"), tmp_path, "python", 1)
    assert out["tool_errors"] == 1 and out["raw_findings"] == [] and out["usage"]["prompt_tokens"] == 100


def test_review_attaches_enclosing_function(tmp_path):
    (tmp_path / "app.py").write_text(APP)
    out = rl.review(StubProvider(orig=[_finding(line=7, cwe="CWE-22")]), tmp_path, "python", 1)
    assert out["raw_findings"][0]["function"] == "export" and out["tool_errors"] == 0


def test_run_specimen_scores_every_run_and_variant(tree):
    root, d = tree
    provider = StubProvider()
    rec = rl.run_specimen(d, provider, 2, [], "2026-01-01T00:00:00Z", jobs=3)
    assert sorted(provider.calls) == [("fixed", 1), ("fixed", 2), ("orig", 1), ("orig", 2)]
    assert rec["tool"] == "llm-only" and rec["model"] == "vendor/model-a"
    assert rec["prompt_hash"] == rl.prompt_hash() and rec["source_hash"] == "hash-py-01-x"
    assert [r["run"] for r in rec["runs"]] == [1, 2]
    run = rec["runs"][0]
    assert run["counts"]["detected"] == 1 and run["counts"]["missed"] == 1
    assert run["fixed"]["false_alarms"] == 1 and run["fixed"]["still_reported"] == []
    assert run["fixed_usage"]["completion_tokens"] == 20


def test_run_specimen_without_fixed_patch(tmp_path, monkeypatch):
    root, (d,) = _tree(tmp_path, fixed=False)
    _patch_root(monkeypatch, root)
    provider = StubProvider()
    rec = rl.run_specimen(d, provider, 1, [], "t")
    assert provider.calls == [("orig", 1)]
    assert "fixed" not in rec["runs"][0] and "fixed_raw_findings" not in rec["runs"][0]


def test_run_specimen_detects_on_fixed_code_as_still_reported(tree):
    root, d = tree
    rec = rl.run_specimen(d, StubProvider(fixed=[_finding(line=2)]), 1, [], "t")
    assert rec["runs"][0]["fixed"]["still_reported"] == ["PY01-D01"]


# --- rescore ---------------------------------------------------------------------

def _write(d, rec, model="vendor/model-a"):
    path = rl.record_path(d, model)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec))


def test_rescore_round_trip_and_new_review(tree):
    root, d = tree
    rec = rl.run_specimen(d, StubProvider(), 1, [], "t0")
    _write(d, rec)
    again = rl.rescore_record(d, "vendor/model-a", [])
    assert again == rec
    review = {"specimen": "py-01-x", "file": "app.py", "finding_contains": "unused",
              "verdict": "false_positive", "reason": "style"}
    ruled = rl.rescore_record(d, "vendor/model-a", [review])
    assert ruled["runs"][0]["fixed"]["finding_counts"]["false_positive"] == 1
    assert ruled["generated_at"] == "t0"


@pytest.mark.parametrize("change,match", [
    ({"model": "vendor/model-b"}, "current settings"),
    ({"prompt_hash": "0" * 16}, "current settings"),
    ({"prompt_version": 0}, "current settings"),
    ({"temperature": 1}, "current settings"),
    ({"source_hash": "old"}, "specimen changed"),
    ({"runs": []}, "no runs"),
])
def test_rescore_refuses_stale_records(tree, change, match):
    root, d = tree
    rec = rl.run_specimen(d, StubProvider(), 1, [], "t")
    _write(d, dict(rec, **change))
    with pytest.raises(SystemExit, match=match):
        rl.rescore_record(d, "vendor/model-a", [])


def test_rescore_refuses_missing_record_and_fixed_findings(tree):
    root, d = tree
    with pytest.raises(SystemExit, match="missing"):
        rl.rescore_record(d, "vendor/model-a", [])
    rec = rl.run_specimen(d, StubProvider(), 1, [], "t")
    del rec["runs"][0]["fixed_raw_findings"]
    _write(d, rec)
    with pytest.raises(SystemExit, match="no fixed-variant findings"):
        rl.rescore_record(d, "vendor/model-a", [])


# --- aggregate / summary -----------------------------------------------------------

def _records(tmp_path, monkeypatch, providers):
    names = [f"py-0{i}-x" for i in range(1, len(providers) + 1)]
    root, dirs = _tree(tmp_path, names)
    _patch_root(monkeypatch, root)
    return [rl.run_specimen(d, p, 3, [], "t") for d, p in zip(dirs, providers)]


class Flaky(StubProvider):
    """Detects the defect only on odd seeds."""

    def complete(self, messages, seed):
        self.orig = [_finding()] if seed % 2 else []
        return super().complete(messages, seed)


def test_aggregate_spread_union_and_cost(tmp_path, monkeypatch):
    records = _records(tmp_path, monkeypatch, [StubProvider(), Flaky()])
    s = rl.aggregate(records, "vendor/model-a")
    assert s["specimens"] == 2 and s["defects"] == 4 and [r["run"] for r in s["runs"]] == [1, 2, 3]
    assert [r["counts"]["detected"] for r in s["runs"]] == [2, 1, 2]
    assert s["detected"] == {"mean": 1.67, "min": 1, "max": 2}
    assert s["detected_in_any_run"] == 2 and s["detected_in_every_run"] == 1
    assert s["runs"][0]["usage"]["calls"] == 4
    assert s["cost_usd"] == pytest.approx(0.012) and s["cost_unknown_calls"] == 0
    assert s["fixed_false_alarms"] == {"mean": 2, "min": 2, "max": 2}


def test_aggregate_counts_calls_without_cost(tmp_path, monkeypatch):
    class NoCost(StubProvider):
        @staticmethod
        def _usage(cost=None):
            return StubProvider._usage(cost=None)
    s = rl.aggregate(_records(tmp_path, monkeypatch, [NoCost()]), "m")
    assert s["cost_usd"] == 0 and s["cost_unknown_calls"] == 6
    assert "6 calls without a reported cost" in rl.render_summary(s, [])


def test_run_views_refuse_mismatched_runs(tmp_path, monkeypatch):
    records = _records(tmp_path, monkeypatch, [StubProvider(), StubProvider()])
    records[1]["runs"] = records[1]["runs"][:1]
    with pytest.raises(SystemExit, match="no run 2"):
        rl.aggregate(records, "m")


def test_render_summary_table(tmp_path, monkeypatch):
    s = rl.aggregate(_records(tmp_path, monkeypatch, [StubProvider()]), "vendor/model-a")
    text = rl.render_summary(s, [{"specimen": "py-01-x", "file": "app.py", "finding_contains": "gone"}])
    assert "`vendor/model-a`" in text and "| 1 | 1/2 (50%) |" in text
    assert text.count("\n| ") == 4 and "Stale reviews" in text and "`gone`" in text


def test_stale_reviews(tmp_path, monkeypatch):
    root, (d,) = _tree(tmp_path)
    _patch_root(monkeypatch, root)
    used = {"specimen": "py-01-x", "file": "app.py", "finding_contains": "unused",
            "verdict": "false_positive", "reason": "r"}
    unused = dict(used, finding_contains="never matches")
    rec = rl.run_specimen(d, StubProvider(), 1, [used, unused], "t")
    assert rl.stale_reviews([rec], [used, unused]) == [unused]


# --- main ----------------------------------------------------------------------------

def test_main_writes_outputs(tree):
    root, d = tree
    assert _main(root, "--runs", "2", provider=StubProvider()) == 0
    rec = json.loads(rl.record_path(d, "vendor/model-a").read_text())
    assert len(rec["runs"]) == 2
    summary = json.loads((root / "scoreboard" / "llm_only.json").read_text())
    assert summary["model"] == "vendor/model-a" and summary["detected"]["max"] == 1
    assert "# LLM-only review" in (root / "LLM_ONLY.md").read_text()


@pytest.mark.parametrize("args,match", [
    (["--runs", "0"], "at least 1"),
    (["--only", "nope"], "unknown specimen"),
    (["--model", "vendor/model-b"], "differs from LLM_MODEL"),
])
def test_main_rejects_bad_arguments(tree, args, match):
    root, _ = tree
    with pytest.raises(SystemExit, match=match):
        _main(root, *args, provider=StubProvider())


def test_main_requires_a_key(tree, monkeypatch):
    root, _ = tree
    for name in ("LLM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="is not set"):
        _main(root)


def test_provider_from_env(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", SENTINEL_KEY)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setenv("LLM_MODEL", "vendor/model-a")
    p = rl.provider_from_env(30)
    assert p.base_url == rl.DEFAULT_BASE_URL and p.model == "vendor/model-a" and p.timeout == 30


def test_main_only_reviews_named_specimens_and_rescores_others(tmp_path, monkeypatch):
    root, dirs = _tree(tmp_path, ("py-01-x", "py-02-x", "py-03-x"))
    _patch_root(monkeypatch, root)
    _main(root, "--runs", "1", "--only", "py-01-x,py-02-x", provider=StubProvider())
    assert not rl.record_path(dirs[2], "vendor/model-a").exists()
    provider = StubProvider(orig=[])
    _main(root, "--runs", "1", "--only", "py-02-x", provider=provider)
    assert len(provider.calls) == 2
    first = json.loads(rl.record_path(dirs[0], "vendor/model-a").read_text())
    second = json.loads(rl.record_path(dirs[1], "vendor/model-a").read_text())
    assert first["runs"][0]["counts"]["detected"] == 1 and second["runs"][0]["counts"]["detected"] == 0
    summary = json.loads((root / "scoreboard" / "llm_only.json").read_text())
    assert summary["specimens"] == 2


def test_main_rescore_without_model_calls(tree, monkeypatch):
    root, d = tree
    with pytest.raises(SystemExit, match="no LLM-only reviews"):
        _main(root, "--rescore", "--model", "vendor/model-a")
    _main(root, "--runs", "1", provider=StubProvider())

    class Boom(StubProvider):
        def complete(self, *a):
            raise AssertionError("model called during --rescore")
    monkeypatch.setenv("LLM_MODEL", "vendor/model-a")
    assert _main(root, "--rescore", provider=Boom()) == 0


def test_key_never_written(tree, monkeypatch, capsys):
    root, d = tree
    monkeypatch.setenv("LLM_API_KEY", SENTINEL_KEY)
    monkeypatch.setenv("LLM_MODEL", "vendor/model-a")
    monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    opener = Opener(*[_reply(json.dumps({"findings": [_finding()]}), {"cost": 0.001})
                      for _ in range(2)])
    provider = rl.provider_from_env(10)
    provider.opener = opener
    assert _main(root, "--runs", "1", "--jobs", "1", provider=provider) == 0
    out = capsys.readouterr()
    assert SENTINEL_KEY not in out.out + out.err
    for p in root.rglob("*"):
        if p.is_file():
            assert SENTINEL_KEY not in p.read_text(errors="replace"), p
