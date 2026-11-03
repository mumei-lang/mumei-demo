## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/go/go-01-inventory-api`
- verification_status: `refuted`
- Summary: Audit directory: specimens/go/go-01-inventory-api\n  calc.go: 2 violations, 0 gaps\n  handlers.go: 0 violations, 0 gaps\n  main.go: 0 violations, 4 gaps\n  store.go: 0 violations, 0 gaps\nSummary: 4 files, 3 files with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 1356-1424\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: validate-spec で仕様の矛盾を修正\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: vague_adjective at Position 3950-3960, conditional at Position 5179-5211, conditional at Position 6564-6623\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 1035-1149, conditional at Position 1520-1556\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: NewStore.requires, Put.requires, Put.ensures, Get.ensures, All.requires, All.ensures, Reset.requires, Reset.ensures, conditional at Position 1788-1814\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 1356-1424
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** validate-spec で仕様の矛盾を修正
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: vague_adjective at Position 3950-3960, conditional at Position 5179-5211, conditional at Position 6564-6623
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
5. **[V1-E-1:重要]** validate-spec-to-code で制約の対応を確認
   ```bash
   mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human
   ```
6. **[V1-E-1:重要]** 欠落要件を追記してから再監査（推測で補完しない）
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
7. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 1035-1149, conditional at Position 1520-1556
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
8. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: NewStore.requires, Put.requires, Put.ensures, Get.ensures, All.requires, All.ensures, Reset.requires, Reset.ensures, conditional at Position 1788-1814
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["main.go: spec ambiguity (missing_requirement): main.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering main; none was stated.", "main.go: spec ambiguity (missing_requirement): main.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering main; none was stated.", "main.go: spec ambiguity (missing_requirement): auditRequests.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering auditRequests; none was stated."]
- `verification_violations`: ["calc.go: Go function `reorderPoint` can divide by `int32(len(locations))` without a non-zero contract (Z3 counterexample: int32(len(locations))=0)", "calc.go: Z3 Counter-example: int32(len(locations))=0"]

### 検出事項
- `verification_violations`
  - calc.go: Go function `reorderPoint` can divide by `int32(len(locations))` without a non-zero contract (Z3 counterexample: int32(len(locations))=0)
  - calc.go: Z3 Counter-example: int32(len(locations))=0
- `cross_validation_gaps`
  - main.go: spec ambiguity (missing_requirement): main.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering main; none was stated.
  - main.go: spec ambiguity (missing_requirement): main.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering main; none was stated.
  - main.go: spec ambiguity (missing_requirement): auditRequests.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering auditRequests; none was stated.
  - main.go: spec ambiguity (missing_requirement): auditRequests.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering auditRequests; none was stated.
- `spec_health_issues`
  - handlers.go: malformed-extraction: itemHandler ensures: garbled comparison operators '==>'
  - handlers.go: malformed-extraction: reserveHandler ensures: garbled comparison operators '==>'
  - handlers.go: malformed-extraction: reserveHandler ensures: garbled comparison operators '==>'
  - handlers.go: malformed-extraction: reserveHandler ensures: garbled comparison operators '==>'
  - handlers.go: malformed-extraction: reserveHandler ensures: garbled comparison operators '==>'
  - handlers.go: malformed-extraction: reserveHandler ensures: garbled comparison operators '==>'
  - handlers.go: malformed-extraction: releaseHandler ensures: garbled comparison operators '==>'
  - handlers.go: malformed-extraction: releaseHandler ensures: garbled comparison operators '==>'
  - handlers.go: malformed-extraction: releaseHandler ensures: garbled comparison operators '==>'
  - handlers.go: malformed-extraction: releaseHandler ensures: garbled comparison operators '==>'
