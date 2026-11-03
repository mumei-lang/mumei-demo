## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/typescript/ts-03-invoice-cli`
- verification_status: `unverifiable`
- Summary: Audit directory: specimens/typescript/ts-03-invoice-cli\n  invoice.ts: 0 violations, 7 gaps\n  pricing.ts: 0 violations, 8 gaps\nSummary: 2 files, 2 files with issues\nnext_steps:\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 2263-2288\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: validate-spec で仕様の矛盾を修正\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: subtotal.requires, subtotal.ensures, money.requires, money.ensures, conditional at Position 1577-1646, conditional at Position 2322-2361, conditional at Position 3029-3064\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** validate-spec-to-code で制約の対応を確認
   ```bash
   mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human
   ```
2. **[V1-E-1:重要]** 欠落要件を追記してから再監査（推測で補完しない）
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 2263-2288
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** validate-spec で仕様の矛盾を修正
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
5. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: subtotal.requires, subtotal.ensures, money.requires, money.ensures, conditional at Position 1577-1646, conditional at Position 2322-2361, conditional at Position 3029-3064
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["invoice.ts: spec ambiguity (missing_requirement): parseArgs.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering parseArgs; none was stated.", "invoice.ts: spec ambiguity (missing_requirement): parseArgs.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering parseArgs; none was stated.", "invoice.ts: spec ambiguity (missing_requirement): row.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering row; none was stated."]

### 検出事項
- `cross_validation_gaps`
  - invoice.ts: spec ambiguity (missing_requirement): parseArgs.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering parseArgs; none was stated.
  - invoice.ts: spec ambiguity (missing_requirement): parseArgs.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering parseArgs; none was stated.
  - invoice.ts: spec ambiguity (missing_requirement): row.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering row; none was stated.
  - invoice.ts: spec ambiguity (missing_requirement): row.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering row; none was stated.
  - invoice.ts: spec ambiguity (missing_requirement): renderInvoice.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering renderInvoice; none was stated.
  - invoice.ts: spec ambiguity (missing_requirement): main.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering main; none was stated.
  - invoice.ts: spec ambiguity (missing_requirement): main.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering main; none was stated.
  - pricing.ts: spec ambiguity (missing_requirement): parseItems.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering parseItems; none was stated.
  - pricing.ts: spec ambiguity (missing_requirement): parseItems.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering parseItems; none was stated.
  - pricing.ts: spec ambiguity (missing_requirement): toCents.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering toCents; none was stated.
- `spec_health_issues`
  - pricing.ts: malformed-extraction: parseItem ensures: garbled comparison operators '==>'
  - pricing.ts: malformed-extraction: parseItem ensures: garbled comparison operators '==>'
  - pricing.ts: malformed-extraction: effectiveTaxRate ensures: garbled comparison operators '==>'
  - pricing.ts: malformed-extraction: effectiveTaxRate ensures: garbled comparison operators '==>'
  - pricing.ts: malformed-extraction: pageFooters ensures: garbled comparison operators '==>'
  - pricing.ts: malformed-extraction: pageFooters ensures: garbled comparison operators '==>'
