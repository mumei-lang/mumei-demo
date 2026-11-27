from __future__ import annotations

import os
import sys
from pathlib import Path

import json

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_adversarial_port_corpus as adversarial  # noqa: E402
import port_fidelity as fidelity  # noqa: E402
import run_contract_bench as cb  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def mumei_bin() -> str | None:
    candidates = []
    if os.environ.get("MUMEI_BIN"):
        candidates.append(Path(os.environ["MUMEI_BIN"]))
    candidates.extend([
        REPO_ROOT.parent / "mumei" / "target" / "debug" / "mumei",
        REPO_ROOT.parent / "mumei" / "target" / "release" / "mumei",
    ])
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    return None


MUMEI_BIN = mumei_bin()
requires_mumei = pytest.mark.skipif(MUMEI_BIN is None, reason="mumei binary is not available")


def case_by_id(case_id: str) -> dict:
    return next(case for case in cb.load_cases()[0] if case["id"] == case_id)


def test_struct_comparison_targets_accepted_output_not_failure_sentinels() -> None:
    case = case_by_id("SOL03-D08")
    candidate = "Payout { ok: transfer_ok, owed: amount }"

    text = fidelity.output_compare_text(case, candidate, "fixed")

    assert "let reference = {" in text
    assert "let candidate = {" in text
    assert "!(reference.ok && candidate.ok)" in text
    assert "(reference.owed == candidate.owed)" in text
    assert "atom compare_getReward" in text


def test_primitive_comparison_is_not_vacuous() -> None:
    case = case_by_id("GO01-D04")

    text = fidelity.output_compare_text(case, "if has_sku { sku } else { 0 }", "fixed")

    assert "reference == candidate" in text
    assert "reference.ok" not in text


def test_loop_equivalence_is_explicitly_unavailable_without_committed_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    case = {**case_by_id("PY02-D05"), "id": "PY02-D05-no-bounded-inputs"}

    def forbidden(*_args):
        pytest.fail("loop comparison must not call the verifier")

    monkeypatch.setattr(fidelity, "verify_text", forbidden)

    evidence = fidelity.output_equivalence(case, "0", "unused", 5, "fixed")

    assert evidence["outcome"] == "unavailable"
    assert evidence["reason"] == "loop_equivalence_unverified"


def test_bounded_interaction_harness_pins_inputs_and_runtime_exit_codes() -> None:
    case = case_by_id("PY02-D05")
    reference = fidelity.body_inner(fidelity.split_port(case["ports"]["fixed"], case["atom"])[2]).strip()
    values = {"daily": [0, 10], "n": 2, "threshold": 5}

    text = fidelity.bounded_interaction_text(case, reference, values, "fixed")

    assert "atom main() -> i64" in text
    assert text.count("let daily = [0, 10];") == 3
    assert "if !(len(daily) == n && n >= 1) { 43 }" in text
    assert "if reference == candidate { 0 } else { 42 }" in text


def test_bounded_interaction_tool_failure_is_inconclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fidelity, "run_bounded_interaction_text", lambda *_args: {
        "exit_code": 1, "output_tail": "compiler error", "seconds": 0.1, "budget_seconds": 5})
    case = case_by_id("PY02-D05")
    reference = fidelity.body_inner(fidelity.split_port(case["ports"]["fixed"], case["atom"])[2]).strip()

    evidence = fidelity.output_equivalence(case, reference, "unused", 5, "fixed")

    assert evidence["outcome"] == "inconclusive"
    assert evidence["reason"] == "bounded_interaction_tool_failure"
    assert evidence["failure_kind"] == "environment_failure"
    assert evidence["interaction"]["expected_executions"] == 4


def test_postcondition_refutation_is_divergence_but_safety_failure_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    case = case_by_id("SOL03-D08")
    candidate = "Payout { ok: transfer_ok, owed: amount }"
    responses = iter([
        {"outcome": "refuted", "status": "failed", "diagnostics": [
            {"atom": "compare_getReward", "code": "failed", "message": "Verification Error: Postcondition (ensures) is not satisfied."}]},
        {"outcome": "refuted", "status": "failed", "diagnostics": [
            {"atom": "compare_getReward", "code": "failed", "message": "Verification Error: Postcondition (ensures) is not satisfied."}]},
        {"outcome": "refuted", "status": "failed", "diagnostics": [
            {"atom": "compare_getReward", "code": "failed", "message": "Verification Error: Division by zero."}]},
    ])
    monkeypatch.setattr(fidelity, "verify_text", lambda *_args: next(responses))

    assert fidelity.output_equivalence(case, candidate, "unused", 5, "fixed")["outcome"] == "diverged"
    assert fidelity.output_equivalence(case, candidate, "unused", 5, "fixed")["outcome"] == "inconclusive"


