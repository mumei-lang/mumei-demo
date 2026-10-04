# ts-02-url-shortener

A URL shortener with custom aliases, optional expiry, click statistics and an
optional link preview, written in TypeScript on Node's standard library.
Clicks are appended to `out/clicks.log` (override with `CLICK_LOG`).

Default port: 8322

## Start manually

```bash
node server.ts                                   # Node 23.6+
node --experimental-strip-types server.ts        # Node 22.6 - 23.5
PORT=9000 node server.ts
```

The server listens on `127.0.0.1` only. Links are kept in memory.

## Endpoints

| Method | Path | Body | Description |
| --- | --- | --- | --- |
| `POST` | `/shorten` | `{"url", "alias"?, "ttlSeconds"?, "preview"?}` | Create a short link. Aliases are case-insensitive, up to 8 characters of `[A-Za-z0-9_-]`. Without an alias a random 7-character code is generated. `preview: true` adds the target page's title. |
| `GET` | `/r/:code` | | `302` redirect to the target and count the click. |
| `GET` | `/stats/:code` | | Clicks, creation/expiry time and average clicks per day. |
| `POST` | `/admin/delete` | `{"code"}` | Delete a link. Requires the `X-Admin` header. |
| `GET` | `/health` | | Liveness check and link count. |

Example:

```bash
curl -X POST localhost:8322/shorten -d '{"url":"https://nodejs.org/api/http.html","alias":"node"}'
curl -i localhost:8322/r/node
curl localhost:8322/stats/node
```

## Scripts

- `./run.sh` starts the server on `$PORT` (default 8322), creates and follows a
  few links with curl, prints the responses and stops the server.
- `./repro.sh` starts its own server and runs one check per entry in
  `DEFECTS.json`, printing `[REPRODUCED]` / `[NOT REPRODUCED]` lines; exits 0
  only when every case reproduces. Takes about five seconds.
