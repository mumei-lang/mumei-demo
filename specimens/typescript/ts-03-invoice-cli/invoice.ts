/**
 * Invoice calculator.
 *
 * Usage:
 *   node invoice.ts --items items.json [--tax 10] [--discount 5]
 *                   [--customer NAME] [--date YYYY-MM-DD] [--out invoice.txt] [--json]
 *
 * Prints the invoice to stdout, or writes it to --out and checks the written file.
 */
import { execSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { computeTotals, effectiveTaxRate, lineTotal, money, pageFooters, parseItems, taxAmount } from "./pricing.ts";
import type { LineItem, Totals } from "./pricing.ts";

const LINES_PER_PAGE = 10;

interface Options {
  items: string;
  tax: number;
  discount: number;
  customer: string;
  date: string;
  out: string | null;
  json: boolean;
}

function parseArgs(argv: string[]): Options {
  const opts: Options = {
    items: "items.json",
    tax: 0,
    discount: 0,
    customer: "ACME Corp",
    date: new Date().toISOString().slice(0, 10),
    out: null,
    json: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const value = (): string => {
      const v = argv[++i];
      if (v === undefined) throw new Error(`${arg} needs a value`);
      return v;
    };
    if (arg === "--items") opts.items = value();
    else if (arg === "--tax") opts.tax = Number(value());
    else if (arg === "--discount") opts.discount = Number(value());
    else if (arg === "--customer") opts.customer = value();
    else if (arg === "--date") opts.date = value();
    else if (arg === "--out") opts.out = value();
    else if (arg === "--json") opts.json = true;
    else throw new Error(`unknown option ${arg}`);
  }
  if (!Number.isFinite(opts.tax) || opts.tax < 0) throw new Error("--tax must be a non-negative number");
  if (!Number.isFinite(opts.discount)) throw new Error("--discount must be a number");
  return opts;
}

/** Stable invoice number for a customer and invoice date. */
function invoiceId(customer: string, date: string): string {
  return "INV-" + createHash("md5").update(`${customer}:${date}`).digest("hex").slice(0, 12).toUpperCase();
}

function row(label: string, amount: string): string {
  return `${label}:`.padEnd(52) + amount.padStart(14);
}

function renderInvoice(id: string, opts: Options, items: LineItem[], totals: Totals): string {
  const lines: string[] = [];
  lines.push(`Invoice ${id}`, `Customer: ${opts.customer}`, `Date: ${opts.date}`, "");
  for (const item of items) {
    const desc = `${item.sku} ${item.description}`.padEnd(36);
    const qty = String(item.quantity).padStart(4);
    lines.push(`${desc}${qty} x ${money(item.unitPrice).padStart(9)} = ${money(lineTotal(item)).padStart(10)}`);
  }
  lines.push("");
  lines.push(row("Subtotal", money(totals.subtotal)));
  lines.push(row(`Discount (${opts.discount}%)`, "-" + money(totals.discount)));
  lines.push(row(`Tax (${opts.tax}%)`, money(taxAmount(totals.subtotal, opts.tax))));
  lines.push(row("Total", money(totals.total)));
  lines.push(`Effective tax rate: ${effectiveTaxRate(totals.tax, totals.net).toFixed(2)}%`);
  const footers = pageFooters(items, LINES_PER_PAGE);
  if (footers.length > 0) lines.push("", ...footers);
  return lines.join("\n") + "\n";
}

function writeInvoice(path: string, text: string): void {
  writeFileSync(path, text);
  const written = execSync("cat " + path, { encoding: "utf8" });
  if (written !== text) throw new Error(`verification of ${path} failed`);
}

function main(): void {
  const opts = parseArgs(process.argv.slice(2));
  const entries = JSON.parse(readFileSync(opts.items, "utf8"));
  if (!Array.isArray(entries)) throw new Error(`${opts.items} must contain a JSON array of items`);
  const items = parseItems(entries);
  const totals = computeTotals(items, opts.tax, opts.discount);
  const id = invoiceId(opts.customer, opts.date);
  const text = opts.json
    ? JSON.stringify({ id, customer: opts.customer, date: opts.date, items, ...totals }, null, 2) + "\n"
    : renderInvoice(id, opts, items, totals);
  if (opts.out) {
    writeInvoice(opts.out, text);
    console.log(`wrote ${opts.out} (invoice ${id})`);
  } else {
    process.stdout.write(text);
  }
}

try {
  main();
} catch (err) {
  console.error(`invoice: ${(err as Error).message}`);
  process.exit(1);
}
