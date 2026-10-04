/**
 * Link model for the URL shortener: code generation, validation, lookup and
 * statistics. The store is a plain Map owned by the HTTP layer.
 */

export interface Link {
  code: string;
  target: string;
  /** Unix time in seconds. */
  createdAt: number;
  expiresAt: number | null;
  clicks: number;
}

export interface LinkStats {
  code: string;
  target: string;
  clicks: number;
  createdAt: string;
  expiresAt: string | null;
  clicksPerDay: number;
}

export const CODE_LENGTH = 7;
export const MAX_ALIAS_LENGTH = 8;
const SECONDS_PER_DAY = 86400;

export class ValidationError extends Error {}

export function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

/** Random base36 code for links created without an alias. */
export function generateCode(): string {
  return Math.random().toString(36).slice(2, 2 + CODE_LENGTH);
}

export function validateTarget(target: unknown): string {
  if (typeof target !== "string" || target.length === 0 || target.length > 2048) {
    throw new ValidationError("url must be a non-empty string of at most 2048 characters");
  }
  try {
    new URL(target);
  } catch {
    throw new ValidationError("url must be an absolute URL");
  }
  return target;
}

export function validateAlias(alias: unknown): string {
  if (typeof alias !== "string" || !/^[A-Za-z0-9_-]+$/.test(alias)) {
    throw new ValidationError("alias may contain letters, digits, '-' and '_'");
  }
  if (alias.length > MAX_ALIAS_LENGTH) {
    throw new ValidationError(`alias must be at most ${MAX_ALIAS_LENGTH} characters`);
  }
  return alias;
}

/** Aliases are case-insensitive; store them in canonical form. */
export function normalizeAlias(alias: string): string {
  const canonical = alias.toLowerCase();
  return canonical.slice(0, CODE_LENGTH);
}

export function createLink(
  links: Map<string, Link>,
  target: unknown,
  alias: unknown,
  ttlSeconds: number | undefined,
): Link {
  const url = validateTarget(target);
  const code = alias === undefined ? generateCode() : normalizeAlias(validateAlias(alias));
  const link: Link = {
    code,
    target: url,
    createdAt: nowSeconds(),
    expiresAt: ttlSeconds ? Date.now() + ttlSeconds * 1000 : null,
    clicks: 0,
  };
  links.set(code, link);
  return link;
}

export function isExpired(link: Link, now: number): boolean {
  return link.expiresAt !== null && link.expiresAt < now;
}

/** Look up a live link by code; returns null when unknown or expired. */
export function resolveLink(links: Map<string, Link>, code: string, now: number): Link | null {
  const link = links.get(code);
  if (!link || isExpired(link, now)) return null;
  return link;
}

/** Average clicks per full day since creation, rounded to two decimals. */
export function clicksPerDay(clicks: number, createdAt: number, now: number): number {
  const days = Math.floor((now - createdAt) / SECONDS_PER_DAY);
  return Math.round((clicks / days) * 100) / 100;
}

export function linkStats(links: Map<string, Link>, code: string, now: number): LinkStats {
  const link = links.get(code) as Link;
  return {
    code: link.code,
    target: link.target,
    clicks: link.clicks,
    createdAt: new Date(link.createdAt * 1000).toISOString(),
    expiresAt: link.expiresAt === null ? null : new Date(link.expiresAt).toISOString(),
    clicksPerDay: clicksPerDay(link.clicks, link.createdAt, now),
  };
}
