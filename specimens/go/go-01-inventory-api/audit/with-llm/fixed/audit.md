## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/go/go-01-inventory-api`
- verification_status: `refuted`
- Summary: Audit directory: specimens/go/go-01-inventory-api\n  calc.go: 2 violations, 1 gap\n  handlers.go: 0 violations, 12 gaps\n  main.go: 0 violations, 3 gaps\n  store.go: 0 violations, 1 gap\nSummary: 4 files, 4 files with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 1069-1170\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: vague_adjective at Position 2436-2447, conditional at Position 2840-2890, conditional at Position 3629-3641, conditional at Position 4666-4707\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 286-306, conditional at Position 447-531, conditional at Position 1337-1434, conditional at Position 2064-2096\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 2538-2557\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:重要]** validate-spec-to-code で制約の対応を確認
   ```bash
   mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 1069-1170
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:重要]** 欠落要件を追記してから再監査（推測で補完しない）
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
5. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: vague_adjective at Position 2436-2447, conditional at Position 2840-2890, conditional at Position 3629-3641, conditional at Position 4666-4707
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
6. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 286-306, conditional at Position 447-531, conditional at Position 1337-1434, conditional at Position 2064-2096
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
7. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 2538-2557
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["calc.go: spec stronger than implementation: reorderPoint", "handlers.go: spec ambiguity (missing_requirement): decodeMovement.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering decodeMovement; none was stated.", "handlers.go: spec ambiguity (missing_requirement): decodeMovement.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering decodeMovement; none was stated."]
- `verification_violations`: ["calc.go: Go function `reorderPoint` can divide by `int32(len(locations))` without a non-zero contract (Z3 counterexample: int32(len(locations))=0)", "calc.go: Z3 Counter-example: int32(len(locations))=0"]

### 検出事項
- `verification_violations`
  - calc.go: Go function `reorderPoint` can divide by `int32(len(locations))` without a non-zero contract (Z3 counterexample: int32(len(locations))=0)
  - calc.go: Z3 Counter-example: int32(len(locations))=0
- `cross_validation_gaps`
  - calc.go: spec stronger than implementation: reorderPoint
  - handlers.go: spec ambiguity (missing_requirement): decodeMovement.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering decodeMovement; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): decodeMovement.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering decodeMovement; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): writeMovement.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering writeMovement; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): writeMovement.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering writeMovement; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): restockHandler.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering restockHandler; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): restockHandler.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering restockHandler; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): reportHandler.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering reportHandler; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): reportHandler.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering reportHandler; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): searchHandler.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering searchHandler; none was stated.
