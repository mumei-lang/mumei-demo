## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/python/py-02-report-cli`
- verification_status: `refuted`
- finding_counts: `code=2, confirmed=0, spec=2, model_limitations=0, errors=0`
- files_with_spec_diagnostics: `1`
- Summary: Audit directory: specimens/python/py-02-report-cli\n  report.py: 0 violations, 0 gaps\n  timesheet.py: 2 violations, 2 gaps\nSummary: 2 files, 1 file with issues, 1 file with spec diagnostics\nfinding_counts: code=2, confirmed=0, spec=2, model_limitations=0, errors=0\ntriage: refuted=1, verified=0, unverifiable=1\nnext_steps:\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: parse_args.requires, parse_row.requires, load_entries.requires, aggregate.requires, render.requires, post_process.requires, post_process.ensures, main.requires\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: parse_duration.requires, overtime_minutes.requires, is_weekend.requires\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: parse_args.requires, parse_row.requires, load_entries.requires, aggregate.requires, render.requires, post_process.requires, post_process.ensures, main.requires
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
2. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
3. **[V1-E-1:重要]** validate-spec-to-code で制約の対応を確認
   ```bash
   mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human
   ```
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: parse_duration.requires, overtime_minutes.requires, is_weekend.requires
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["timesheet.py: spec stronger than implementation: share_of_total", "timesheet.py: spec precondition assumed, not enforced, by `share_of_total`"]
- `verification_violations`: ["timesheet.py: Python function `share_of_total` can divide by `whole` without a non-zero contract (Z3 counterexample: whole=0)", "timesheet.py: Z3 Counter-example: whole=0"]

### 検出事項
- `verification_violations`
  - timesheet.py: Python function `share_of_total` can divide by `whole` without a non-zero contract (Z3 counterexample: whole=0)
  - timesheet.py: Z3 Counter-example: whole=0
- `cross_validation_gaps`
  - timesheet.py: spec stronger than implementation: share_of_total
  - timesheet.py: spec precondition assumed, not enforced, by `share_of_total`
