from __future__ import annotations

import json
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "scenarios"
REPORTS = ROOT / "reports"
SCENARIO_ORDER = [
    "ownership_transfer",
    "rtgs_settlement",
    "regtech_compliance",
    "nl_to_verified",
    "smart_contract_audit",
    "blockchain_audit",
    "medical_device",
    "aviation_control",
]


def scenario_names() -> list[str]:
    names = sorted(
        path.name for path in SCENARIOS.iterdir()
        if path.is_dir() and path.name != "_template"
    )
    ordered = [name for name in SCENARIO_ORDER if name in names]
    return ordered + [name for name in names if name not in SCENARIO_ORDER]


def latest_result(scenario: str) -> Path | None:
    latest = REPORTS / scenario / "latest" / "result.json"
    if latest.exists():
        return latest
    candidates = sorted((REPORTS / scenario).glob("*/result.json"), reverse=True)
    return candidates[0] if candidates else None


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def layer_density_values(data: dict, layer: str) -> tuple[int, int, float]:
    counted_statuses = {"PASS", "REJECTED", "CERTIFIED", "FAIL"}
    verified_statuses = {"PASS", "REJECTED", "CERTIFIED"}
    steps = data.get("layers", {}).get(layer, {}).get("steps", [])
    counted = [step for step in steps if step.get("status") in counted_statuses]
    total = len(counted)
    verified = sum(1 for step in counted if step.get("status") in verified_statuses)
    percentage = round((verified / total) * 100, 1) if total else 0.0
    return verified, total, percentage


def compliance_label(data: dict) -> str:
    compliance = data.get("harness_contract_compliance", {})
    if not isinstance(compliance, dict):
        return "N/A"
    total = int(compliance.get("total", 0) or 0)
    status = str(compliance.get("status", "N/A"))
    if total == 0:
        return status
    return f"{status} ({int(compliance.get('passed', 0) or 0)}/{total})"


def intent_fidelity_label(data: dict) -> str:
    summary = data.get("intent_fidelity_summary", {})
    if not isinstance(summary, dict):
        return "N/A"
    status = str(summary.get("status", "N/A"))
    score = summary.get("score")
    criteria_total = int(summary.get("criteria_total", 0) or 0)
    criteria_passed = int(summary.get("criteria_passed", 0) or 0)
    parts = [status]
    if score is not None:
        try:
            parts.append(f"score {float(score):.2f}")
        except (TypeError, ValueError):
            parts.append(f"score {score}")
    if criteria_total:
        parts.append(f"{criteria_passed}/{criteria_total} criteria")
    return " · ".join(parts)


def artifact_payload_summary(payload: object) -> str:
    if not isinstance(payload, dict):
        return "captured"
    if "error" in payload:
        return f"error: {payload['error']}"
    if "certificate_hash" in payload:
        return f"proof certificate {payload['certificate_hash']}"
    if "all_verified" in payload:
        return f"proof certificate all_verified={payload['all_verified']}"
    if payload.get("scenario"):
        return f"harness state for {payload.get('scenario')}"
    if payload.get("type") == "text":
        return "text preview captured"
    if "atoms" in payload:
        atoms = payload.get("atoms")
        count = len(atoms) if isinstance(atoms, list) else "unknown"
        return f"structured spec with {count} atom(s)"
    return "captured"