def test_opaque_helper_atom_counterexample_is_inconclusive_not_divergence(monkeypatch: pytest.MonkeyPatch) -> None:
    case = case_by_id("GO02-D03")
    monkeypatch.setattr(fidelity, "verify_text", lambda *_args: {
        "outcome": "refuted", "status": "failed", "diagnostics": [
            {"atom": "compare_formatSummary", "code": "failed",
             "message": "Verification Error: Postcondition (ensures) is not satisfied."}]})

    evidence = fidelity.output_equivalence(case, "slice_to(parts, 0, top)", "unused", 5, "fixed")

    assert evidence["outcome"] == "inconclusive"
    assert evidence["reason"] == "opaque_atom_call_counterexample"
    assert evidence["opaque_atom_calls"] == ["slice_to"]


def test_bounded_interaction_timeout_is_budget_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fidelity, "run_bounded_interaction_text", lambda *_args: {
        "result": "error", "error": "TimeoutExpired", "timeout": True,
        "seconds": 5.0, "budget_seconds": 5})
    case = case_by_id("PY02-D05")
    reference = fidelity.body_inner(fidelity.split_port(case["ports"]["fixed"], case["atom"])[2]).strip()

    evidence = fidelity.output_equivalence(case, reference, "unused", 5, "fixed")

    assert evidence["outcome"] == "inconclusive"
    assert evidence["status"] == "timeout"
    assert evidence["reason"] == "bounded_interaction_timeout"
    assert evidence["failure_kind"] == "budget_exhausted"


def test_bounded_interaction_policy_rejects_extra_input_keys(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = {**case_by_id("PY02-D05"), "id": "PY02-D05-extra-input-key"}
    proofs = tmp_path / "proofs"
    proofs.mkdir()
    data = json.loads((fidelity.REPO_ROOT / "proofs/output-equivalence-policy.json").read_text())
    data["cases"][case["id"]] = {"bounded_interaction_inputs": [
        {"name": "bad", "values": {"daily": [1], "n": 1, "threshold": 0}, "extra": True}]}
    (proofs / "output-equivalence-policy.json").write_text(json.dumps(data))
    monkeypatch.setattr(fidelity, "REPO_ROOT", tmp_path)

    with pytest.raises(ValueError, match="exactly name and values"):
        fidelity.output_policy(case)


def test_bounded_interaction_outside_requires_is_inconclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fidelity, "run_bounded_interaction_text", lambda *_args: {
        "exit_code": 43, "seconds": 0.1, "budget_seconds": 5})
    case = case_by_id("PY02-D05")
    reference = fidelity.body_inner(fidelity.split_port(case["ports"]["fixed"], case["atom"])[2]).strip()

    evidence = fidelity.output_equivalence(case, reference, "unused", 5, "fixed")

    assert evidence["outcome"] == "inconclusive"
    assert evidence["reason"] == "bounded_interaction_input_outside_requires"
    assert evidence["failure_kind"] == "unsupported"


def test_bounded_interaction_does_not_execute_effectful_or_ffi_preludes() -> None:
    case = {**case_by_id("PY02-D05"), "prelude": 'extern \"Rust\" { fn side_effect(); }\n'}
    reference = fidelity.body_inner(fidelity.split_port(case["ports"]["fixed"], case["atom"])[2]).strip()

    evidence = fidelity.bounded_interaction_equivalence(case, reference, "unused", 5, "fixed")

    assert evidence["outcome"] == "unavailable"
    assert evidence["reason"] == "bounded_interaction_effectful_prelude"


def test_output_equality_overrides_lint_only_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fidelity, "replay_inputs", lambda case: (_ for _ in ()).throw(OSError("no fixture")))
    monkeypatch.setattr(fidelity, "lint_findings", lambda *_args: [
        {"kind": "success_flag_rewrite", "message": "syntactic warning"}])
    monkeypatch.setattr(fidelity, "output_equivalence", lambda *_args, **_kwargs: {
        "outcome": "matched", "method": "solver_output_compare", "status": "success"})
    case = case_by_id("SOL03-D08")

    gated = cb.apply_port_fidelity_gate(case, "Payout { ok: transfer_ok, owed: amount }",
                                        {"outcome": "proven", "status": "success", "diagnostics": []},
                                        "unused", 5, "fixed")

    assert gated["fidelity_gate"]["decision"] == "accepted"
    assert cb.project_fidelity_result(gated)["outcome"] == "proven"


