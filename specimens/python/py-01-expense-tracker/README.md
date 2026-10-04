# py-01-expense-tracker

A small HTTP expense tracker backed by SQLite. Users record expenses with an
amount in cents, a category label such as `food:groceries`, and a day
(`YYYY-MM-DD`). The service can summarise a month, track a monthly budget per
user, and export CSV reports.

Default port: 8311

## Running

```bash
./run.sh                 # starts the server, exercises the happy path, exits 0
./repro.sh               # demonstrates every documented defect, exits 0 when all reproduce
```

Or start it manually:

```bash
DATA_DIR=$(mktemp -d) PORT=8311 python3 app.py
```

Runtime state (the SQLite database and generated reports) lives under
`DATA_DIR` (default `./data`). The scripts pass a temporary `DATA_DIR` and
clean it up on exit.

## API

Identity for writes is carried by the `X-User` header.

- `POST /expenses` — JSON body `{"amount_cents": int, "category": "food:groceries", "day": "YYYY-MM-DD", "note": "..."}`. Returns `201`.
- `GET /expenses?user=<name>` — lists the expenses for a user as JSON.
- `GET /summary?user=<name>&month=YYYY-MM` — month totals, a per-day average
  over the days that have expenses, and a per-subcategory breakdown (the part
  of the category label after `:`).
- `POST /budget` — JSON body `{"user": "...", "month": "YYYY-MM", "limit_cents": int}`.
  The response `status` is `exceeded` once spending reaches the limit, and
  `ok` while budget remains.
- `POST /reports?user=<name>&month=YYYY-MM` — writes a CSV report into the
  reports directory and returns its file name.
- `GET /export?path=<name>` — serves a file from the reports directory.
- `GET /admin/stats` — requires the `X-Admin-Token` header; returns per-user
  counts and totals.
- `GET /health` — service status including the number of open database
  connections.
