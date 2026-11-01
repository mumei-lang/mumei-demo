# mumei-demo Roadmap

## Scenario evidence: requirements-to-CI example

The Charter scenario opts into `mumei-demo.scenario-evidence/v1`. Readers
revalidate the required claims and artifacts, independently display proof grades
and dependency completeness, and separate model evidence, finite observations,
declared assumptions, unverified connections, and exclusions. Existing scenarios
without the evidence configuration keep their existing contract.

`make demo-charter-regression` connects the existing Charter, negative-control,
and test-observation scenarios without pretending they prove a single model.
The real binary checks G4, complete dependencies, and stale-certificate rejection;
eleven explicitly synthetic reader cases cover missing/replaced evidence,
staleness, missing dependencies, required artifact omissions, and failure preservation.
CI saves diagnostics, current reviewed inputs, and the baseline Git diff.
The [runbook](../scenarios/charter_gate_demo/README.md) is the executable reference.

Cross-repo responsibilities remain unchanged: `mumei` owns verification, grades,
Claim Book and Charter gates; `mumei-agent` owns test harvesting and repair tools;
`mumei-lean` remains an optional proof backend; `mumei-demo` binds and presents
scenario evidence. No compiler DSL, alternate grade, audit-key alias, mandatory
LLM step, or new Lean guarantee is introduced. Production/runtime correspondence
remains outside that Charter example.

## Limited single-record execution experiment

The independent [fixed execution adapter](RECORD_EXECUTION.md) now accepts only
data proposals for single-record reads/value updates. Current authority and
version checks run in the same single-process lock as publication. Typed,
copied initial state, strict JSON parsing, serialized policy configuration,
minimal audit events and fail-closed fault/concurrency regressions are included.
`make test-record-execution` runs this separately; no existing scenario is
changed or promoted to a new proof grade.

The optional [record-operation scenario](../scenarios/record_execution_demo/README.md)
now joins that adapter with a local `.mm` version contract, fresh independent
Lean model/kernel audit, finite implementation checks and four detected
broken-host variants. Existing evidence readers show independent model proofs
separately, without a new grade or Python promotion. The default 18-scenario
sequence stays unchanged; the optional target requires the pinned Lean toolchain
and is exercised separately in source-built CI. Formal model/Python
correspondence, production authentication/storage, distributed operations and
arbitrary-code confinement remain unproved and outside this experiment.

## Cross-project no-.mm scenario contract

`mumei-lang/mumei/docs/CROSS_PROJECT_ROADMAP.md` owns the global V1 order. Demo scenarios that cover the no-`.mm` path must keep the same `audit -> migrate-suggest -> heal` gate order as `mumei-agent audit --auto-migrate --auto-heal` and MCP `scan_and_fix`.

For `scenarios/no_mm_audit`, the user-facing copy stays in this order: 既存コードを渡すだけでバグ箇所を指摘 / 仕様から既存コードとの差分を指摘 / 仕様単独でおかしい場合を指摘, then `next_steps`, `artifact_keys`, and `harness_contract`. `next_steps` is the only human-review entrypoint before `migration_hints`, `healed_files`, or `heal_errors` evidence is accepted.

## Contract vocabulary regression — docs/README coverage

`scripts/check_scenario_contracts.py` validates both scenario JSON files and docs/README files against the canonical forbidden-alias list. The docs check targets key-like contexts (backtick-quoted, code-fenced, or JSON-key style) to avoid false positives on regular English prose while catching contract-key drift.

Covered docs: `docs/HARNESS_CONTRACTS.md`, `docs/ROADMAP.md`, `docs/SCENARIO_SPEC.md`, `scenarios/no_mm_audit/README.md`, `scenarios/spec_code_verification_suite/README.md`.

Run the local scenario/docs contract gate before opening a PR that touches those scenario JSON files or docs:

```bash
python3 scripts/check_scenario_contracts.py
python3 -m pytest tests/test_check_scenario_contracts.py -q
```

