# ts-01-task-board

A small Kanban task board JSON API written in TypeScript on Node's standard
library. Tasks move through the columns `todo -> in_progress -> review -> done
-> archived` (review can send a task back to `in_progress`, and `in_progress`
back to `todo`). Each task response includes `next`, the columns it may move to.
Callers identify themselves with the `X-User` header; only a task's owner may
edit it.

Default port: 8321

## Start manually

```bash
node server.ts                                   # Node 23.6+
node --experimental-strip-types server.ts        # Node 22.6 - 23.5
PORT=9000 node server.ts                         # another port
```

The server listens on `127.0.0.1` only. State is kept in memory.

## Endpoints

| Method | Path | Body / query | Description |
| --- | --- | --- | --- |
| `POST` | `/tasks` | `{"title", "description"?, "priority"? (1-5)}` | Create a task owned by `X-User`. Title is required. |
| `PATCH` | `/tasks/:id` | `{"title"?, "description"?, "priority"?}` | Update a task (owner only). |
| `POST` | `/tasks/:id/move` | `{"to": "<column>"}` | Move a task to another column. |
| `GET` | `/board` | | Per-column counts and ids (oldest first), total, completion %. |
| `GET` | `/search` | `q`, `page` (1-based), `size` | HTML `<ul>` fragment of tasks matching `q`, for the board's live search box. |
| `GET` | `/health` | | Liveness check. |

Example:

```bash
curl -X POST localhost:8321/tasks -H 'X-User: alice' -H 'content-type: application/json' \
     -d '{"title":"Write release notes","priority":2}'
curl -X POST localhost:8321/tasks/1/move -H 'X-User: alice' -d '{"to":"in_progress"}'
curl localhost:8321/board
```

## Scripts

- `./run.sh` starts the server on `$PORT` (default 8321), runs a short happy-path
  session with curl, prints the responses and stops the server.
- `./repro.sh` starts its own server and runs one check per entry in
  `DEFECTS.json`, printing `[REPRODUCED]` / `[NOT REPRODUCED]` lines. It exits 0
  only when every case reproduces. Takes a few seconds.

Server logs go to `out/`.
