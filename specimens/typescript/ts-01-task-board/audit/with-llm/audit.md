## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/typescript/ts-01-task-board`
- verification_status: `unverifiable`
- Summary: Audit directory: specimens/typescript/ts-01-task-board\n  board.ts: 1 violation, 0 gaps\n  server.ts: 2 violations, 20 gaps\nSummary: 2 files, 2 files with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: validate-spec で仕様の矛盾を修正\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: isStatus.requires, conditional at Position 474-509, conditional at Position 3338-3365, conditional at Position 3886-3977, conditional at Position 5146-5160\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: route.requires, route.ensures, conditional at Position 1431-1489\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** validate-spec で仕様の矛盾を修正
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: isStatus.requires, conditional at Position 474-509, conditional at Position 3338-3365, conditional at Position 3886-3977, conditional at Position 5146-5160
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:重要]** validate-spec-to-code で制約の対応を確認
   ```bash
   mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human
   ```
5. **[V1-E-1:重要]** 欠落要件を追記してから再監査（推測で補完しない）
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
6. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: route.requires, route.ensures, conditional at Position 1431-1489
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["server.ts: spec ambiguity (missing_requirement): readBody.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering readBody; none was stated.", "server.ts: spec ambiguity (missing_requirement): readBody.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering readBody; none was stated.", "server.ts: spec ambiguity (missing_requirement): readJson.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering readJson; none was stated."]
- `verification_violations`: ["board.ts: TypeScript function `moveTask` uses `task` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches", "server.ts: TypeScript function `handlePatch` uses `task` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches", "server.ts: TypeScript function `handlePatch` indexes with the result of `.indexOf((…)` inline — a miss yields a sentinel (`-1`) used directly as an index"]

### 検出事項
- `verification_violations`
  - board.ts: TypeScript function `moveTask` uses `task` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches
  - server.ts: TypeScript function `handlePatch` uses `task` (from `.find(...)`) without an `undefined`/`null` check — `find` returns `undefined` when no element matches
  - server.ts: TypeScript function `handlePatch` indexes with the result of `.indexOf((…)` inline — a miss yields a sentinel (`-1`) used directly as an index
- `cross_validation_gaps`
  - server.ts: spec ambiguity (missing_requirement): readBody.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering readBody; none was stated.
  - server.ts: spec ambiguity (missing_requirement): readBody.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering readBody; none was stated.
  - server.ts: spec ambiguity (missing_requirement): readJson.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering readJson; none was stated.
  - server.ts: spec ambiguity (missing_requirement): readJson.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering readJson; none was stated.
  - server.ts: spec ambiguity (missing_requirement): sendJson.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering sendJson; none was stated.
  - server.ts: spec ambiguity (missing_requirement): sendJson.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering sendJson; none was stated.
  - server.ts: spec ambiguity (missing_requirement): sendError.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering sendError; none was stated.
  - server.ts: spec ambiguity (missing_requirement): sendError.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering sendError; none was stated.
  - server.ts: spec ambiguity (missing_requirement): currentUser.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering currentUser; none was stated.
  - server.ts: spec ambiguity (missing_requirement): currentUser.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering currentUser; none was stated.
- `spec_health_issues`
  - board.ts: malformed-extraction: moveTask ensures: garbled comparison operators '==>'
  - board.ts: malformed-extraction: paginate ensures: garbled comparison operators '==>'
