## No-.mm ディレクトリ監査レポート

- ステータス: **合格**
- 言語: `mixed`
- Source: `specimens/go/go-03-auth-gateway`
- verification_status: `verified`
- finding_counts: `code=0, confirmed=0, spec=1, model_limitations=0, errors=0`
- files_with_spec_diagnostics: `1`
- Summary: Audit directory: specimens/go/go-03-auth-gateway\n  auth.go: 0 violations, 1 gap\n  handlers.go: 0 violations, 0 gaps\n  main.go: 0 violations, 0 gaps\nSummary: 3 files, 0 files with issues, 1 file with spec diagnostics\nfinding_counts: code=0, confirmed=0, spec=1, model_limitations=0, errors=0\ntriage: refuted=0, verified=3, unverifiable=0\nnext_steps:\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: randomHex.requires, randomHex.ensures, seedUsers.requires, seedUsers.ensures, newUser.requires, newUser.ensures, hashPassword.requires, hashPassword.ensures, passwordMatches.ensures, tokenMatches.requires, tokenMatches.ensures, sessionUser.requires, sessionUser.ensures, bearerUser.requires, bearerUser.ensures, allowAttempt.requires, allowAttempt.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: loginHandler.requires, loginHandler.ensures, profileHandler.requires, profileHandler.ensures, proxyHandler.requires, proxyHandler.ensures, rotateHandler.requires, rotateHandler.ensures, healthHandler.requires, healthHandler.ensures, writeJSON.requires, writeJSON.ensures, publicAddress.requires, publicAddress.ensures, localPath.requires, localPath.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: main.requires, main.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** validate-spec-to-code で制約の対応を確認
   ```bash
   mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: randomHex.requires, randomHex.ensures, seedUsers.requires, seedUsers.ensures, newUser.requires, newUser.ensures, hashPassword.requires, hashPassword.ensures, passwordMatches.ensures, tokenMatches.requires, tokenMatches.ensures, sessionUser.requires, sessionUser.ensures, bearerUser.requires, bearerUser.ensures, allowAttempt.requires, allowAttempt.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: loginHandler.requires, loginHandler.ensures, profileHandler.requires, profileHandler.ensures, proxyHandler.requires, proxyHandler.ensures, rotateHandler.requires, rotateHandler.ensures, healthHandler.requires, healthHandler.ensures, writeJSON.requires, writeJSON.ensures, publicAddress.requires, publicAddress.ensures, localPath.requires, localPath.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: main.requires, main.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["auth.go: spec precondition assumed, not enforced, by `passwordMatches`"]

### 検出事項
- `cross_validation_gaps`
  - auth.go: spec precondition assumed, not enforced, by `passwordMatches`
