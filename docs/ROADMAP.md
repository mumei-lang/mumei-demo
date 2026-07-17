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

## P9-G: Ecosystem Integration — ✅ Implemented

`mumei-lang/mumei-demo` は P9-G NLAE pipeline の Evaluation Loop を担当する。

### Implemented scope

- ✅ `demos/nlae_integration/README.md` — 4 repo demo の実行手順
- ✅ `demos/nlae_integration/run_demo.sh` — `mumei` fixture、`mumei-agent` pipeline、`mumei-lean` fidelity checker を接続する harness
- ✅ `demos/nlae_integration/expected_output.json` — CI regression 用の期待出力

### P9 completion

P9-D/E/F/G の完了により、NLAE integration milestone は実装済み。
