## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/go/go-03-auth-gateway`
- verification_status: `verified`
- finding_counts: `code=3, confirmed=0, spec=0, model_limitations=0, errors=0`
- files_with_spec_diagnostics: `0`
- Summary: Audit directory: specimens/go/go-03-auth-gateway\n  auth.go: 1 violation, 0 gaps\n  handlers.go: 1 violation, 0 gaps\n  main.go: 1 violation, 0 gaps\nSummary: 3 files, 3 files with issues, 0 files with spec diagnostics\nfinding_counts: code=3, confirmed=0, spec=0, model_limitations=0, errors=0\ntriage: refuted=0, verified=3, unverifiable=0\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: tokenMatches.requires, tokenMatches.ensures, sessionUser.requires, sessionUser.ensures, bearerUser.requires, bearerUser.ensures, allowAttempt.requires, allowAttempt.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: loginHandler.requires, loginHandler.ensures, profileHandler.requires, profileHandler.ensures, proxyHandler.requires, proxyHandler.ensures, rotateHandler.requires, rotateHandler.ensures, healthHandler.requires, healthHandler.ensures, writeJSON.requires, writeJSON.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: main.requires, main.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: tokenMatches.requires, tokenMatches.ensures, sessionUser.requires, sessionUser.ensures, bearerUser.requires, bearerUser.ensures, allowAttempt.requires, allowAttempt.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: loginHandler.requires, loginHandler.ensures, profileHandler.requires, profileHandler.ensures, proxyHandler.requires, proxyHandler.ensures, rotateHandler.requires, rotateHandler.ensures, healthHandler.requires, healthHandler.ensures, writeJSON.requires, writeJSON.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: main.requires, main.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `verification_violations`: ["auth.go: Go function `tokenMatches` uses non-constant-time credential comparison that may expose a timing side channel", "handlers.go: Go function `loginHandler` generates credential material from a timestamp at line 34", "main.go: Go hardcoded credential constant `adminPassword` in package main is stored directly in source"]

### 検出事項
- `verification_violations`
  - auth.go: Go function `tokenMatches` uses non-constant-time credential comparison that may expose a timing side channel
  - handlers.go: Go function `loginHandler` generates credential material from a timestamp at line 34
  - main.go: Go hardcoded credential constant `adminPassword` in package main is stored directly in source