@pytest.mark.parametrize("kind", ["silent_repair", "missing_modeled_operation", "self_call"])
def test_output_equality_does_not_override_structural_fidelity_loss(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fidelity, "replay_inputs", lambda case: (_ for _ in ()).throw(OSError("no fixture")))
    monkeypatch.setattr(fidelity, "lint_findings", lambda *_args: [
        {"kind": kind, "message": "structural warning"}])
    monkeypatch.setattr(fidelity, "output_equivalence", lambda *_args, **_kwargs: {
        "outcome": "matched", "method": "solver_output_compare", "status": "success"})
    case = case_by_id("SOL03-D08")

    gated = cb.apply_port_fidelity_gate(case, "Payout { ok: transfer_ok, owed: amount }",
                                        {"outcome": "proven", "status": "success", "diagnostics": []},
                                        "unused", 5, "fixed")

    assert gated["fidelity_gate"]["decision"] == "blocked"
    assert cb.project_fidelity_result(gated)["failure_kind"] == "unsupported"


def test_output_divergence_blocks_despite_confirming_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = [{"name": "counterexample", "source": "test", "values": {"transfer_ok": True, "amount": 1}}]
    monkeypatch.setattr(fidelity, "replay_inputs", lambda case: (inputs, "hash"))
    monkeypatch.setattr(fidelity, "port_verdict", lambda *_args: {
        "verdict": "holds", "status": "holds", "diagnostics": [], "verification_attempted": True})
    monkeypatch.setattr(fidelity, "lint_findings", lambda *_args: [])
    monkeypatch.setattr(fidelity, "output_equivalence", lambda *_args, **_kwargs: {
        "outcome": "diverged", "method": "solver_output_compare", "status": "failed"})
    case = case_by_id("SOL03-D08")

    gated = cb.apply_port_fidelity_gate(case, "Payout { ok: transfer_ok, owed: amount }",
                                        {"outcome": "proven", "status": "success", "diagnostics": []},
                                        "unused", 5, "fixed")
    projected = cb.project_fidelity_result(gated)

    assert gated["outcome"] == "proven"
    assert gated["fidelity_gate"]["decision"] == "blocked"
    assert projected["outcome"] == "inconclusive"
    assert projected["failure_kind"] == "unsupported"
    assert "output-equivalence:diverged" in projected["status"]


def test_matched_output_equality_overrides_guard_folding_false_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fidelity, "replay_inputs", lambda case: (_ for _ in ()).throw(OSError("no fixture")))
    monkeypatch.setattr(fidelity, "lint_findings", lambda *_args: [
        {"kind": "guard_folding", "message": "syntactic warning"}])
    monkeypatch.setattr(fidelity, "output_equivalence", lambda *_args, **_kwargs: {
        "outcome": "matched", "method": "solver_output_compare", "status": "success"})
    case = case_by_id("SOL03-D08")

    gated = cb.apply_port_fidelity_gate(case, "Payout { ok: transfer_ok, owed: amount }",
                                        {"outcome": "proven", "status": "success", "diagnostics": []},
                                        "unused", 5, "fixed")

    assert gated["fidelity_gate"]["decision"] == "accepted"


def semantic_corpus_cases() -> list[dict]:
    doc = adversarial.load_corpus()
    return [case for case in doc["cases"] if "expected_output_equivalence" in case]


@requires_mumei
@pytest.mark.parametrize("corpus_case", semantic_corpus_cases(), ids=lambda case: case["id"])
def test_adversarial_output_equivalence_controls_with_real_verifier(corpus_case: dict) -> None:
    case = adversarial._port_case(corpus_case)

    evidence = fidelity.output_equivalence(case, corpus_case["candidate_body"], MUMEI_BIN, 10,
                                           corpus_case.get("variant", "buggy"))

    assert evidence["outcome"] == corpus_case["expected_output_equivalence"]


@requires_mumei
def test_exact_nonloop_fixed_reference_copies_match_with_real_verifier() -> None:
    mismatches = []
    compared = 0
    unavailable_loops = 0
    for case in cb.load_cases()[0]:
        reference = fidelity.body_inner(fidelity.split_port(case["ports"]["fixed"], case["atom"])[2]).strip()
        evidence = fidelity.output_equivalence(case, reference, MUMEI_BIN, 10, "fixed")
        if ((evidence["outcome"] == "unavailable" and evidence.get("reason") == "loop_equivalence_unverified")
                or evidence.get("method") == "bounded_native_interaction"):
            unavailable_loops += 1
            continue
        compared += 1
        if evidence["outcome"] != "matched":
            mismatches.append((case["id"], evidence["outcome"], evidence.get("diagnostics")))

    assert unavailable_loops >= 1
    assert compared >= 65
    assert mismatches == []


