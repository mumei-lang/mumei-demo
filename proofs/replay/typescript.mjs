// Native replay driver for the TypeScript specimens (node strips the types).
// Usage: node typescript.mjs <specimen tree>  (JSON lines {"case", "values"} on stdin)
// Prints {"case", "violates", "observed"} per input; see python.py for the conventions.
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";
import path from "node:path";

const tree = process.argv[2];
const load = (file) => import(pathToFileURL(path.join(tree, file)).href);
const COLUMNS = ["todo", "in_progress", "review", "done", "archived"];
const ALLOWED = new Set(["0-1", "1-2", "1-0", "2-3", "2-1", "3-4"]);
const task = (id, status) => ({ id, title: `t${id}`, status, priority: 3, createdAt: "", updatedAt: "" });
const thrown = (fn) => { try { return [true, fn()]; } catch (e) { return [false, e]; } };

async function check(id, v) {
  if (id.startsWith("TS01")) {
    const b = await load("board.ts");
    if (id === "TS01-D01") {
      const r = b.canMove(COLUMNS[v.from], COLUMNS[v.to]);
      return [r !== ALLOWED.has(`${v.from}-${v.to}`), `canMove(${COLUMNS[v.from]}, ${COLUMNS[v.to]}) -> ${r}`];
    }
    if (id === "TS01-D03") {
      const tasks = v.found ? [task(1, "todo")] : [];
      const [ok, r] = thrown(() => b.moveTask(tasks, 1, v.can_move ? "in_progress" : "done"));
      const clean = ok || r?.name !== "TypeError";
      return [!v.found && (ok || !clean), ok ? "moved" : `threw ${r?.name}: ${r?.message}`];
    }
    if (id === "TS01-D04") {
      const tasks = Array.from({ length: v.active }, (_, i) => task(i, i < v.done ? "done" : "todo"));
      const r = b.completionPercent(tasks);
      const bad = !Number.isFinite(r) || r < 0 || r > 100 || (v.active === 0 && r !== 0);
      return [bad, `completionPercent -> ${r}`];
    }
    if (id === "TS01-D07") {
      const raw = v.missing ? undefined : v.numeric ? v.value : "not-a-number";
      const [ok, r] = thrown(() => b.parsePriority(raw));
      return [ok && !(Number.isInteger(r) && r >= 1 && r <= 5), `parsePriority(${JSON.stringify(raw)}) -> ${ok ? r : r?.message}`];
    }
    if (id === "TS01-D12") {
      const r = b.paginate(Array.from({ length: v.n }, (_, i) => i), v.page, v.size);
      return [v.page * v.size <= v.n && r.length !== v.size, `paginate -> ${r.length} items`];
    }
  }
  if (id.startsWith("TS02")) {
    const l = await load("links.ts");
    if (id === "TS02-D05") {
      const r = l.clicksPerDay(v.clicks, v.created_at, v.now);
      return [!Number.isFinite(r) || r < 0 || r > v.clicks, `clicksPerDay -> ${r}`];
    }
    if (id === "TS02-D08") {
      const alias = "a".repeat(v.n);
      const r = l.normalizeAlias(alias);
      return [r.length !== v.n, `normalizeAlias(${alias}) -> ${r}`];
    }
    if (id === "TS02-D11") {
      const links = new Map();
      if (v.found) links.set("abc", { code: "abc", target: "https://example.com", clicks: v.clicks, createdAt: 0, expiresAt: null });
      const [ok, r] = thrown(() => l.linkStats(links, "abc", 86400));
      const notFound = !ok && r?.name !== "TypeError" && /not ?found|unknown/i.test(`${r?.name} ${r?.message}`);
      return [!v.found && !notFound, ok ? "returned stats" : `threw ${r?.name}: ${r?.message}`];
    }
  }
  if (id.startsWith("TS03")) {
    const p = await load("pricing.ts");
    if (id === "TS03-D03") {
      const r = p.effectiveTaxRate(v.tax, v.net);
      return [v.net === 0 && r !== 0, `effectiveTaxRate -> ${r}`];
    }
    if (id === "TS03-D04") {
      const [ok, r] = thrown(() => p.parseItem({ sku: "a", unitPrice: 1, quantity: v.quantity }));
      return [ok && !(r.quantity > 0), ok ? `accepted quantity ${r.quantity}` : `threw ${r?.message}`];
    }
    if (id === "TS03-D05") {
      const items = Array.from({ length: v.n }, (_, i) => ({ sku: `s${i}`, description: "", unitPrice: 1, quantity: 1 }));
      const [ok, r] = thrown(() => p.pageFooters(items, v.per_page));
      return [!ok || r.some((f) => f.includes("undefined")), ok ? JSON.stringify(r) : `threw ${r?.name}: ${r?.message}`];
    }
    if (id === "TS03-D09") {
      const [ok, r] = thrown(() => p.applyDiscount(v.amount, v.percent));
      return [ok && !(r >= 0 && r <= v.amount), ok ? `applyDiscount -> ${r}` : `threw ${r?.message}`];
    }
  }
  throw new Error(`unknown case ${id}`);
}

for await (const line of createInterface({ input: process.stdin })) {
  if (!line.trim()) continue;
  const req = JSON.parse(line);
  let violates, observed;
  try {
    [violates, observed] = await check(req.case, req.values);
  } catch (e) {
    if (String(e?.message).startsWith("unknown case")) throw e;
    [violates, observed] = [true, `raised ${e?.name}: ${e?.message}`];
  }
  console.log(JSON.stringify({ case: req.case, violates: Boolean(violates), observed: String(observed).slice(0, 300) }));
}
