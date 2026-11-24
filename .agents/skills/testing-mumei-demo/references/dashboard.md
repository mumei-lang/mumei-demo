# Dashboard recording flow (Streamlit)

Read this when testing `dashboard/app.py` in the browser or recording dashboard evidence.

## Dashboard recording flow

After generating a successful latest report, start the dashboard:

```bash
streamlit run dashboard/app.py
```

Open the local Streamlit page in the browser and verify:

- Sidebar scenario can be changed between `ownership_transfer`, `rtgs_settlement`, `regtech_compliance`, `nl_to_verified`, `smart_contract_audit`, `medical_device`, and `aviation_control`.
- Natural-language dashboard evidence should show `l2_agent=PASS`, `l1_z3=PASS`, and Proof Density `100%` with `3/3 atoms`.
- RegTech dashboard evidence should show `l1_z3=PASS`, `l2_agent=PASS`, no `l3_lean` metric, and Proof Density `100%` with `5/5 atoms or layer steps verified`.
- RTGS/ownership dashboard evidence should show expected L1/L2/L3 metrics; proof density is usually `100%` and `6/6 atoms` for RTGS in a Lake-available environment.
- Expanding the RegTech rejected steps shows log text containing `Match is not exhaustive` and `CustomerType::PEP (tag=3)`.
- Expanding the ownership rejected step shows log text containing `InvalidPreState`.
- Expanding proof certificate artifacts shows generated JSON. RegTech should show `compliance.proof.json`; RTGS should show both `settlement.proof.json` and `settlement.lean-cert.json`.

If recording dashboard evidence, maximize the browser first where possible and annotate scenario selection, layer metrics, proof density, expanded step logs, and verification/proof evidence. Save and attach the processed mp4 in the final testing report.
