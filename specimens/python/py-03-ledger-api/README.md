# py-03-ledger-api

A small in-memory double-entry ledger exposed over HTTP. Accounts are created
with an owner and an initial deposit, transfers move cents between accounts
and charge a flat 25-cent fee to the sender (credited to the house account
`0`, labelled `fees`), and each account exposes a JSON or HTML statement.

Default port: 8312

## Running

```bash
./run.sh                 # starts the server, exercises the happy path, exits 0
./repro.sh               # demonstrates every documented defect, exits 0 when all reproduce
```

Or start it manually:

```bash
DATA_DIR=$(mktemp -d) PORT=8312 python3 app.py
```

The transfer journal is written to `DATA_DIR` (default `./data`); account
state itself is in memory and resets on restart.

## API

Mutating calls carry the caller's identity in the `X-Owner` header.

- `POST /accounts` — JSON body `{"owner": "alice", "label": "checking", "initial_cents": 5000}`.
  Initial deposits are capped at 10000 cents. Returns the account including its `id`.
- `GET /accounts` — lists every account with balances.
- `GET /accounts/<id>` — returns one account.
- `POST /transfer` — JSON body `{"from": 1, "to": 2, "amount_cents": 300}`.
  Debits `amount + 25` from the source and credits `amount` to the destination.
- `POST /close` — JSON body `{"id": 3}`. Moves the remaining balance to the
  house account, appends a `close` entry to the statement, and marks the
  account closed.
- `GET /statement/<id>?offset=&limit=` — paginated JSON statement.
- `GET /statement/<id>.html` — HTML statement view.
- `GET /health` — service status.
