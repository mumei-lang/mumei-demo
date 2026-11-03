## No-.mm ディレクトリ監査レポート

- ステータス: **要レビュー**
- 言語: `mixed`
- Source: `specimens/rust/rs-01-bank-core`
- verification_status: `refuted`
- Summary: Audit directory: specimens/rust/rs-01-bank-core\n  src/bank.rs: 3 violations, 0 gaps\n  src/main.rs: 0 violations, 0 gaps\n  src/store.rs: 0 violations, 0 gaps\nSummary: 3 files, 2 files with issues\nnext_steps:\n  - priority: high\n    action: migrate-suggest で .mm スケルトンを生成\n    command: mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: accrue_interest.requires, remaining_daily_allowance.requires, find_index.requires, get_mut.requires, open_account.requires, deposit.requires, request_transfer.requires, settle.requires, close_account.requires, charge_fee.requires, apply_interest.requires, adjust.requires, record_audit.requires, recent_audit.requires\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: parse_cents.requires, parse_cents.ensures, usage.requires, usage.ensures, main.requires, main.ensures, conditional at Position 2069-2084, conditional at Position 2416-2565\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: validate-spec で仕様の矛盾を修正\n    command: mumei-agent validate-spec --input <spec> --format human\n  - priority: medium\n    action: underspecified な意図を明文化（推測で補完しない）: conditional at Position 582-611\n    command: mumei-agent validate-spec --input <spec> --format human

### 次の手順 (V1-E-1)
1. **[V1-E-1:重要]** migrate-suggest で .mm スケルトンを生成
   ```bash
   mumei-agent migrate-suggest --code-file <file> --language <lang> --output generated/mm
   ```
2. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: accrue_interest.requires, remaining_daily_allowance.requires, find_index.requires, get_mut.requires, open_account.requires, deposit.requires, request_transfer.requires, settle.requires, close_account.requires, charge_fee.requires, apply_interest.requires, adjust.requires, record_audit.requires, recent_audit.requires
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
3. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: parse_cents.requires, parse_cents.ensures, usage.requires, usage.ensures, main.requires, main.ensures, conditional at Position 2069-2084, conditional at Position 2416-2565
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
4. **[V1-E-1:通常]** validate-spec で仕様の矛盾を修正
   ```bash
   mumei-agent validate-spec --input <spec> --format human
   ```
5. **[V1-E-1:通常]** underspecified な意図を明文化（推測で補完しない）: conditional at Position 582-611
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
- `spec_health_issues`
  - src/store.rs: malformed-extraction: load ensures: garbled comparison operators '==>'
  - src/store.rs: malformed-extraction: load ensures: garbled comparison operators '==>'
  - src/store.rs: malformed-extraction: load ensures: garbled comparison operators '==>'
  - src/store.rs: malformed-extraction: save ensures: garbled comparison operators '==>'
  - src/store.rs: malformed-extraction: save ensures: garbled comparison operators '==>'
