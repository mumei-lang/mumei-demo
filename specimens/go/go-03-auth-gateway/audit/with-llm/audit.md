## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/go/go-03-auth-gateway`
- verification_status: `unverifiable`
- Summary: Audit directory: specimens/go/go-03-auth-gateway\n  auth.go: 0 violations, 0 gaps\n  handlers.go: 0 violations, 0 gaps\n  main.go: 0 violations, 2 gaps\nSummary: 3 files, 3 files with issues\nnext_steps:\n  - priority: medium\n    action: validate-spec で仕様の矛盾を修正\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: tokenMatches.requires, conditional at Position 1715-1763, conditional at Position 2450-2477\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: vague_adjective at Position 2479-2489, conditional at Position 434-466\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:通常]** validate-spec で仕様の矛盾を修正
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: tokenMatches.requires, conditional at Position 1715-1763, conditional at Position 2450-2477
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: vague_adjective at Position 2479-2489, conditional at Position 434-466
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

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["main.go: spec ambiguity (missing_requirement): main.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering main; none was stated.", "main.go: spec ambiguity (missing_requirement): main.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering main; none was stated."]

### 検出事項
- `cross_validation_gaps`
  - main.go: spec ambiguity (missing_requirement): main.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering main; none was stated.
  - main.go: spec ambiguity (missing_requirement): main.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering main; none was stated.
- `spec_health_issues`
  - auth.go: encoding-gap: bearerUser: spec_not_boolean: ensures clause 'let token = if has_prefix(authorization_header, "Bearer ") then substring(authorization_header, 7, len(authorization_header)) else authorization_header' must lower to boolean (constraints: ["let token = if has_prefix(authorization_header, \"Bearer \") then substring(authorization_header, 7, len(authorization_header)) else authorization_header"])
  - auth.go: encoding-gap: allowAttempt: spec_not_boolean: ensures clause 'let key = if host_parse_succeeded then parsed_host else address' must lower to boolean (constraints: ["let key = if host_parse_succeeded then parsed_host else address"])
  - handlers.go: encoding-gap: loginHandler: spec_lowering_failed: failed to lower ensures clause '! allow_attempt => result.status == 429 && result.message == "try again later" && ! result.body_processed && ! result.session_recorded': Verification Error: Expected int (constraints: ["! allow_attempt => result.status == 429 && result.message == \"try again later\" && ! result.body_processed && ! result.session_recorded"])
  - handlers.go: encoding-gap: profileHandler: spec_lowering_failed: failed to lower requires clause 'account_exists || requested_user != "" || bearer_user == ""': Verification Error: Expected int (constraints: ["account_exists || requested_user != \"\" || bearer_user == \"\""])
  - handlers.go: encoding-gap: proxyHandler: spec_lowering_failed: failed to lower requires clause 'bearer_user == "" || ! upstream_succeeds ||(upstream_status >= 100 && upstream_status <= 599)': Verification Error: Expected int (constraints: ["bearer_user == \"\" || ! upstream_succeeds ||(upstream_status >= 100 && upstream_status <= 599)"])
  - handlers.go: encoding-gap: rotateHandler: spec_lowering_failed: failed to lower requires clause 'bearer_user != "admin" || epoch < i64 :: MAX': Verification Error: Expected int (constraints: ["bearer_user != \"admin\" || epoch < i64 :: MAX"])
  - handlers.go: encoding-gap: healthHandler: spec_lowering_failed: failed to lower ensures clause 'result.health_status == "ok"': Verification Error: Expected int (constraints: ["result.health_status == \"ok\""])
  - handlers.go: encoding-gap: writeJSON: spec_lowering_failed: failed to lower ensures clause 'result.content_type == "application/json"': Verification Error: Expected int (constraints: ["result.content_type == \"application/json\""])
