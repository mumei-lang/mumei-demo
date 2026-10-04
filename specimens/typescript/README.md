# TypeScript specimens

Runnable TypeScript apps (Node 22.6+ type stripping, standard library only)
with known ground truth in each specimen's `DEFECTS.json`. See
[`../README.md`](../README.md) for conventions.

| Id | Kind | Description | Default port | Defects |
| --- | --- | --- | --- | --- |
| [`ts-01-task-board`](ts-01-task-board/) | web | Kanban task board JSON API with workflow columns, board summary and live search | 8321 | 12 |
| [`ts-02-url-shortener`](ts-02-url-shortener/) | web | URL shortener with aliases, expiry, click stats, link previews and admin delete | 8322 | 11 |
| [`ts-03-invoice-cli`](ts-03-invoice-cli/) | cli | Invoice calculator CLI: JSON line items, discount, tax, text/JSON output | - | 10 |

Each specimen has `run.sh` (happy path) and `repro.sh` (one case per defect).
Both detect the Node version and pass `--experimental-strip-types` only when
the running Node needs it.