CI enforces the same gate through `.github/workflows/contract-vocabulary.yml` on pull requests into `main`. This is the mumei-demo complement to the canonical `mumei/scripts/check_contract_vocabulary.py` gate.

## 2026-10: Claim Book, charter, controls, and test-observation scenarios (#78–#81)

- **#78 — Claim Book reporting:** certificate-writing steps may opt into Claim Book reporting. Per-step claim counts, grades, freshness, and incomplete dependency coverage appear in reports and summaries; this evidence is informational and never changes step or scenario status. This extends existing scenarios rather than adding a separate Claim Book scenario.
- **#79 — Charter Gate (`make demo-charter`):** locks a reviewed dosage Charter and records expected rejection of weakened or narrowed contracts, a trusted shortcut below the required grade, and edited Charter text. Scenario commands run on an output-directory copy.
- CI dogfood: run `mumei-lang/mumei/.github/workflows/mumei-gate.yml@develop` on `charter_gate_demo`'s `correct.mm` at G4 with Charter enabled.
- **#80 — Negative Controls (`make demo-negative-controls`):** holds the dosage implementation constant while contrasting weak and strong contracts. The report records controls, vacuity, and Claim Book gate evidence; a surviving mutant still requires human review.
- **#81 — Test Observations (`make demo-test-observation`):** harvests Python and Rust tests, then compares the observations with a deliberately wrong and an aligned contract using `mumei observe`. Missing or malformed reports fail closed; the fixture-mode scenario does not require an LLM.
- Current specimen scoreboard, copied verbatim from the README:

  `Latest — no LLM: 10/171 detected (6%), 29/171 detected or function-flagged · with LLM: not run yet`

Regression gate: `python3 scripts/check_scenario_contracts.py` and
`python3 -m pytest tests/test_check_scenario_contracts.py -q`.

## Priority 16: 大規模ケースでの atom-local proof obligation 合成性検証 — ✅ Implemented

canonical 上位ロードマップは `mumei-lang/mumei/docs/CROSS_PROJECT_ROADMAP.md` の
"Priority 16"、compiler 側 local checkpoint は `mumei/docs/ROADMAP.md` の P20。
本節は demo harness 側の checkpoint。

- ✅ `scenarios/{medical_device,rtgs_settlement,regtech_compliance,defi_invariant,ownership_transfer}_scale/`
  を追加（172 atoms / 依存深さ 5–7 / 各 8 状態の effect 状態機械）。既存シナリオの
  一桁増しで、いずれも Z3 で全 atom 検証済み。
- ✅ 既存の決定的 fixture モードは不変: scale ケースは `SCENARIOS` に入れず
  `SCALE_SCENARIOS` の**別 target**（`make demo-scale` ほか）として実行する。
  `make demo` / `make demo-all` / `make demo-ci` の対象は変わらない。
- ✅ 各 scale シナリオは `verify_scale`（`--proof-cert`）→ `verify_cert_strict`
  （`mumei verify-cert --strict`）→ `trust_surface` → `composability` →
  `agent_scale_report` の順で証拠を積み上げる。
- ✅ 合成の破れは既存の `verification_status` / `verification_violations` /
  `next_steps` でのみ報告する（`mumei-agent scale-report`）。新しい verdict 分類や
  別名 alias は追加しない。
- ✅ 測定値は各シナリオ README の "Measured" 表に記録（closure ratio、composition
  break のパターン別内訳、trust surface、Z3 solver 時間、`budget_policy_fingerprint`）。

## P9-G: Ecosystem Integration — ✅ Implemented

`mumei-lang/mumei-demo` は P9-G NLAE pipeline の Evaluation Loop を担当する。

### Implemented scope

- ✅ `demos/nlae_integration/README.md` — 4 repo demo の実行手順
- ✅ `demos/nlae_integration/run_demo.sh` — `mumei` fixture、`mumei-agent` pipeline、`mumei-lean` fidelity checker を接続する harness
- ✅ `demos/nlae_integration/expected_output.json` — CI regression 用の期待出力

### P9 completion

P9-D/E/F/G の完了により、NLAE integration milestone は実装済み。
