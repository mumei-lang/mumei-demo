# py-04-doc-vault

A token-gated document store. Users upload documents with a per-user
`X-Api-Key` header, read them back by id, and can mint share tokens so that
anyone holding a token can read the document until it expires. Each api key
has a 64 KiB storage quota. Uploads are staged to a temp file before being
promoted into the document directory.

Default port: 8313

## Running

```bash
./run.sh                 # starts the server, exercises the happy path, exits 0
./repro.sh               # demonstrates every documented defect, exits 0 when all reproduce
```

Or start it manually:

```bash
DATA_DIR=$(mktemp -d) PORT=8313 python3 app.py
```

Uploaded documents and staging files live under `DATA_DIR` (default `./data`).

## API

- `POST /upload` — JSON body `{"title": "...", "body": "<base64>", "meta": {"format": "text" | "object"}}`.
  `object` payloads are deserialized on import. Returns `{"id": ...}`.
- `GET /doc?id=<id>&token=<token>` — returns the document body; the owner's
  api key or a valid share token is required.
- `POST /share` — JSON body `{"id": "<doc id>", "ttl_seconds": 3600}` (owner
  only). Returns `{"token", "created_at", "expires_at"}`.
- `GET /fetch?url=<url>` — downloads a document from a URL and stores it.
- `POST /admin/purge` — requires the `X-Admin-Key` header; deletes all
  documents and resets usage.
- `GET /go?next=<url>` — redirect helper used after login.
- `GET /docs.html` — HTML listing of document titles.
- `GET /quota` — storage used and remaining for the caller's api key.
- `GET /health` — service status.
