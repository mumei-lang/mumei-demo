## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/typescript/ts-01-task-board`
- verification_status: `verified`
- finding_counts: `code=1, confirmed=0, spec=0, model_limitations=0, errors=0`
- files_with_spec_diagnostics: `0`
- Summary: Audit directory: specimens/typescript/ts-01-task-board\n  board.ts: 1 violation, 0 gaps\n  server.ts: 0 violations, 0 gaps\nSummary: 2 files, 1 file with issues, 0 files with spec diagnostics\nfinding_counts: code=1, confirmed=0, spec=0, model_limitations=0, errors=0\ntriage: refuted=0, verified=2, unverifiable=0\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: isStatus.requires, isStatus.ensures, canMove.requires, canMove.ensures, parsePriority.requires, parsePriority.ensures, newTask.requires, newTask.ensures, applyPatch.requires, applyPatch.ensures, moveTask.requires, moveTask.ensures, columnOrder.requires, columnOrder.ensures, completionPercent.requires, completionPercent.ensures, summarizeBoard.requires, summarizeBoard.ensures, searchTasks.requires, searchTasks.ensures, paginate.requires, paginate.ensures, renderResults.requires, renderResults.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: readBody.requires, readBody.ensures, readJson.requires, readJson.ensures, sendJson.requires, sendJson.ensures, sendError.requires, sendError.ensures, currentUser.requires, currentUser.ensures, withNext.requires, withNext.ensures, handleCreate.requires, handleCreate.ensures, handlePatch.requires, handlePatch.ensures, handleMove.requires, handleMove.ensures, handleSearch.requires, handleSearch.ensures, route.requires, route.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: isStatus.requires, isStatus.ensures, canMove.requires, canMove.ensures, parsePriority.requires, parsePriority.ensures, newTask.requires, newTask.ensures, applyPatch.requires, applyPatch.ensures, moveTask.requires, moveTask.ensures, columnOrder.requires, columnOrder.ensures, completionPercent.requires, completionPercent.ensures, summarizeBoard.requires, summarizeBoard.ensures, searchTasks.requires, searchTasks.ensures, paginate.requires, paginate.ensures, renderResults.requires, renderResults.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: readBody.requires, readBody.ensures, readJson.requires, readJson.ensures, sendJson.requires, sendJson.ensures, sendError.requires, sendError.ensures, currentUser.requires, currentUser.ensures, withNext.requires, withNext.ensures, handleCreate.requires, handleCreate.ensures, handlePatch.requires, handlePatch.ensures, handleMove.requires, handleMove.ensures, handleSearch.requires, handleSearch.ensures, route.requires, route.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `verification_violations`: ["board.ts: TypeScript function `moveTask` uses `task` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches"]

### 検出事項
- `verification_violations`
  - board.ts: TypeScript function `moveTask` uses `task` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches
