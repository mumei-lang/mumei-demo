## No-.mm ディレクトリ監査レポート

- ステータス: **合格**
- 言語: `mixed`
- Source: `specimens/typescript/ts-03-invoice-cli`
- verification_status: `verified`
- Summary: Audit directory: specimens/typescript/ts-03-invoice-cli\n  invoice.ts: 0 violations, 0 gaps\n  pricing.ts: 0 violations, 0 gaps\nSummary: 2 files, 0 files with issues\nnext_steps:\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: parseArgs.requires, parseArgs.ensures, invoiceId.requires, invoiceId.ensures, row.requires, row.ensures, renderInvoice.requires, renderInvoice.ensures, writeInvoice.requires, writeInvoice.ensures, main.requires, main.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: parseItem.requires, parseItem.ensures, parseItems.requires, parseItems.ensures, lineTotal.requires, lineTotal.ensures, subtotal.requires, subtotal.ensures, applyDiscount.requires, taxAmount.requires, taxAmount.ensures, computeTotals.requires, computeTotals.ensures, effectiveTaxRate.requires, pageFooters.requires, pageFooters.ensures, money.requires, money.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: parseArgs.requires, parseArgs.ensures, invoiceId.requires, invoiceId.ensures, row.requires, row.ensures, renderInvoice.requires, renderInvoice.ensures, writeInvoice.requires, writeInvoice.ensures, main.requires, main.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: parseItem.requires, parseItem.ensures, parseItems.requires, parseItems.ensures, lineTotal.requires, lineTotal.ensures, subtotal.requires, subtotal.ensures, applyDiscount.requires, taxAmount.requires, taxAmount.ensures, computeTotals.requires, computeTotals.ensures, effectiveTaxRate.requires, pageFooters.requires, pageFooters.ensures, money.requires, money.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- レビュー専用のギャップはありません。

### 検出事項
- 検出事項はありません。
