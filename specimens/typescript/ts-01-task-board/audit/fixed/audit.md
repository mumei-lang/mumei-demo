## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/typescript/ts-01-task-board`
- verification_status: `verified`
- Summary: Audit directory: specimens/typescript/ts-01-task-board\n  board.ts: 0 violations, 0 gaps\n  server.ts: 3 violations, 0 gaps\nSummary: 2 files, 1 file with issues\nnext_steps:\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: isStatus.requires, isStatus.ensures, canMove.ensures, parsePriority.requires, parsePriority.ensures, newTask.requires, newTask.ensures, applyPatch.requires, applyPatch.ensures, moveTask.requires, moveTask.ensures, columnOrder.requires, columnOrder.ensures, completionPercent.requires, completionPercent.ensures, summarizeBoard.ensures, searchTasks.requires, searchTasks.ensures, paginate.requires, paginate.ensures, escapeHtml.requires, escapeHtml.ensures, renderResults.requires, renderResults.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: readBody.ensures, readJson.requires, readJson.ensures, sendJson.requires, sendJson.ensures, sendError.requires, sendError.ensures, currentUser.requires, currentUser.ensures, withNext.requires, withNext.ensures, handleCreate.requires, handleCreate.ensures, handlePatch.requires, handlePatch.ensures, handleMove.requires, handleMove.ensures, handleSearch.requires, handleSearch.ensures, route.requires, route.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: isStatus.requires, isStatus.ensures, canMove.ensures, parsePriority.requires, parsePriority.ensures, newTask.requires, newTask.ensures, applyPatch.requires, applyPatch.ensures, moveTask.requires, moveTask.ensures, columnOrder.requires, columnOrder.ensures, completionPercent.requires, completionPercent.ensures, summarizeBoard.ensures, searchTasks.requires, searchTasks.ensures, paginate.requires, paginate.ensures, escapeHtml.requires, escapeHtml.ensures, renderResults.requires, renderResults.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
2. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: readBody.ensures, readJson.requires, readJson.ensures, sendJson.requires, sendJson.ensures, sendError.requires, sendError.ensures, currentUser.requires, currentUser.ensures, withNext.requires, withNext.ensures, handleCreate.requires, handleCreate.ensures, handlePatch.requires, handlePatch.ensures, handleMove.requires, handleMove.ensures, handleSearch.requires, handleSearch.ensures, route.requires, route.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `verification_violations`: ["server.ts: TypeScript function `handlePatch` uses `task` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches", "server.ts: TypeScript function `handlePatch` indexes with the result of `.indexOf((…)` inline — a miss yields a sentinel (`-1`) used directly as an index", "server.ts: TypeScript function `handleMove` uses `owned` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches"]

### 検出事項
- `verification_violations`
  - server.ts: TypeScript function `handlePatch` uses `task` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches
  - server.ts: TypeScript function `handlePatch` indexes with the result of `.indexOf((…)` inline — a miss yields a sentinel (`-1`) used directly as an index
  - server.ts: TypeScript function `handleMove` uses `owned` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches
