## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/rust/rs-01-bank-core`
- verification_status: `refuted`
- Summary: Audit directory: specimens/rust/rs-01-bank-core\n  src/bank.rs: 3 violations, 0 gaps\n  src/main.rs: 0 violations, 0 gaps\n  src/store.rs: 0 violations, 0 gaps\nSummary: 3 files, 1 file with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: accrue_interest.requires, accrue_interest.ensures, remaining_daily_allowance.requires, remaining_daily_allowance.ensures, split_payment.requires, split_payment.ensures, find_index.requires, find_index.ensures, get_mut.requires, get_mut.ensures, account_at.requires, account_at.ensures, open_account.requires, open_account.ensures, deposit.requires, deposit.ensures, request_transfer.requires, request_transfer.ensures, settle.requires, settle.ensures, close_account.requires, close_account.ensures, charge_fee.requires, charge_fee.ensures, apply_interest.requires, apply_interest.ensures, adjust.requires, adjust.ensures, record_audit.requires, record_audit.ensures, recent_audit.requires, recent_audit.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: parse_cents.requires, parse_cents.ensures, operator_token.requires, operator_token.ensures, balance_of.requires, balance_of.ensures, print_balance.requires, print_balance.ensures, write_statement.requires, write_statement.ensures, usage.requires, usage.ensures, run_line.requires, main.requires, main.ensures\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: load.requires, load.ensures, save.requires, save.ensures\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: accrue_interest.requires, accrue_interest.ensures, remaining_daily_allowance.requires, remaining_daily_allowance.ensures, split_payment.requires, split_payment.ensures, find_index.requires, find_index.ensures, get_mut.requires, get_mut.ensures, account_at.requires, account_at.ensures, open_account.requires, open_account.ensures, deposit.requires, deposit.ensures, request_transfer.requires, request_transfer.ensures, settle.requires, settle.ensures, close_account.requires, close_account.ensures, charge_fee.requires, charge_fee.ensures, apply_interest.requires, apply_interest.ensures, adjust.requires, adjust.ensures, record_audit.requires, record_audit.ensures, recent_audit.requires, recent_audit.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: parse_cents.requires, parse_cents.ensures, operator_token.requires, operator_token.ensures, balance_of.requires, balance_of.ensures, print_balance.requires, print_balance.ensures, write_statement.requires, write_statement.ensures, usage.requires, usage.ensures, run_line.requires, main.requires, main.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: load.requires, load.ensures, save.requires, save.ensures
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```

### 人手レビュー入口
- `next_steps` が human review の最初の入口です。
- `verification_violations`: ["src/bank.rs: Rust function `request_transfer` can truncate `amount_cents` in cast to `u64` without a range contract (amount_cents outside 0..=18446744073709551615 wraps)", "src/bank.rs: Rust function `charge_fee` can truncate `cents` in cast to `u64` without a range contract (cents outside 0..=18446744073709551615 wraps)", "src/bank.rs: Z3 Counter-example: amount_cents=-9223372036854775808"]

### 検出事項
- `verification_violations`
  - src/bank.rs: Rust function `request_transfer` can truncate `amount_cents` in cast to `u64` without a range contract (amount_cents outside 0..=18446744073709551615 wraps)
  - src/bank.rs: Rust function `charge_fee` can truncate `cents` in cast to `u64` without a range contract (cents outside 0..=18446744073709551615 wraps)
  - src/bank.rs: Z3 Counter-example: amount_cents=-9223372036854775808