def render_spec_code_mapping(data: dict) -> None:
    st.subheader("Specification-Code Mapping")
    spec_code_mapping = data.get("spec_code_mapping", [])
    if not spec_code_mapping:
        for artifact in data.get("artifacts", []):
            payload = data.get("artifact_payloads", {}).get(artifact)
            if isinstance(payload, dict) and payload.get("spec_code_mapping"):
                spec_code_mapping = payload["spec_code_mapping"]
                break

    if spec_code_mapping:
        for mapping in spec_code_mapping:
            if not isinstance(mapping, dict):
                continue
            status_icon = {
                "passed": "✅",
                "failed": "❌",
                "unknown": "⚠️",
            }.get(mapping.get("verification_status", "unknown"), "⚠️")
            confidence = float(mapping.get("confidence", 0) or 0)
            label = (
                f"{status_icon} {mapping.get('spec_description', 'Unnamed specification')} "
                f"(confidence: {confidence:.2f})"
            )

            with st.expander(label):
                st.write(f"**Spec Item ID:** {mapping.get('spec_item_id', 'N/A')}")
                if mapping.get("requires_clause"):
                    st.code(
                        f"requires: {mapping['requires_clause']}",
                        language="mumei",
                    )
                if mapping.get("ensures_clause"):
                    st.code(
                        f"ensures: {mapping['ensures_clause']}",
                        language="mumei",
                    )

                loc = mapping.get("code_location", {})
                if not isinstance(loc, dict):
                    loc = {}
                if loc.get("line", 0) > 0:
                    st.caption(
                        f"Code location: Line {loc.get('line')}, Column {loc.get('col', '?')}"
                    )
                st.write(
                    "**Verification Status:** "
                    f"{mapping.get('verification_status', 'unknown')}"
                )
    else:
        st.info("No specification-code mapping available.")


def render_harness_contract(data: dict) -> None:
    contract = data.get("harness_contract")
    if not isinstance(contract, dict):
        return

    st.subheader("Harness Contract")
    compliance = data.get("harness_contract_compliance", {})
    status = compliance.get("status", "N/A") if isinstance(compliance, dict) else "N/A"
    st.metric("Harness Contract Compliance", compliance_label(data))
    st.markdown(f"**Policy:** `{contract.get('policy', 'unspecified')}`")
    st.markdown(f"**Acceptance path:** `{', '.join(str(item) for item in contract.get('acceptance_path', []))}`")
    st.markdown(f"**State directory:** `{contract.get('state_dir', 'unspecified')}`")
    st.markdown(f"**State file:** `{contract.get('state_file', data.get('harness_state_file', 'unspecified'))}`")
    st.markdown(f"**Intent:** {contract.get('intent', '_Not specified_')}")

    if status != "COMPLIANT":
        st.warning("Harness contract metadata needs attention.")
    if isinstance(compliance, dict) and isinstance(compliance.get("checks"), list):
        st.table([
            {
                "check": check.get("name", ""),
                "result": "PASS" if check.get("passed") else "ATTENTION",
            }
            for check in compliance["checks"]
            if isinstance(check, dict)
        ])

    artifact_contracts = contract.get("artifact_contracts", [])
    if isinstance(artifact_contracts, list) and artifact_contracts:
        with st.expander("Artifact Contracts", expanded=True):
            for item in artifact_contracts:
                st.markdown(f"- {item}")

    intent_fidelity = data.get("intent_fidelity")
    if isinstance(intent_fidelity, dict):
        with st.expander("Intent Fidelity", expanded=True):
            st.metric("Intent Fidelity", intent_fidelity_label(data))
            st.markdown(f"**Source intent:** {intent_fidelity.get('source_intent', 'N/A')}")
            criteria = intent_fidelity.get("success_criteria", [])
            if isinstance(criteria, list) and criteria:
                st.markdown("**Success criteria:**")
                for item in criteria:
                    st.markdown(f"- {item}")
            if intent_fidelity.get("drift_risk"):
                st.markdown(f"**Drift risk:** {intent_fidelity['drift_risk']}")

    rows = []
    for layer, payload in data.get("layers", {}).items():
        for step in payload.get("steps", []):
            if not any(key in step for key in ("harness_stage", "artifact_contract", "verifier_gate")):
                continue
            rows.append({
                "layer": layer,
                "stage": step.get("harness_stage", ""),
                "artifact_contract": step.get("artifact_contract", step.get("artifacts", [])),
                "verifier_gate": step.get("verifier_gate", ""),
                "failure_taxonomy": step.get("failure_taxonomy", ""),
            })
    if rows:
        st.markdown("#### Stage Gates")
        st.table(rows)

    evidence = data.get("verification_evidence", [])
    if isinstance(evidence, list) and evidence:
        st.markdown("#### Verification Evidence")
        st.table(evidence)

    payloads = data.get("artifact_payloads", {})
    if isinstance(payloads, dict) and payloads:
        st.markdown("#### Artifact Contract Visualization")
        artifact_rows = [
            {
                "artifact": artifact,
                "contract_evidence": artifact_payload_summary(payloads.get(artifact)),
            }
            for artifact in data.get("artifacts", [])
            if artifact in payloads
        ]
        if artifact_rows:
            st.table(artifact_rows)
        for artifact in data.get("artifacts", []):
            payload = payloads.get(artifact)
            if payload is None:
                continue
            with st.expander(f"Artifact: {artifact}"):
                if isinstance(payload, dict) and payload.get("type") == "text":
                    st.code(payload.get("preview", ""), language="text")
                else:
                    st.json(payload)