@requires_mumei
def test_exact_loop_fixed_reference_has_bounded_interaction_agreement_with_real_verifier() -> None:
    case = case_by_id("PY02-D05")
    reference = fidelity.body_inner(fidelity.split_port(case["ports"]["fixed"], case["atom"])[2]).strip()

    evidence = fidelity.output_equivalence(case, reference, MUMEI_BIN, 20, "fixed")

    assert evidence["outcome"] == "inconclusive"
    assert evidence["reason"] == "bounded_interactions_matched"
    assert evidence["method"] == "bounded_native_interaction"
    assert [attempt["result"] for attempt in evidence["inputs"]] == ["matched"] * 4


@requires_mumei
def test_first_day_only_loop_positive_control_diverges_with_real_verifier() -> None:
    corpus_case = next(case for case in adversarial.load_corpus()["cases"]
                       if case["id"] == "py02-loop-first-day-only-positive-control")
    case = adversarial._port_case(corpus_case)

    evidence = fidelity.output_equivalence(case, corpus_case["candidate_body"], MUMEI_BIN, 20, "fixed")

    assert evidence["outcome"] == "diverged"
    assert evidence["method"] == "bounded_native_interaction"
    assert evidence["divergence_input"]["name"] == "second-day-only-overtime"
    assert "diverged" in [attempt["result"] for attempt in evidence["inputs"]]


@requires_mumei
def test_failure_path_payload_noise_is_boundary_only_not_output_divergence_with_real_verifier() -> None:
    case = case_by_id("PY01-D10")
    candidate = "if value <= 0 { Parsed { ok: false, value: value } } else { Parsed { ok: true, value: value } }"

    evidence = fidelity.output_equivalence(case, candidate, MUMEI_BIN, 10, "fixed")

    assert evidence["outcome"] == "inconclusive"
    assert evidence["reason"] == "abstraction_boundary_only"
    assert evidence["exact_output"]["outcome"] == "diverged"
    assert evidence["verification"]["expected_calls"] == 2


def test_output_policy_adjudicates_dontcare_failure_state_and_rounding() -> None:
    sol02 = case_by_id("SOL02-D11")
    sol03 = case_by_id("SOL03-D08")
    ts09 = case_by_id("TS03-D09")

    sol02_text = fidelity.output_compare_text(sol02, "Outbid { bid_of: new_bid, pending: prev_pending }", "fixed")
    sol03_text = fidelity.output_compare_text(sol03, "Payout { ok: transfer_ok, owed: 0 }", "fixed")
    ts09_text = fidelity.output_compare_text(ts09, "Parsed { ok: true, value: amount }", "fixed")

    assert "!(has_previous) || (reference.bid_of == candidate.bid_of)" in sol02_text
    assert sol03_text.count("(reference.owed == candidate.owed)") == 2
    assert "(reference.value - candidate.value) <= 1" in ts09_text


def test_output_equivalence_reports_applied_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fidelity, "verify_text", lambda *_args: {
        "outcome": "proven", "status": "success", "diagnostics": []})
    evidence = fidelity.output_equivalence(case_by_id("SOL02-D11"), "Outbid { bid_of: new_bid, pending: prev_pending }",
                                           "unused", 5, "fixed")
    assert evidence["comparison_policy"]["field_relevance"] == {"bid_of": "has_previous"}
    assert "no previous bidder" in evidence["comparison_policy"]["rationale"]


def test_output_policy_rejects_unknown_adjudication_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    (tmp_path / "proofs").mkdir()
    (tmp_path / "proofs/output-equivalence-policy.json").write_text(json.dumps({
        "schema": "mumei-demo.output-equivalence-policy/v1",
        "cases": {"SOL03-D08": {"unsupported_key": True}}}))
    monkeypatch.setattr(fidelity, "REPO_ROOT", tmp_path)

    with pytest.raises(ValueError, match="unsupported output-equivalence policy keys"):
        fidelity.output_policy(case_by_id("SOL03-D08"))


def test_boundary_only_output_prevents_lint_only_guard_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fidelity, "replay_inputs", lambda case: (_ for _ in ()).throw(OSError("no fixture")))
    monkeypatch.setattr(fidelity, "lint_findings", lambda *_args: [
        {"kind": "guard_folding", "message": "syntactic warning"}])
    monkeypatch.setattr(fidelity, "output_equivalence", lambda *_args, **_kwargs: {
        "outcome": "inconclusive", "reason": "abstraction_boundary_only",
        "method": "solver_output_compare", "status": "success"})
    case = case_by_id("PY01-D10")

    gated = cb.apply_port_fidelity_gate(case, "Parsed { ok: value > 0, value: value }",
                                        {"outcome": "proven", "status": "success", "diagnostics": []},
                                        "unused", 5, "fixed")

    assert gated["fidelity_gate"]["decision"] == "accepted"
