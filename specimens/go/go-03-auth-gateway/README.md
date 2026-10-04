# Auth Gateway

A local gateway for seeded accounts, profile lookup, outbound HTTP requests,
and signing configuration rotation.

Default port: 8332

## Build and start

```bash
go build -o bin/auth-gateway .
PORT=8332 ./bin/auth-gateway
```

The server listens on loopback. Set `PORT` to use another local port.

## Endpoints

- `POST /login` accepts `user` and `password`; an optional `next` query value
  selects a redirect destination.
- `GET /profile?user=alice` returns a profile for an authenticated bearer
  token.
- `GET /proxy?target=http://127.0.0.1:9000/` forwards an authenticated request.
- `POST /rotate` changes the active signing configuration for an administrator.
- `GET /healthz` reports service status.

The seeded accounts are `alice`, `bob`, and `admin`.

## Scripts

`./run.sh` builds the gateway, starts it locally, and makes sample requests.
`./repro.sh` builds the gateway and runs local request examples, including a
temporary loopback service.
