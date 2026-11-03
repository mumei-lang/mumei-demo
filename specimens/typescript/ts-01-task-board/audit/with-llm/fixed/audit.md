## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/typescript/ts-01-task-board`
- verification_status: `unverifiable`
- Summary: Audit directory: specimens/typescript/ts-01-task-board\n  board.ts: 0 violations, 4 gaps\n  server.ts: 3 violations, 17 gaps\nSummary: 2 files, 2 files with issues\nnext_steps:\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: newTask.requires, applyPatch.requires, vague_adjective at Position 536-547, conditional at Position 1803-1835, conditional at Position 2744-2780\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: validate-spec で仕様の矛盾を修正\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: route.requires, route.ensures, conditional at Position 473-513, conditional at Position 674-747, conditional at Position 2412-2474, conditional at Position 3380-3403\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** validate-spec-to-code で制約の対応を確認
   ```bash
   mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human
   ```
2. **[V1-E-1:重要]** 欠落要件を追記してから再監査（推測で補完しない）
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: newTask.requires, applyPatch.requires, vague_adjective at Position 536-547, conditional at Position 1803-1835, conditional at Position 2744-2780
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
5. **[V1-E-1:通常]** validate-spec で仕様の矛盾を修正
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
6. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: route.requires, route.ensures, conditional at Position 473-513, conditional at Position 674-747, conditional at Position 2412-2474, conditional at Position 3380-3403
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["board.ts: spec ambiguity (missing_requirement): isStatus.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering isStatus; none was stated.", "board.ts: spec ambiguity (missing_requirement): canMove.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering canMove; none was stated.", "board.ts: spec ambiguity (missing_requirement): parsePriority.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering parsePriority; none was stated."]
- `verification_violations`: ["server.ts: TypeScript function `handlePatch` uses `task` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches", "server.ts: TypeScript function `handlePatch` indexes with the result of `.indexOf((…)` inline — a miss yields a sentinel (`-1`) used directly as an index", "server.ts: TypeScript function `handleMove` uses `owned` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches"]

### 検出事項
- `verification_violations`
  - server.ts: TypeScript function `handlePatch` uses `task` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches
  - server.ts: TypeScript function `handlePatch` indexes with the result of `.indexOf((…)` inline — a miss yields a sentinel (`-1`) used directly as an index
  - server.ts: TypeScript function `handleMove` uses `owned` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches
- `cross_validation_gaps`
  - board.ts: spec ambiguity (missing_requirement): isStatus.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering isStatus; none was stated.
  - board.ts: spec ambiguity (missing_requirement): canMove.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering canMove; none was stated.
  - board.ts: spec ambiguity (missing_requirement): parsePriority.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering parsePriority; none was stated.
  - board.ts: spec ambiguity (missing_requirement): escapeHtml.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering escapeHtml; none was stated.
  - server.ts: spec ambiguity (missing_requirement): readBody.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering readBody; none was stated.
  - server.ts: spec ambiguity (missing_requirement): readJson.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering readJson; none was stated.
  - server.ts: spec ambiguity (missing_requirement): readJson.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering readJson; none was stated.
  - server.ts: spec ambiguity (missing_requirement): sendJson.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering sendJson; none was stated.
  - server.ts: spec ambiguity (missing_requirement): sendJson.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering sendJson; none was stated.
  - server.ts: spec ambiguity (missing_requirement): sendError.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering sendError; none was stated.
- `spec_health_issues`
  - server.ts: encoding-gap: handleSearch: spec_not_boolean: ensures clause 'result.is_html' must lower to boolean (constraints: ["result.is_html"])
