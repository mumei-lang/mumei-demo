# Inventory API

A small warehouse service for item records, reservations, releases, restocks,
reports, and search.

Default port: 8331

## Build and start

```bash
go build -o bin/inventory-api .
PORT=8331 ./bin/inventory-api
```

The server listens on loopback. Set `PORT` to use another local port.

## Endpoints

- `POST /items` creates an item from JSON with `sku`, `name`, `stock`,
  `locations`, and an optional `supplier` object.
- `POST /reserve` and `POST /release` accept `sku` and `qty`.
- `POST /restock` accepts `sku`, `packs`, and `perPack`.
- `GET /items/{sku}` returns one item.
- `GET /report?limit=N` returns inventory rows.
- `GET /search?q=term` searches item names.
- `POST /admin/reset` clears the store when sent with the configured request
  header.

## Scripts

`./run.sh` builds the service, starts it locally, and makes a few sample
requests. `./repro.sh` exercises the documented request flows against a local
server and prints one result line per case.
