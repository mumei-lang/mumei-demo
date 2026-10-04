/**
 * URL shortener HTTP API.
 *
 *   POST /shorten        {"url", "alias"?, "ttlSeconds"?, "preview"?}
 *   GET  /r/:code        302 redirect to the target
 *   GET  /stats/:code    click statistics
 *   POST /admin/delete   {"code"} (requires X-Admin)
 */
import { createServer } from "node:http";
import type { IncomingMessage, ServerResponse } from "node:http";
import { mkdirSync } from "node:fs";
import { appendFile } from "node:fs/promises";
import { dirname } from "node:path";
import { ValidationError, createLink, linkStats, nowSeconds, resolveLink } from "./links.ts";
import type { Link } from "./links.ts";

const HOST = "127.0.0.1";
const PORT = Number(process.env.PORT ?? 8322);
const CLICK_LOG = process.env.CLICK_LOG ?? "out/clicks.log";
const ADMIN_TOKEN = "sl-admin-7f3c9e21";
const MAX_BODY = 64 * 1024;

const links = new Map<string, Link>();

interface Preview {
  status: number;
  title: string | null;
  snippet: string;
}

function readJson(req: IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_BODY) {
        reject(new ValidationError("request body too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      const text = Buffer.concat(chunks).toString("utf8");
      try {
        const value = text.trim() === "" ? {} : JSON.parse(text);
        if (typeof value !== "object" || value === null || Array.isArray(value)) {
          reject(new ValidationError("expected a JSON object"));
          return;
        }
        resolve(value as Record<string, unknown>);
      } catch {
        reject(new ValidationError("request body is not valid JSON"));
      }
    });
    req.on("error", reject);
  });
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

/** Fetch the target once so the client can show a title next to the short link. */
async function fetchPreview(target: string): Promise<Preview> {
  const res = await fetch(target, { signal: AbortSignal.timeout(3000) });
  const text = await res.text();
  const match = /<title>([^<]*)<\/title>/i.exec(text);
  return { status: res.status, title: match ? match[1].trim() : null, snippet: text.slice(0, 200) };
}

async function recordClick(link: Link, req: IncomingMessage): Promise<void> {
  const clicks = link.clicks;
  const referer = req.headers.referer ?? "-";
  await appendFile(CLICK_LOG, `${new Date().toISOString()} ${link.code} ${referer}\n`);
  link.clicks = clicks + 1;
}

async function handleShorten(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const body = await readJson(req);
  const ttl = typeof body.ttlSeconds === "number" ? body.ttlSeconds : undefined;
  const link = createLink(links, body.url, body.alias, ttl);
  const preview = body.preview === true ? await fetchPreview(link.target).catch(() => null) : undefined;
  sendJson(res, 201, { code: link.code, shortUrl: `http://${HOST}:${PORT}/r/${link.code}`, target: link.target, preview });
}

async function handleRedirect(req: IncomingMessage, res: ServerResponse, code: string): Promise<void> {
  const link = resolveLink(links, code, nowSeconds());
  if (!link) return sendJson(res, 404, { error: "unknown or expired link" });
  await recordClick(link, req);
  res.writeHead(302, { location: link.target, "content-type": "text/plain; charset=utf-8" });
  res.end(`Redirecting to ${link.target}\n`);
}

function handleStats(res: ServerResponse, code: string): void {
  sendJson(res, 200, linkStats(links, code, nowSeconds()));
}

async function handleAdminDelete(req: IncomingMessage, res: ServerResponse): Promise<void> {
  if (req.headers["x-admin"] !== ADMIN_TOKEN) return sendJson(res, 403, { error: "admin only" });
  const body = await readJson(req);
  const code = String(body.code ?? "");
  const deleted = links.delete(code);
  sendJson(res, deleted ? 200 : 404, { code, deleted });
}

async function route(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const url = new URL(req.url ?? "/", `http://${HOST}`);
  const method = req.method ?? "GET";
  const [section, code] = url.pathname.split("/").filter(Boolean);

  if (method === "GET" && url.pathname === "/health") return sendJson(res, 200, { ok: true, links: links.size });
  if (method === "POST" && url.pathname === "/shorten") return handleShorten(req, res);
  if (method === "POST" && url.pathname === "/admin/delete") return handleAdminDelete(req, res);
  if (method === "GET" && section === "r" && code) return handleRedirect(req, res, code);
  if (method === "GET" && section === "stats" && code) return handleStats(res, code);
  sendJson(res, 404, { error: "not found" });
}

mkdirSync(dirname(CLICK_LOG), { recursive: true });

createServer((req, res) => {
  route(req, res).catch((err) => {
    if (err instanceof ValidationError) return sendJson(res, 400, { error: err.message });
    console.error(err);
    sendJson(res, 500, { error: "internal error" });
  });
}).listen(PORT, HOST, () => {
  console.log(`url shortener listening on http://${HOST}:${PORT}`);
});
