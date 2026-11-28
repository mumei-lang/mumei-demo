## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/go/go-02-logscan-cli`
- verification_status: `refuted`
- finding_counts: `code=2, confirmed=0, spec=0, model_limitations=0, errors=0`
- files_with_spec_diagnostics: `0`
- Summary: Audit directory: specimens/go/go-02-logscan-cli\n  main.go: 2 violations, 0 gaps\nSummary: 1 file, 1 file with issues, 0 files with spec diagnostics\nfinding_counts: code=2, confirmed=0, spec=0, model_limitations=0, errors=0\ntriage: refuted=1, verified=0, unverifiable=0\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: main.requires, main.ensures, run.requires, run.ensures, parsePercentiles.requires, parsePercentiles.ensures, readFiles.requires, readFiles.ensures, parseFile.requires, parseFile.ensures, formatSummary.requires, formatSummary.ensures, percentileAt.requires, percentileAt.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: main.requires, main.ensures, run.requires, run.ensures, parsePercentiles.requires, parsePercentiles.ensures, readFiles.requires, readFiles.ensures, parseFile.requires, parseFile.ensures, formatSummary.requires, formatSummary.ensures, percentileAt.requires, percentileAt.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `verification_violations`: ["main.go: Go function `formatSummary` can divide by `int64(len(records))` without a non-zero contract (Z3 counterexample: int64(len(records))=0)", "main.go: Z3 Counter-example: int64(len(records))=0"]

### 検出事項
- `verification_violations`
  - main.go: Go function `formatSummary` can divide by `int64(len(records))` without a non-zero contract (Z3 counterexample: int64(len(records))=0)
  - main.go: Z3 Counter-example: int64(len(records))=0
