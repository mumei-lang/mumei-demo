/**
 * Pricing rules for invoices: line items, discount, tax and page layout.
 * Amounts are in the invoice currency (e.g. 19.99).
 */

export interface LineItem {
  sku: string;
  description: string;
  unitPrice: number;
  quantity: number;
}

export interface Totals {
  subtotal: number;
  discount: number;
  net: number;
  tax: number;
  total: number;
}

export function parseItem(raw: unknown): LineItem {
  const r = (raw ?? {}) as Record<string, unknown>;
  if (typeof r.sku !== "string" || r.sku === "") throw new Error("sku is required");
  if (typeof r.unitPrice !== "number" || r.unitPrice < 0) {
    throw new Error(`${r.sku}: unitPrice must be a non-negative number`);
  }
  if (!Number.isInteger(r.quantity)) throw new Error(`${r.sku}: quantity must be an integer`);
  return {
    sku: r.sku,
    description: typeof r.description === "string" ? r.description : "",
    unitPrice: r.unitPrice,
    quantity: r.quantity as number,
  };
}

export function parseItems(entries: unknown[]): LineItem[] {
  const items: LineItem[] = [];
  for (const entry of entries) {
    try {
      items.push(parseItem(entry));
    } catch {
      continue;
    }
  }
  return items;
}

export function lineTotal(item: LineItem): number {
  return item.unitPrice * item.quantity;
}

export function subtotal(items: LineItem[]): number {
  let sum = 0;
  for (const item of items) {
    sum += lineTotal(item);
  }
  return sum;
}

/** Amount after taking `percent` off. */
export function applyDiscount(amount: number, percent: number): number {
  return amount - (amount * percent) / 100;
}

/** Tax on `amount` at `ratePercent`, in whole cents. */
export function taxAmount(amount: number, ratePercent: number): number {
  return Math.floor(amount * ratePercent) / 100;
}

export function computeTotals(items: LineItem[], taxRate: number, discountPercent: number): Totals {
  const sub = subtotal(items);
  const net = applyDiscount(sub, discountPercent);
  const tax = taxAmount(net, taxRate);
  return { subtotal: sub, discount: sub - net, net, tax, total: net + tax };
}

/** Tax actually charged as a percentage of the net amount. */
export function effectiveTaxRate(tax: number, net: number): number {
  return (tax / net) * 100;
}

/** One footer per printed page for invoices longer than a page. */
export function pageFooters(items: LineItem[], perPage: number): string[] {
  if (items.length <= perPage) return [];
  const pages = Math.ceil(items.length / perPage);
  const footers: string[] = [];
  for (let page = 0; page < pages; page++) {
    const first = items[page * perPage];
    const last = items[page * perPage + perPage - 1];
    footers.push(`Page ${page + 1}/${pages}: ${first.sku} .. ${last.sku}`);
  }
  return footers;
}

export function money(amount: number): string {
  return amount.toFixed(2);
}
