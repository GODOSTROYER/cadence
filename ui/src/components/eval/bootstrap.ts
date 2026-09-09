/**
 * Per-class F1 with a seeded bootstrap CI, mirroring `cadence.eval.bootstrap` (percentile method,
 * 1000 resamples, seed 42). Used only when the export lacks `ci95.per_class_f1` for a system and the
 * exported golden rows provably reproduce that system's point estimates.
 */
import type { CI95, MergedGoldenExample, PerClassMetrics, SystemId } from "@/lib/types";

export const BOOTSTRAP_RESAMPLES = 1000;
export const BOOTSTRAP_SEED = 42;

/** Small, fast, deterministic PRNG (mulberry32) so whiskers are identical on every render. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** F1 per label in `labels` order; a label with no gold and no predictions scores 0 (sklearn's zero_division=0). */
export function perClassF1(gold: readonly string[], pred: readonly string[], labels: readonly string[]): number[] {
  const index = new Map(labels.map((l, i) => [l, i]));
  const tp = new Array<number>(labels.length).fill(0);
  const fp = new Array<number>(labels.length).fill(0);
  const fn = new Array<number>(labels.length).fill(0);
  for (let i = 0; i < gold.length; i++) {
    const g = index.get(gold[i] ?? "");
    const p = index.get(pred[i] ?? "");
    if (g !== undefined && g === p) tp[g] = (tp[g] ?? 0) + 1;
    else {
      if (p !== undefined) fp[p] = (fp[p] ?? 0) + 1;
      if (g !== undefined) fn[g] = (fn[g] ?? 0) + 1;
    }
  }
  return labels.map((_, k) => {
    const denominator = 2 * (tp[k] ?? 0) + (fp[k] ?? 0) + (fn[k] ?? 0);
    return denominator === 0 ? 0 : (2 * (tp[k] ?? 0)) / denominator;
  });
}

/** Linear-interpolated quantile of an ascending array (numpy's default). */
function quantile(sorted: readonly number[], q: number): number {
  if (sorted.length === 0) return 0;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  const a = sorted[lo] ?? 0;
  const b = sorted[hi] ?? a;
  return a + (b - a) * (pos - lo);
}

/** Percentile bootstrap 95% CI of per-class F1, one interval per label. */
export function bootstrapPerClassF1(
  gold: readonly string[],
  pred: readonly string[],
  labels: readonly string[],
  n = BOOTSTRAP_RESAMPLES,
  seed = BOOTSTRAP_SEED,
): CI95[] {
  const rng = mulberry32(seed);
  const m = gold.length;
  const samples: number[][] = labels.map(() => []);
  const g = new Array<string>(m);
  const p = new Array<string>(m);
  for (let b = 0; b < n; b++) {
    for (let i = 0; i < m; i++) {
      const j = Math.floor(rng() * m);
      g[i] = gold[j] ?? "";
      p[i] = pred[j] ?? "";
    }
    perClassF1(g, p, labels).forEach((v, k) => samples[k]?.push(v));
  }
  return samples.map((s) => {
    s.sort((a, b) => a - b);
    return [quantile(s, 0.025), quantile(s, 0.975)];
  });
}

/**
 * Per-class F1 CIs computed from the exported test rows of `system`, or null when those rows do not
 * reproduce the summary's own per-class F1 (a stale or partial export) — a CI from different data
 * than the point estimate would mislead, so none is shown instead.
 */
export function perClassCiFromRows(
  rows: readonly MergedGoldenExample[],
  system: SystemId,
  labels: readonly string[],
  summary: Record<string, PerClassMetrics>,
  tolerance = 5e-3,
): Record<string, CI95> | null {
  const test = rows.filter((r) => r.split === "test" && r.predictions[system]);
  if (test.length === 0) return null;
  const gold = test.map((r) => r.gold.intent);
  const pred = test.map((r) => r.predictions[system]?.intent ?? "");
  const point = perClassF1(gold, pred, labels);
  const consistent = labels.every((label, k) => {
    const reported = summary[label];
    if (!reported) return true;
    if (reported.support !== gold.filter((g) => g === label).length) return false;
    return Math.abs((point[k] ?? 0) - reported.f1) <= tolerance;
  });
  if (!consistent) return null;
  const cis = bootstrapPerClassF1(gold, pred, labels);
  return Object.fromEntries(labels.map((label, k) => [label, cis[k] ?? [0, 0]]));
}
