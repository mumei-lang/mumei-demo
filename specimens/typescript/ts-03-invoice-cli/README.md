# ts-03-invoice-cli

A command-line invoice calculator written in TypeScript on Node's standard
library. It reads line items from a JSON file, applies a percentage discount
and tax, and prints a text invoice (or JSON with `--json`). Invoices longer
than ten lines get a page footer per printed page. With `--out` the invoice is
written to a file and the written file is checked against the rendered text.

## Usage

```bash
node invoice.ts --items items.json --tax 10 --discount 5 --out invoice.txt   # Node 23.6+
node --experimental-strip-types invoice.ts --items items.json --tax 10       # Node 22.6 - 23.5
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--items FILE` | `items.json` | JSON array of `{"sku", "description"?, "unitPrice", "quantity"}` |
| `--tax PCT` | `0` | Tax rate in percent |
| `--discount PCT` | `0` | Discount in percent, applied before tax |
| `--customer NAME` | `ACME Corp` | Customer name on the invoice |
| `--date YYYY-MM-DD` | today | Invoice date |
| `--out FILE` | stdout | Write the invoice to FILE |
| `--json` | off | Emit JSON instead of text |

`items.json` in this directory is a small sample order.

## Scripts

- `./run.sh` renders the sample order as text, to a file under `out/`, and as
  JSON, and exits 0.
- `./repro.sh` runs one check per entry in `DEFECTS.json` against fixtures it
  writes to `out/repro/`, printing `[REPRODUCED]` / `[NOT REPRODUCED]` lines;
  exits 0 only when every case reproduces.
