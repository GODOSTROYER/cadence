/**
 * Null-tolerant readers for `eval_summary.json`. The eval module writes `null` (never NaN) for any
 * statistic that is undefined on the data — Spearman on constant ratings, a mean with no scores, a
 * CI on an empty set — and whole blocks (`reply_quality`, `judge_agreement`) can be null before the
 * judge or the human ratings have run. `src/lib/types.ts` types the happy path; these helpers make
 * the pages hold up on the rest.
 */
import type { CI95 } from "@/lib/types";

export type Maybe<T> = T | null | undefined;

export function isNum(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

/** Format a number, or the em dash when it is missing. */
export function fmtMaybe(x: Maybe<number>, format: (v: number) => string): string {
  return isNum(x) ? format(x) : "—";
}

/** A `[low, high]` pair of finite numbers, else undefined. */
export function ciOf(x: unknown): CI95 | undefined {
  if (!Array.isArray(x) || x.length !== 2) return undefined;
  const [lo, hi] = x as [unknown, unknown];
  return isNum(lo) && isNum(hi) ? [lo, hi] : undefined;
}

/** Read an optional additive field off a summary block without widening the shared types. */
export function extra<T>(block: unknown, key: string): T | undefined {
  if (!block || typeof block !== "object") return undefined;
  return (block as Record<string, T | undefined>)[key];
}
