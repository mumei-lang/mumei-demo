## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/python/py-02-report-cli`
- verification_status: `refuted`
- Summary: Audit directory: specimens/python/py-02-report-cli\n  report.py: 0 violations, 4 gaps\n  timesheet.py: 2 violations, 0 gaps\nSummary: 2 files, 2 files with issues\nnext_steps:\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: high\n    action: 欠落要件を追記してから再監査（推測で補完しない）\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: parse_args.requires, post_process.requires, post_process.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 992-1085\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** validate-spec-to-code で制約の対応を確認
   ```bash
   mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human
   ```
2. **[V1-E-1:重要]** 欠落要件を追記してから再監査（推測で補完しない）
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: parse_args.requires, post_process.requires, post_process.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
5. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 992-1085
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["report.py: spec ambiguity (missing_requirement): load_entries.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering load_entries; none was stated.", "report.py: spec ambiguity (missing_requirement): aggregate.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering aggregate; none was stated.", "report.py: spec ambiguity (missing_requirement): render.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering render; none was stated."]
- `verification_violations`: ["timesheet.py: Python function `share_of_total` can divide by `whole` without a non-zero contract (Z3 counterexample: whole=0)", "timesheet.py: Z3 Counter-example: whole=0"]

### 検出事項
- `verification_violations`
  - timesheet.py: Python function `share_of_total` can divide by `whole` without a non-zero contract (Z3 counterexample: whole=0)
  - timesheet.py: Z3 Counter-example: whole=0
- `cross_validation_gaps`
  - report.py: spec ambiguity (missing_requirement): load_entries.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering load_entries; none was stated.
  - report.py: spec ambiguity (missing_requirement): aggregate.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering aggregate; none was stated.
  - report.py: spec ambiguity (missing_requirement): render.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering render; none was stated.
  - report.py: spec ambiguity (missing_requirement): main.requires — no requirement text mentions this atom and the extracted requires clause is trivial. Add a requirement covering main; none was stated.
