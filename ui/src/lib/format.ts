/** Number, interval, date and duration formatting shared by every page. */
import type { CI95 } from "./types";

const NUM = new Intl.NumberFormat("en-US");

/** `0.8123` → `"81%"`; `digits` controls decimals. */
export function pct(x: number, digits = 0): string {
  return `${(x * 100).toFixed(digits)}%`;
}

/** Fixed-point number, trimming a trailing ".0" when `trim` is set. */
export function fixed(x: number, digits = 2, trim = false): string {
  const s = x.toFixed(digits);
  return trim ? s.replace(/\.?0+$/, "") : s;
}

/** Thousands-separated integer. */
export function int(x: number): string {
  return NUM.format(Math.round(x));
}

/** Compact large numbers: 1_384_220 → "1.38M", 26_068 → "26.1k". */
export function compact(x: number): string {
  if (Math.abs(x) >= 1_000_000) return `${(x / 1_000_000).toFixed(2)}M`;
  if (Math.abs(x) >= 10_000) return `${(x / 1_000).toFixed(1)}k`;
  return NUM.format(x);
}

/** `[0.72, 0.85]` → `"0.72 – 0.85"` (en dash, thin spaces). */
export function ci(interval: CI95, digits = 2): string {
  return `${interval[0].toFixed(digits)} – ${interval[1].toFixed(digits)}`;
}

/** `[0.72, 0.85]` → `"72 – 85%"`. */
export function ciPct(interval: CI95, digits = 0): string {
  return `${(interval[0] * 100).toFixed(digits)} – ${(interval[1] * 100).toFixed(digits)}%`;
}

/** Half-width of an interval in the same units. */
export function ciHalfWidth(interval: CI95): number {
  return (interval[1] - interval[0]) / 2;
}

/** Milliseconds → "12 ms" / "1.4 s" / "2 min". */
export function ms(n: number): string {
  if (n < 1000) return `${Math.round(n)} ms`;
  if (n < 60_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)} s`;
  return `${Math.round(n / 60_000)} min`;
}

/** Signed delta with a sign prefix, e.g. "+0.12" / "−0.05". */
export function delta(x: number, digits = 2): string {
  const s = Math.abs(x).toFixed(digits);
  if (x > 0) return `+${s}`;
  if (x < 0) return `−${s}`;
  return s;
}

/** Signed delta in percentage points: "+12 pts". */
export function deltaPts(x: number, digits = 0): string {
  const v = x * 100;
  const s = Math.abs(v).toFixed(digits);
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${s} pts`;
}

const DATE = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
const DATE_TIME = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : DATE.format(d);
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : `${DATE_TIME.format(d)} UTC`;
}

/**
 * Relative date in the style of a tweet timestamp: "3h", "2d", or the calendar date when older
 * than a week or when `now` is far from the event (the corpus is from 2017).
 */
export function relativeDate(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diff = now.getTime() - d.getTime();
  const sec = Math.round(diff / 1000);
  if (sec < 60) return "now";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m`;
  const hrs = Math.round(min / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.round(hrs / 24);
  if (days < 7) return `${days}d`;
  return DATE.format(d);
}

/** Simple pluraliser: plural(1, "example") → "1 example". */
export function plural(n: number, singular: string, pluralForm = `${singular}s`): string {
  return `${int(n)} ${n === 1 ? singular : pluralForm}`;
}

/** Truncate to `n` characters with an ellipsis. */
export function truncate(text: string, n = 120): string {
  if (text.length <= n) return text;
  return `${text.slice(0, Math.max(0, n - 1)).trimEnd()}…`;
}

/** Title-case a snake_case id as a last-resort label. */
export function titleCase(id: string): string {
  return id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
