/**
 * HTTP API for the task board.
 *
 *   POST  /tasks            create a task (owner taken from X-User)
 *   PATCH /tasks/:id        update title/description/priority (owner only)
 *   POST  /tasks/:id/move   move a task to another column
 *   GET   /board            column summary
 *   GET   /search?q=        HTML fragment of matching tasks
 */
import { createServer } from "node:http";
import type { IncomingMessage, ServerResponse } from "node:http";
import {
  COLUMNS,
  NEXT_STATUSES,
  TransitionError,
  ValidationError,
  applyPatch,
  isStatus,
  moveTask,
  newTask,
  paginate,
  renderResults,
  searchTasks,
  summarizeBoard,
} from "./board.ts";
import type { Task } from "./board.ts";

const HOST = "127.0.0.1";
const PORT = Number(process.env.PORT ?? 8321);

const tasks: Task[] = [];
let nextId = 1;

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

async function readJson(req: IncomingMessage): Promise<Record<string, unknown>> {
  const text = await readBody(req);
  if (text.trim() === "") return {};
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new ValidationError("request body is not valid JSON");
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ValidationError("expected a JSON object");
  }
  return value as Record<string, unknown>;
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function sendError(res: ServerResponse, err: unknown): void {
  if (err instanceof ValidationError) return sendJson(res, 400, { error: err.message });
  if (err instanceof TransitionError) return sendJson(res, 409, { error: err.message });
  const e = err as Error;
  console.error(e);
  sendJson(res, 500, { error: e.message, stack: e.stack });
}

function currentUser(req: IncomingMessage): string | null {
  const user = req.headers["x-user"];
  return typeof user === "string" && user !== "" ? user : null;
}

function withNext(task: Task): Task & { next: string[] } {
  return { ...task, next: NEXT_STATUSES[task.status] ?? [] };
}

async function handleCreate(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const user = currentUser(req);
  if (!user) return sendJson(res, 401, { error: "X-User header required" });
  const body = await readJson(req);
  const task = newTask(nextId++, body, user);
  tasks.push(task);
  sendJson(res, 201, withNext(task));
}

async function handlePatch(req: IncomingMessage, res: ServerResponse, id: number): Promise<void> {
  const user = currentUser(req);
  if (!user) return sendJson(res, 401, { error: "X-User header required" });
  const task = tasks.find((t) => t.id === id);
  if (!task) return sendJson(res, 404, { error: "task not found" });
  if (task.ownerId !== user) return sendJson(res, 403, { error: "only the owner can edit a task" });
  const body = await readJson(req);
  const updated = applyPatch(task, body);
  tasks[tasks.indexOf(task)] = updated;
  sendJson(res, 200, withNext(updated));
}

async function handleMove(req: IncomingMessage, res: ServerResponse, id: number): Promise<void> {
  const user = currentUser(req);
  if (!user) return sendJson(res, 401, { error: "X-User header required" });
  const body = await readJson(req);
  if (!isStatus(body.to)) {
    throw new ValidationError(`to must be one of ${COLUMNS.join(", ")}`);
  }
  const task = moveTask(tasks, id, body.to);
  sendJson(res, 200, withNext(task));
}

function handleSearch(res: ServerResponse, url: URL): void {
  const q = url.searchParams.get("q") ?? "";
  const page = Number(url.searchParams.get("page") ?? "1");
  const size = Number(url.searchParams.get("size") ?? "20");
  const results = paginate(searchTasks(tasks, q), page, size);
  res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  res.end(renderResults(results));
}

async function route(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const url = new URL(req.url ?? "/", `http://${HOST}`);
  const parts = url.pathname.split("/").filter(Boolean);
  const method = req.method ?? "GET";

  if (method === "GET" && url.pathname === "/health") return sendJson(res, 200, { ok: true });
  if (method === "GET" && url.pathname === "/board") return sendJson(res, 200, summarizeBoard(tasks));
  if (method === "GET" && url.pathname === "/search") return handleSearch(res, url);
  if (method === "POST" && url.pathname === "/tasks") return handleCreate(req, res);
  if (parts[0] === "tasks" && parts.length >= 2) {
    const id = Number(parts[1]);
    if (!Number.isInteger(id)) return sendJson(res, 400, { error: "invalid task id" });
    if (method === "PATCH" && parts.length === 2) return handlePatch(req, res, id);
    if (method === "POST" && parts.length === 3 && parts[2] === "move") return handleMove(req, res, id);
  }
  sendJson(res, 404, { error: "not found" });
}

createServer((req, res) => {
  route(req, res).catch((err) => sendError(res, err));
}).listen(PORT, HOST, () => {
  console.log(`task board listening on http://${HOST}:${PORT}`);
});
