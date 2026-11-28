## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/typescript/ts-02-url-shortener`
- verification_status: `verified`
- finding_counts: `code=3, confirmed=0, spec=0, model_limitations=0, errors=0`
- files_with_spec_diagnostics: `0`
- Summary: Audit directory: specimens/typescript/ts-02-url-shortener\n  links.ts: 2 violations, 0 gaps\n  server.ts: 1 violation, 0 gaps\nSummary: 2 files, 2 files with issues, 0 files with spec diagnostics\nfinding_counts: code=3, confirmed=0, spec=0, model_limitations=0, errors=0\ntriage: refuted=0, verified=2, unverifiable=0\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: nowSeconds.requires, nowSeconds.ensures, generateCode.requires, generateCode.ensures, validateTarget.requires, validateTarget.ensures, validateAlias.requires, validateAlias.ensures, normalizeAlias.requires, normalizeAlias.ensures, createLink.requires, createLink.ensures, isExpired.requires, isExpired.ensures, resolveLink.requires, resolveLink.ensures, clicksPerDay.requires, clicksPerDay.ensures, linkStats.requires, linkStats.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: readJson.requires, readJson.ensures, sendJson.requires, sendJson.ensures, fetchPreview.requires, fetchPreview.ensures, recordClick.requires, recordClick.ensures, handleShorten.requires, handleShorten.ensures, handleRedirect.requires, handleRedirect.ensures, handleStats.requires, handleStats.ensures, handleAdminDelete.requires, handleAdminDelete.ensures, route.requires, route.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: nowSeconds.requires, nowSeconds.ensures, generateCode.requires, generateCode.ensures, validateTarget.requires, validateTarget.ensures, validateAlias.requires, validateAlias.ensures, normalizeAlias.requires, normalizeAlias.ensures, createLink.requires, createLink.ensures, isExpired.requires, isExpired.ensures, resolveLink.requires, resolveLink.ensures, clicksPerDay.requires, clicksPerDay.ensures, linkStats.requires, linkStats.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: readJson.requires, readJson.ensures, sendJson.requires, sendJson.ensures, fetchPreview.requires, fetchPreview.ensures, recordClick.requires, recordClick.ensures, handleShorten.requires, handleShorten.ensures, handleRedirect.requires, handleRedirect.ensures, handleStats.requires, handleStats.ensures, handleAdminDelete.requires, handleAdminDelete.ensures, route.requires, route.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `verification_violations`: ["links.ts: TypeScript function `linkStats` uses `link` (from a type-asserted `Map.get(...)`) without an `undefined`/`null` check — the assertion hides a missing-key `undefined`", "links.ts: TypeScript function `generateCode` generates a lookup capability with direct weak randomness at line 36", "server.ts: TypeScript function `handleAdminDelete` uses hardcoded credential constant `ADMIN_TOKEN` stored directly in source"]

### 検出事項
- `verification_violations`
  - links.ts: TypeScript function `linkStats` uses `link` (from a type-asserted `Map.get(...)`) without an `undefined`/`null` check — the assertion hides a missing-key `undefined`
  - links.ts: TypeScript function `generateCode` generates a lookup capability with direct weak randomness at line 36
  - server.ts: TypeScript function `handleAdminDelete` uses hardcoded credential constant `ADMIN_TOKEN` stored directly in source
