# mumei-demo Roadmap

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
