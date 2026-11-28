## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/python/py-04-doc-vault`
- verification_status: `unverifiable`
- finding_counts: `code=2, confirmed=0, spec=1, model_limitations=0, errors=0`
- files_with_spec_diagnostics: `1`
- Summary: Audit directory: specimens/python/py-04-doc-vault\n  app.py: 0 violations, 0 gaps\n  vault.py: 2 violations, 1 gap\nSummary: 2 files, 1 file with issues, 1 file with spec diagnostics\nfinding_counts: code=2, confirmed=0, spec=1, model_limitations=0, errors=0\ntriage: refuted=0, verified=0, unverifiable=2\nnext_steps:\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: log_message.requires, log_message.ensures, _read_json.requires, _respond.requires, _respond.ensures, _respond_html.requires, _respond_html.ensures, _respond_text.requires, _respond_text.ensures, _api_key.requires, _dispatch.requires, _dispatch.ensures, _route.requires, do_GET.requires, do_GET.ensures, do_POST.requires, do_POST.ensures, upload.requires, upload.ensures, get_doc.requires, share.requires, share.ensures, fetch.requires, fetch.ensures, purge.requires, go.requires, go.ensures, docs_html.requires, docs_html.ensures, quota.requires, quota.ensures, main.requires, main.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: high\n    action: validate-spec-to-code で制約の対応を確認\n    command: mumei-agent validate-spec-to-code --spec <spec> --code <file> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: token_matches.requires, token_matches.ensures, share_expiry.requires, remaining_quota.requires, can_read.requires, can_read.ensures, __init__.requires, __init__.ensures, _stage.requires, save_upload.requires, decode_body.requires, fetch_remote.requires, get.requires, create_share.requires, usage_for.requires, purge.requires\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: log_message.requires, log_message.ensures, _read_json.requires, _respond.requires, _respond.ensures, _respond_html.requires, _respond_html.ensures, _respond_text.requires, _respond_text.ensures, _api_key.requires, _dispatch.requires, _dispatch.ensures, _route.requires, do_GET.requires, do_GET.ensures, do_POST.requires, do_POST.ensures, upload.requires, upload.ensures, get_doc.requires, share.requires, share.ensures, fetch.requires, fetch.ensures, purge.requires, go.requires, go.ensures, docs_html.requires, docs_html.ensures, quota.requires, quota.ensures, main.requires, main.ensures
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
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: token_matches.requires, token_matches.ensures, share_expiry.requires, remaining_quota.requires, can_read.requires, can_read.ensures, __init__.requires, __init__.ensures, _stage.requires, save_upload.requires, decode_body.requires, fetch_remote.requires, get.requires, create_share.requires, usage_for.requires, purge.requires
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `cross_validation_gaps`: ["vault.py: spec precondition assumed, not enforced, by `make_share_token`"]
- `verification_violations`: ["vault.py: Python function `token_matches` uses early-exit credential comparison that may expose a timing side channel", "vault.py: Python function `make_share_token` generates credential material with direct weak randomness at line 25"]

### 検出事項
- `verification_violations`
  - vault.py: Python function `token_matches` uses early-exit credential comparison that may expose a timing side channel
  - vault.py: Python function `make_share_token` generates credential material with direct weak randomness at line 25
- `cross_validation_gaps`
  - vault.py: spec precondition assumed, not enforced, by `make_share_token`
