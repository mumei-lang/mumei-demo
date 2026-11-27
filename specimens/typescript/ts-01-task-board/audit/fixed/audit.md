## No-.mm ディレクトリ監査レポート

- ステータス: **合格**
- 言語: `mixed`
- Source: `specimens/typescript/ts-01-task-board`
- verification_status: `verified`
- finding_counts: `code=0, confirmed=0, spec=0, model_limitations=0, errors=0`
- files_with_spec_diagnostics: `0`
- Summary: Audit directory: specimens/typescript/ts-01-task-board\n  board.ts: 0 violations, 0 gaps\n  server.ts: 0 violations, 0 gaps\nSummary: 2 files, 0 files with issues, 0 files with spec diagnostics\nfinding_counts: code=0, confirmed=0, spec=0, model_limitations=0, errors=0\ntriage: refuted=0, verified=2, unverifiable=0\nnext_steps:\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: isStatus.requires, isStatus.ensures, canMove.requires, canMove.ensures, parsePriority.requires, parsePriority.ensures, newTask.requires, newTask.ensures, applyPatch.requires, applyPatch.ensures, moveTask.requires, moveTask.ensures, columnOrder.requires, columnOrder.ensures, completionPercent.requires, completionPercent.ensures, summarizeBoard.requires, summarizeBoard.ensures, searchTasks.requires, searchTasks.ensures, paginate.requires, paginate.ensures, escapeHtml.requires, escapeHtml.ensures, renderResults.requires, renderResults.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: readBody.requires, readBody.ensures, readJson.requires, readJson.ensures, sendJson.requires, sendJson.ensures, sendError.requires, sendError.ensures, currentUser.requires, currentUser.ensures, withNext.requires, withNext.ensures, handleCreate.requires, handleCreate.ensures, handlePatch.requires, handlePatch.ensures, handleMove.requires, handleMove.ensures, handleSearch.requires, handleSearch.ensures, route.requires, route.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: isStatus.requires, isStatus.ensures, canMove.requires, canMove.ensures, parsePriority.requires, parsePriority.ensures, newTask.requires, newTask.ensures, applyPatch.requires, applyPatch.ensures, moveTask.requires, moveTask.ensures, columnOrder.requires, columnOrder.ensures, completionPercent.requires, completionPercent.ensures, summarizeBoard.requires, summarizeBoard.ensures, searchTasks.requires, searchTasks.ensures, paginate.requires, paginate.ensures, escapeHtml.requires, escapeHtml.ensures, renderResults.requires, renderResults.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: readBody.requires, readBody.ensures, readJson.requires, readJson.ensures, sendJson.requires, sendJson.ensures, sendError.requires, sendError.ensures, currentUser.requires, currentUser.ensures, withNext.requires, withNext.ensures, handleCreate.requires, handleCreate.ensures, handlePatch.requires, handlePatch.ensures, handleMove.requires, handleMove.ensures, handleSearch.requires, handleSearch.ensures, route.requires, route.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- レビュー専用のギャップはありません。

### 検出事項
- 検出事項はありません。
