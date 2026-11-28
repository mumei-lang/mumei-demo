"""Regression tests for the verify-distribution reference validation wiring."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_verify_distribution_reference.py"
spec = importlib.util.spec_from_file_location("check_verify_distribution_reference", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def report(*, runtime_status="skipped", native_status="accepted"):
    runtime = {"status": runtime_status}
    if runtime_status == "skipped":
        runtime["reason"] = "runtime_observations_not_enabled"
    return {
        "schema_version": "mumei.verify-distribution-report/v1",
        "scope": "native_first_distribution_role_orchestration",
        "checks_not_performed": [
            "adapter_evidence",
            "deep_acceptance_fold",
            "unified_verdict",
        ],
        "roles": {
            "proof_certificate": {"status": "accepted"},
            "native_source_llvm": {"status": native_status, "reason": "unclaimed_exit_outcome", "exit_code": 1},
            "artifact_reproduction": {"status": native_status, "reason": "unclaimed_exit_outcome", "exit_code": 1},
            "runtime_observation": runtime,
        },
    }


def test_positive_runtime_off_requires_role_separation():
    module.validate_positive_report(report(), runtime=False)


def test_positive_runtime_on_requires_explicit_runtime_acceptance():
    data = report(runtime_status="accepted")
    module.validate_positive_report(data, runtime=True)


def test_runtime_off_rejects_silent_runtime_acceptance_or_skip_change():
    data = report(runtime_status="accepted")
    with pytest.raises(ValueError):
        module.validate_positive_report(data, runtime=False)


def test_wrong_build_id_requires_unclaimed_inconclusive_native_roles():
    module.validate_wrong_build_id_report(report(native_status="inconclusive"))
    with pytest.raises(ValueError):
        module.validate_wrong_build_id_report(report(native_status="accepted"))


def test_trusted_build_id_channel_accepts_single_lowercase_sha256_line(tmp_path):
    channel = tmp_path / "trusted-build-id.txt"
    channel.write_text("a" * 64 + "\n", encoding="utf-8")
    assert module.read_trusted_build_id_channel(channel) == "a" * 64

    channel.write_text("b" * 64, encoding="utf-8")
    assert module.read_trusted_build_id_channel(channel) == "b" * 64

    channel.write_bytes(b"c" * 64 + b"\r\n")
    assert module.read_trusted_build_id_channel(channel) == "c" * 64


def test_trusted_build_id_channel_rejects_missing_file(tmp_path):
    with pytest.raises(ValueError, match="missing"):
        module.read_trusted_build_id_channel(tmp_path / "trusted-build-id.txt")


@pytest.mark.parametrize(
    ("content", "reason"),
    (
        ("", "empty"),
        ("\n", "empty"),
        ("a" * 63 + "\n", "lowercase sha256"),
        ("A" * 64 + "\n", "lowercase sha256"),
        ("g" * 64 + "\n", "lowercase sha256"),
        (" " + "a" * 64 + "\n", "lowercase sha256"),
        ("a" * 64 + " \n", "lowercase sha256"),
        ("a" * 64 + "\v", "lowercase sha256"),
        ("a" * 64 + "\r", "lowercase sha256"),
        ("a" * 64 + "\n\n", "exactly one line"),
        ("a" * 64 + "\n" + "b" * 64 + "\n", "exactly one line"),
    ),
    ids=("empty-file", "blank-line", "short", "uppercase", "non-hex", "leading-space", "trailing-space", "vertical-tab", "carriage-return-only", "extra-blank", "two-lines"),
)
def test_trusted_build_id_channel_rejects_empty_or_malformed_content(tmp_path, content, reason):
    channel = tmp_path / "trusted-build-id.txt"
    channel.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=reason):
        module.read_trusted_build_id_channel(channel)


def test_consumer_invocations_use_trusted_channel_readback(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture.mm"
    fixture.write_text("atom main() -> i64\nrequires: true;\nbody: { 0 };\n", encoding="utf-8")
    monkeypatch.setattr(module, "TRUSTED_FIXTURE", fixture.resolve())
    fake_core = tmp_path / "mumei"
    fake_core.write_text("#!/bin/sh\n", encoding="utf-8")

    def fake_build(argv, **kwargs):
        bundle = Path(argv[argv.index("-o") + 1])
        bundle.mkdir(parents=True)
        (bundle / "native-bundle.json").write_text("{}", encoding="utf-8")
        return module.subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_build)
    monkeypatch.setattr(module, "sha256_file", lambda path: "a" * 64)
    monkeypatch.setattr(module, "read_trusted_build_id_channel", lambda path: "b" * 64)
    invocations = []

    def fake_run_checked(argv, *, cwd, expected_exit=0):
        invocations.append(list(argv))
        report_path = Path(argv[argv.index("--output") + 1])
        wrong_id = hashlib.sha256(b"not-the-trusted-build-id").hexdigest()
        build_id = argv[argv.index("--expected-build-id") + 1]
        runtime = "--enable-runtime-observations" in argv
        data = report(native_status="inconclusive") if build_id == wrong_id else report(
            runtime_status="accepted" if runtime else "skipped"
        )
        report_path.write_text(json.dumps(data), encoding="utf-8")
        stderr = ""
        if report_path.name == "verify-distribution-extra-file.json":
            stderr = "verify-distribution: bundle layout contains an undeclared file"
        elif report_path.name == "verify-distribution-extra-symlink.json":
            stderr = "verify-distribution: bundle layout contains an undeclared symlink"
        return module.subprocess.CompletedProcess(argv, expected_exit, stdout="", stderr=stderr)

    monkeypatch.setattr(module, "run_checked", fake_run_checked)
    parser = module.build_parser()
    args = parser.parse_args([
        "--mumei-bin", str(fake_core),
        "--mumei-agent-python", "python",
        "--mumei-agent-repo", str(tmp_path),
        "--source", str(fixture),
        "--work-dir", str(tmp_path / "out"),
    ])
    module.validate_fixture(args)

    assert (tmp_path / "out" / module.TRUSTED_BUILD_ID_FILE).read_text(encoding="utf-8") == "a" * 64 + "\n"
    supplied = [argv[argv.index("--expected-build-id") + 1] for argv in invocations]
    assert len(supplied) == 5
    assert supplied[:2] == ["b" * 64, "b" * 64]
    assert supplied[2] == hashlib.sha256(b"not-the-trusted-build-id").hexdigest()
    assert supplied[3:] == ["b" * 64, "b" * 64]
    assert "a" * 64 not in supplied
    assert all("--require-exact-bundle-layout" in argv for argv in invocations)
    bundle = tmp_path / "out" / "bundle"
    assert not (bundle / "layout-extra.txt").exists()
    assert not (bundle / "layout-extra-link").exists()


def test_reference_wiring_reads_back_channel_before_consumer_invocations():
    script = SCRIPT_PATH.read_text()
    write_index = script.index("channel_path.write_text")
    read_index = script.index("trusted_build_id = read_trusted_build_id_channel(channel_path)")
    off_index = script.index("verifier_argv(args, bundle, off_report, trusted_build_id)")
    on_index = script.index("verifier_argv(args, bundle, on_report, trusted_build_id)")
    assert write_index < read_index < off_index < on_index
    assert "verifier_argv(args, bundle, off_report, producer_build_id)" not in script
    assert "verifier_argv(args, bundle, on_report, producer_build_id)" not in script
    assert "--require-exact-bundle-layout" in script
    assert "validate_exact_layout_rejections" in script


def test_integration_workflow_uses_trusted_fixture_and_generated_bundle():
    workflow = (ROOT / ".github/workflows/integration.yml").read_text()
    assert "scripts/check_verify_distribution_reference.py" in workflow
    assert "scenarios/native_observations_accept/src/main.mm" in workflow
    assert "reports/verify_distribution/latest" in workflow
    step_start = workflow.index("Validate verify-distribution reference fixture")
    step_end = workflow.index("Run integrated demo scenarios", step_start)
    step = workflow[step_start:step_end]
    assert "--enable-runtime-observations" not in step
    assert "external" not in step.lower()


def test_script_runtime_opt_in_is_internal_to_trusted_reference_validation():
    script = SCRIPT_PATH.read_text()
    assert "--enable-runtime-observations" in script
    assert "trusted fixture" in script
    assert "adapter_evidence" in script
    assert "--memory-bound-mb" in script
    assert "--attempt-timeout" in script


def test_docs_state_role_boundary_and_runtime_opt_in():
    docs = (ROOT / "docs/CI_REFERENCE.md").read_text()
    for fragment in (
        "role-separated orchestration, not a deep acceptance fold",
        "not a unified verdict, not a proof grade",
        "adapter evidence is outside the verifier's scope",
        "trusted fixture source and the bundle built from it only",
        "unconditional execution of external input artifacts",
        "trusted-build-id.txt",
        "reads that file back for the consumer verifier invocations",
        "independent integrity-protected channel",
        "consistency check only; it is not a trust root",
        "do not add verdict, role, or status vocabulary",
        "--require-exact-bundle-layout",
        "raw `mumei native-bundle build` output shape",
        "undeclared extra-file and symlink probes",
        "not a packaging policy",
        "does not generate packaging metadata",
    ):
        assert fragment in docs


def test_reference_test_is_in_explicit_pytest_list():
    workflow = (ROOT / ".github/workflows/integration.yml").read_text()
    assert "tests/test_verify_distribution_reference.py" in workflow


def test_positive_report_rejects_input_drift_or_missing_boundary_checks():
    data = report()
    data["inputs_changed"] = True
    with pytest.raises(ValueError):
        module.validate_positive_report(data, runtime=False)

    data = report()
    data["checks_not_performed"].remove("adapter_evidence")
    with pytest.raises(ValueError):
        module.validate_positive_report(data, runtime=False)


def test_legacy_build_id_file_is_cleaned_for_reused_workdir(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture.mm"
    fixture.write_text("atom main() -> i64\nrequires: true;\nbody: { 0 };\n", encoding="utf-8")
    monkeypatch.setattr(module, "TRUSTED_FIXTURE", fixture.resolve())
    fake_core = tmp_path / "mumei"
    fake_core.write_text("#!/bin/sh\n", encoding="utf-8")
    work_dir = tmp_path / "out"
    work_dir.mkdir()
    legacy = work_dir / "build_id.txt"
    legacy.write_text("old\n", encoding="utf-8")

    def failed_build(argv, **kwargs):
        return module.subprocess.CompletedProcess(argv, 1)

    monkeypatch.setattr(module.subprocess, "run", failed_build)
    parser = module.build_parser()
    args = parser.parse_args([
        "--mumei-bin", str(fake_core),
        "--mumei-agent-python", "python",
        "--mumei-agent-repo", str(tmp_path),
        "--source", str(fixture),
        "--work-dir", str(work_dir),
    ])
    with pytest.raises(RuntimeError, match="build failed"):
        module.validate_fixture(args)
    assert not legacy.exists()


def test_generated_workdir_preserves_unexpected_files(tmp_path, monkeypatch):
    unexpected = tmp_path / "user-file.txt"
    unexpected.write_text("keep", encoding="utf-8")
    prior_bundle = tmp_path / "bundle"
    prior_bundle.mkdir()
    (prior_bundle / "program").write_text("prior", encoding="utf-8")
    fixture = tmp_path / "fixture.mm"
    fixture.write_text("atom main() -> i64\nrequires: true;\nbody: { 0 };\n", encoding="utf-8")
    monkeypatch.setattr(module, "TRUSTED_FIXTURE", fixture.resolve())
    real_iterdir = Path.iterdir

    def bundle_first_iterdir(path):
        children = list(real_iterdir(path))
        if path == tmp_path:
            children.sort(key=lambda child: child.name != "bundle")
        return iter(children)

    monkeypatch.setattr(Path, "iterdir", bundle_first_iterdir)
    fake_core = tmp_path / "mumei"
    fake_core.write_text("#!/bin/sh\n", encoding="utf-8")
    parser = module.build_parser()
    args = parser.parse_args([
        "--mumei-bin", str(fake_core),
        "--mumei-agent-python", "python",
        "--mumei-agent-repo", str(tmp_path),
        "--source", str(fixture),
        "--work-dir", str(tmp_path),
    ])
    with pytest.raises(ValueError, match="not generated"):
        module.validate_fixture(args)
    assert unexpected.read_text(encoding="utf-8") == "keep"
    assert (prior_bundle / "program").read_text(encoding="utf-8") == "prior"


def test_runtime_validation_rejects_non_reference_source(tmp_path):
    parser = module.build_parser()
    fixture = tmp_path / "other.mm"
    fixture.write_text("atom main() -> i64\nrequires: true;\nbody: { 0 };\n", encoding="utf-8")
    args = parser.parse_args([
        "--mumei-bin", "mumei",
        "--mumei-agent-python", "python",
        "--mumei-agent-repo", str(tmp_path),
        "--source", str(fixture),
        "--work-dir", str(tmp_path / "out"),
    ])
    with pytest.raises(ValueError, match="trusted fixture"):
        module.validate_fixture(args)
