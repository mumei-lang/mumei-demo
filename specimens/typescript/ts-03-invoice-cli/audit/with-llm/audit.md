## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/typescript/ts-03-invoice-cli`
- verification_status: `unverifiable`
- Summary: Audit directory: specimens/typescript/ts-03-invoice-cli\n  invoice.ts: 0 violations, 6 gaps\n  pricing.ts: 0 violations, 0 gaps\nSummary: 2 files, 2 files with issues\nnext_steps:\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: validate-spec で仕様の矛盾を修正\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 1922-2004\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 1236-1276, conditional at Position 2020-2131, conditional at Position 2323-2449, conditional at Position 2453-2595, conditional at Position 3149-3167, conditional at Position 3250-3307, conditional at Position 4463-4576\n    command: mumei-agent validate-spec --input <spec> --format human

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
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 1922-2004
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
5. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 1236-1276, conditional at Position 2020-2131, conditional at Position 2323-2449, conditional at Position 2453-2595, conditional at Position 3149-3167, conditional at Position 3250-3307, conditional at Position 4463-4576
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
  - invoice.ts: spec ambiguity (missing_requirement): main.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering main; none was stated.
  - invoice.ts: spec ambiguity (missing_requirement): main.ensures — no requirement text mentions this atom and the extracted ensures clause is trivial. Add a requirement covering main; none was stated.
- `spec_health_issues`
  - invoice.ts: encoding-gap: renderInvoice: spec_lowering_failed: failed to lower requires clause 'len(invoice.items) >= 0': Type Error: len() expects an array or string argument (constraints: ["len(invoice.items) >= 0"])
  - pricing.ts: malformed-extraction: parseItem ensures: garbled comparison operators '==>'
  - pricing.ts: malformed-extraction: parseItem ensures: garbled comparison operators '==>'
  - pricing.ts: malformed-extraction: subtotal ensures: garbled comparison operators '==>'
  - pricing.ts: malformed-extraction: pageFooters ensures: garbled comparison operators '==>'
  - pricing.ts: malformed-extraction: pageFooters ensures: garbled comparison operators '==>'
