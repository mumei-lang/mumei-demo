# rs-02-kv-server

A minimal HTTP key-value server on `std::net::TcpListener`, one thread per
connection. Values live in a `Mutex<HashMap<String,String>>` and per-key
counters in a `Mutex<HashMap<String,i32>>`.

Default port: 8341

The port is read from `PORT`; the data directory (for snapshots) is read from
`KV_DATA_DIR`, default `./data`. The server binds `127.0.0.1` only.

## Build & run

```bash
cargo build --release
PORT=8341 target/release/kv-server
```

## Endpoints

- `PUT /kv/{key}` — body becomes the value
- `GET /kv/{key}`
- `POST /incr/{key}?delta=N` — add to an integer counter (default 1)
- `GET /keys?prefix=` — list keys matching a byte prefix
- `POST /snapshot?path=` — dump the store into the data dir
- `GET /ui?key=` — small HTML echo page
- `POST /admin/flush?token=` — clear both maps (operator token)
