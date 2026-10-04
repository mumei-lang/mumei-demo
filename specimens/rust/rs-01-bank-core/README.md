# rs-01-bank-core

A small banking ledger core with a CLI front end. Accounts hold integer
balances in cents, transfers are queued and applied by a `settle` run, and the
ledger persists to a line-oriented state file between invocations.

## Build

```bash
cargo build --release
```

## Usage

```bash
BIN=target/release/bank-core
$BIN [--state PATH] [--token T] <command> [args]
```

Commands:

- `open <acct> <starting_cents> [daily_limit_cents]` — create an account
- `deposit <acct> <cents>`
- `transfer <from> <to> <cents>` — queue a transfer for settlement
- `fee <acct> <cents>` — charge a fee (counts toward daily usage)
- `interest <acct>` — accrue interest at the configured rate
- `split <amount> <recipients...>` — print the per-recipient share
- `statement <acct> [--out NAME]` — print or save a statement into `reports/`
- `account-at <index>` — print the account at an internal index
- `close <acct>` / `adjust <acct> <delta>` — operator commands (`--token` or `BANK_OPERATOR_TOKEN`)
- `settle` — apply all queued transfers
- `batch` — read one command per line from stdin
- `balance <acct>`, `audit-count` — query helpers

State lives in `state.txt` next to the binary's working directory; pass
`--state` to use a different file.
