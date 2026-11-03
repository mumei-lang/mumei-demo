## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/go/go-03-auth-gateway`
- verification_status: `unverifiable`
- Summary: Audit directory: specimens/go/go-03-auth-gateway\n  auth.go: 0 violations, 5 gaps\n  handlers.go: 0 violations, 4 gaps\n  main.go: 0 violations, 2 gaps\nSummary: 3 files, 3 files with issues\nnext_steps:\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: validate-spec で仕様の矛盾を修正\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 236-285, conditional at Position 1868-1913, conditional at Position 2463-2519, conditional at Position 3313-3378\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** validate-spec-to-code で制約の対応を確認
   ```bash
   mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human
   ```
2. **[V1-E-1:重要]** 欠落要件を追記してから再監査（推測で補完しない）
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** validate-spec で仕様の矛盾を修正
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 236-285, conditional at Position 1868-1913, conditional at Position 2463-2519, conditional at Position 3313-3378
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["auth.go: spec ambiguity (missing_requirement): newUser.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering newUser; none was stated.", "auth.go: spec ambiguity (missing_requirement): newUser.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering newUser; none was stated.", "auth.go: spec ambiguity (missing_requirement): passwordMatches.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering passwordMatches; none was stated."]

### 検出事項
- `cross_validation_gaps`
  - auth.go: spec ambiguity (missing_requirement): newUser.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering newUser; none was stated.
  - auth.go: spec ambiguity (missing_requirement): newUser.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering newUser; none was stated.
  - auth.go: spec ambiguity (missing_requirement): passwordMatches.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering passwordMatches; none was stated.
  - auth.go: spec ambiguity (missing_requirement): tokenMatches.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering tokenMatches; none was stated.
  - auth.go: spec ambiguity (missing_requirement): tokenMatches.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering tokenMatches; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): rotateHandler.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering rotateHandler; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): rotateHandler.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering rotateHandler; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): writeJSON.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering writeJSON; none was stated.
  - handlers.go: spec ambiguity (missing_requirement): writeJSON.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering writeJSON; none was stated.
  - main.go: spec ambiguity (missing_requirement): main.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering main; none was stated.
- `spec_health_issues`
  - auth.go: malformed-extraction: sessionUser ensures: garbled comparison operators '==>'
  - auth.go: malformed-extraction: sessionUser ensures: garbled comparison operators '==>'