def main() -> None:
    st.set_page_config(page_title="Mumei Demo Dashboard", layout="wide")
    st.title("Mumei Secure Verification Demo")

    names = scenario_names()
    if not names:
        st.warning("No scenarios found.")
        return

    scenario = st.sidebar.selectbox("Scenario", names)
    result_path = latest_result(scenario)
    if result_path is None:
        st.info("Run the scenario first to generate a report.")
        return

    data = load_json(result_path)
    st.caption(f"Report: `{result_path}`")
    layers = data.get("layers", {})
    has_lean = "l3_lean" in layers
    verification_type = "Z3 + Lean 4" if has_lean else "Z3 Only"
    st.caption(f"Verification: **{verification_type}**")

    cols = st.columns(len(layers) or 1)
    for col, (layer, payload) in zip(cols, layers.items()):
        col.metric(layer, payload.get("status", "UNKNOWN"))

    density = data.get("proof_density", {})
    metric_cols = st.columns(4 if has_lean else 3)
    metric_cols[0].metric(
        "Proof Density",
        f"{density.get('percentage', 0):g}%",
        f"{density.get('verified', 0)}/{density.get('total', 0)} atoms",
    )
    metric_cols[1].metric("Harness Contract", compliance_label(data))
    metric_cols[2].metric("Intent Fidelity", intent_fidelity_label(data))
    if has_lean:
        lean_verified, lean_total, lean_percentage = layer_density_values(data, "l3_lean")
        metric_cols[3].metric(
            "Lean Proof Coverage",
            f"{lean_percentage:g}%" if lean_total else "N/A",
            f"{lean_verified}/{lean_total} Lean steps",
        )

    render_spec_code_mapping(data)
    render_harness_contract(data)

    st.subheader("Step Details")
    report_dir = result_path.parent
    for layer, payload in data.get("layers", {}).items():
        st.markdown(f"### {layer}")
        for step in payload.get("steps", []):
            label = f"{step.get('display_status', step.get('status'))}: {step.get('name')}"
            with st.expander(label):
                st.json({k: v for k, v in step.items() if k not in {"stdout", "stderr"}})
                log_path = report_dir / step.get("output_file", "")
                if log_path.exists():
                    st.code(log_path.read_text(encoding="utf-8"), language="text")
                elif step.get("stdout") or step.get("stderr"):
                    st.code(f"{step.get('stdout', '')}\n{step.get('stderr', '')}", language="text")

    st.subheader("Proof Certificates")
    for artifact in data.get("artifacts", []):
        if artifact.endswith((".proof.json", ".lean-cert.json")):
            path = report_dir / artifact
            if path.exists():
                with st.expander(artifact):
                    st.json(load_json(path))

    st.subheader("Cross-scenario Proof Density")
    chart_rows = []
    for name in names:
        path = latest_result(name)
        if not path:
            continue
        item = load_json(path)
        chart_rows.append({
            "scenario": name,
            "density": item.get("proof_density", {}).get("percentage", 0),
        })
    if chart_rows:
        st.bar_chart(chart_rows, x="scenario", y="density")

    lean_chart_rows = []
    for name in names:
        path = latest_result(name)
        if not path:
            continue
        item = load_json(path)
        if "l3_lean" not in item.get("layers", {}):
            continue
        lean_verified, lean_total, lean_percentage = layer_density_values(item, "l3_lean")
        if lean_total == 0:
            continue
        lean_chart_rows.append({
            "scenario": name,
            "density": lean_percentage,
            "verified": lean_verified,
            "total": lean_total,
        })
    if lean_chart_rows:
        st.subheader("Cross-scenario Lean Proof Coverage")
        st.bar_chart(lean_chart_rows, x="scenario", y="density")


if __name__ == "__main__":
    main()
