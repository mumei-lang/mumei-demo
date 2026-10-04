## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/go/go-01-inventory-api`
- verification_status: `refuted`
- Summary: Audit directory: specimens/go/go-01-inventory-api\n  calc.go: 2 violations, 0 gaps\n  handlers.go: 0 violations, 0 gaps\n  main.go: 0 violations, 0 gaps\n  store.go: 0 violations, 0 gaps\nSummary: 4 files, 1 file with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: reorderPoint.ensures, appendMovement.requires, appendMovement.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: itemHandler.requires, itemHandler.ensures, createItem.requires, createItem.ensures, viewItem.ensures, reserveHandler.requires, reserveHandler.ensures, releaseHandler.requires, releaseHandler.ensures, restockHandler.requires, restockHandler.ensures, reportHandler.requires, reportHandler.ensures, searchHandler.requires, searchHandler.ensures, resetHandler.requires, resetHandler.ensures, writeJSON.requires, writeJSON.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: main.requires, main.ensures, auditRequests.requires, auditRequests.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: NewStore.requires, NewStore.ensures, Put.requires, Put.ensures, Get.ensures, All.requires, All.ensures, Reset.requires, Reset.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: reorderPoint.ensures, appendMovement.requires, appendMovement.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: itemHandler.requires, itemHandler.ensures, createItem.requires, createItem.ensures, viewItem.ensures, reserveHandler.requires, reserveHandler.ensures, releaseHandler.requires, releaseHandler.ensures, restockHandler.requires, restockHandler.ensures, reportHandler.requires, reportHandler.ensures, searchHandler.requires, searchHandler.ensures, resetHandler.requires, resetHandler.ensures, writeJSON.requires, writeJSON.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: main.requires, main.ensures, auditRequests.requires, auditRequests.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
5. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: NewStore.requires, NewStore.ensures, Put.requires, Put.ensures, Get.ensures, All.requires, All.ensures, Reset.requires, Reset.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `verification_violations`: ["calc.go: Go function `reorderPoint` can divide by `int32(len(locations))` without a non-zero contract (Z3 counterexample: int32(len(locations))=0)", "calc.go: Z3 Counter-example: int32(len(locations))=0"]

### 検出事項
- `verification_violations`
  - calc.go: Go function `reorderPoint` can divide by `int32(len(locations))` without a non-zero contract (Z3 counterexample: int32(len(locations))=0)
  - calc.go: Z3 Counter-example: int32(len(locations))=0
