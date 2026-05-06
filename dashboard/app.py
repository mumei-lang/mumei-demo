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
    st.metric(
        "Proof Density",
        f"{density.get('percentage', 0):g}%",
        f"{density.get('verified', 0)}/{density.get('total', 0)} atoms",
    )

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


if __name__ == "__main__":
    main()
