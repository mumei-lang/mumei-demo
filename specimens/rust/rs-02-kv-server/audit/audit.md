## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/rust/rs-02-kv-server`
- verification_status: `verified`
- finding_counts: `code=2, confirmed=0, spec=0, model_limitations=0, errors=0`
- files_with_spec_diagnostics: `0`
- Summary: Audit directory: specimens/rust/rs-02-kv-server\n  src/main.rs: 2 violations, 0 gaps\nSummary: 1 file, 1 file with issues, 0 files with spec diagnostics\nfinding_counts: code=2, confirmed=0, spec=0, model_limitations=0, errors=0\ntriage: refuted=0, verified=1, unverifiable=0\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: data_dir.requires, data_dir.ensures, normalize_key.requires, normalize_key.ensures, incr.requires, incr.ensures, keys_with_prefix.requires, keys_with_prefix.ensures, snapshot.requires, snapshot.ensures, flush.requires, flush.ensures, log_line.requires, log_line.ensures, read_request.requires, read_request.ensures, find_subslice.requires, find_subslice.ensures, split_target.requires, split_target.ensures, url_decode.requires, url_decode.ensures, respond.requires, respond.ensures, handle.requires, handle.ensures, main.requires, main.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: data_dir.requires, data_dir.ensures, normalize_key.requires, normalize_key.ensures, incr.requires, incr.ensures, keys_with_prefix.requires, keys_with_prefix.ensures, snapshot.requires, snapshot.ensures, flush.requires, flush.ensures, log_line.requires, log_line.ensures, read_request.requires, read_request.ensures, find_subslice.requires, find_subslice.ensures, split_target.requires, split_target.ensures, url_decode.requires, url_decode.ensures, respond.requires, respond.ensures, handle.requires, handle.ensures, main.requires, main.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `verification_violations`: ["src/main.rs: Rust function `handle` uses hardcoded credential constant `ADMIN_TOKEN` stored directly in source", "src/main.rs: Rust function `read_request` indexes a split-produced `Vec` with a positive literal index without a dominating length guard"]

### 検出事項
- `verification_violations`
  - src/main.rs: Rust function `handle` uses hardcoded credential constant `ADMIN_TOKEN` stored directly in source
  - src/main.rs: Rust function `read_request` indexes a split-produced `Vec` with a positive literal index without a dominating length guard
