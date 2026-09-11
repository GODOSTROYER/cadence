import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { ConfusionMatrix } from "@/components/ConfusionMatrix";
import { DataTable, type Column } from "@/components/DataTable";
import { F1Bars, type F1Row } from "@/components/F1Bars";
import { IntentBadge } from "@/components/IntentBadge";
import { SegmentedControl } from "@/components/SegmentedControl";
import { ci as formatCi, fixed, int, pct } from "@/lib/format";
import { systemLabelFor } from "@/lib/labels";
import type { CI95, EvalSummary, IntentId, IntentSystemMetrics, MergedGoldenExample, PerClassMetrics } from "@/lib/types";

import { BOOTSTRAP_RESAMPLES, perClassCiFromRows } from "./bootstrap";
import { ciOf, extra, isNum } from "./maybe";
import { StatTile } from "./StatTile";
import { predictionSystem, resolveSystem, systemOptions } from "./systemKeys";

export interface IntentTabProps {
  summary: EvalSummary;
  /** Golden rows for cell examples and, when the export lacks them, per-class CIs. Null while unavailable. */
  golden: MergedGoldenExample[] | null;
  system: string | null;
  onSystemChange: (system: string) => void;
}

interface ClassRow extends PerClassMetrics {
  id: IntentId;
  ci?: CI95;
}

/** `ci95.per_class_f1` is an additive field the eval module writes for the agent (CONTRACT §14). */
function exportedPerClassCi(metrics: IntentSystemMetrics): Record<string, CI95> | null {
  const raw = extra<Record<string, unknown>>(metrics.ci95, "per_class_f1");
  if (!raw) return null;
  const entries = Object.entries(raw).flatMap(([label, value]) => {
    const interval = ciOf(value);
    return interval ? [[label, interval] as const] : [];
  });
  return entries.length ? Object.fromEntries(entries) : null;
}

function countCorrect(matrix: number[][]): { correct: number; total: number } {
  let correct = 0;
  let total = 0;
  matrix.forEach((row, i) => {
    row.forEach((n, j) => {
      total += n;
      if (i === j) correct += n;
    });
  });
  return { correct, total };
}

/** System switcher, headline tiles, confusion matrix, F1 bars with CI whiskers and the per-class table. */
export function IntentTab({ summary, golden, system, onSystemChange }: IntentTabProps) {
  const navigate = useNavigate();
  const block = summary.intent;
  const keys = Object.keys(block.systems);
  const key = resolveSystem(keys, system);
  const metrics = key ? block.systems[key] : undefined;
  const predSystem = key ? predictionSystem(key) : undefined;

  const testRows = useMemo(
    () => (golden && predSystem ? golden.filter((r) => r.split === "test" && r.predictions[predSystem]) : []),
    [golden, predSystem],
  );

  const examples = useMemo(() => {
    const map = new Map<string, string[]>();
    if (!predSystem) return map;
    for (const row of testRows) {
      const pred = row.predictions[predSystem]?.intent ?? "";
      const cell = `${row.gold.intent}→${pred}`;
      map.set(cell, [...(map.get(cell) ?? []), row.id]);
    }
    return map;
  }, [testRows, predSystem]);

  const perClassCi = useMemo<{ source: "export" | "rows" | null; values: Record<string, CI95> }>(() => {
    if (!metrics) return { source: null, values: {} };
    const exported = exportedPerClassCi(metrics);
    if (exported) return { source: "export", values: exported };
    if (predSystem && testRows.length) {
      const computed = perClassCiFromRows(testRows, predSystem, block.labels, metrics.per_class);
      if (computed) return { source: "rows", values: computed };
    }
    return { source: null, values: {} };
  }, [metrics, predSystem, testRows, block.labels]);

  if (!key || !metrics) {
    return <p className="text-[13px] text-muted">No intent metrics in this summary.</p>;
  }

  const { correct, total } = countCorrect(metrics.confusion.matrix);
  const rows: ClassRow[] = block.labels.map((id) => ({
    id,
    ...(metrics.per_class[id] ?? { precision: 0, recall: 0, f1: 0, support: block.support[id] ?? 0 }),
    ci: perClassCi.values[id],
  }));
  const f1Rows: F1Row[] = rows.map((r) => ({ id: r.id, f1: r.f1, support: r.support, precision: r.precision, recall: r.recall, ci: r.ci }));

  const columns: Column<ClassRow>[] = [
    { id: "intent", header: "Intent", cell: (r) => <IntentBadge id={r.id} compact size="sm" showId={false} className="whitespace-nowrap" />, sortValue: (r) => r.id },
    { id: "precision", header: "Precision", align: "right", mono: true, cell: (r) => fixed(r.precision, 3), sortValue: (r) => r.precision },
    { id: "recall", header: "Recall", align: "right", mono: true, cell: (r) => fixed(r.recall, 3), sortValue: (r) => r.recall },
    { id: "f1", header: "F1", align: "right", mono: true, cell: (r) => fixed(r.f1, 3), sortValue: (r) => r.f1 },
    ...(perClassCi.source
      ? [{ id: "ci", header: "95% CI", align: "right", mono: true, hideOnMobile: true, cell: (r: ClassRow) => (r.ci ? formatCi(r.ci) : "—"), sortValue: (r: ClassRow) => r.ci?.[0] ?? null } satisfies Column<ClassRow>]
      : []),
    { id: "support", header: "Support", align: "right", mono: true, cell: (r) => int(r.support), sortValue: (r) => r.support },
  ];

  const openCell = (gold: IntentId, pred: IntentId, count: number) => {
    if (count === 0 || !predSystem) return;
    const params = new URLSearchParams({ split: "test", system: predSystem, intent: gold, pred });
    navigate(`/golden?${params.toString()}`);
  };

  const ciNote =
    perClassCi.source === "export"
      ? `Whiskers are the exported 95% bootstrap CIs (${extra<number>(summary.meta, "n_boot") ?? BOOTSTRAP_RESAMPLES} resamples, seed 42).`
      : perClassCi.source === "rows"
        ? `Whiskers are 95% bootstrap CIs (${BOOTSTRAP_RESAMPLES} resamples, seed 42) recomputed from the ${int(testRows.length)} exported test rows, which reproduce this system's F1 exactly.`
        : "Per-class CIs are not in this export for this system, so the bars carry no whiskers.";

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl label="Intent system" options={systemOptions(keys, "intent")} value={key} onChange={onSystemChange} />
        <p className="text-[12px] text-faint">
          {systemLabelFor("intent", key)} · {int(total)} test tweets · {block.labels.length} intents
        </p>
      </div>

      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile size="md" label="accuracy" value={metrics.accuracy} format={(v) => pct(v, 1)} ci={ciOf(metrics.ci95?.accuracy)} ciFormat={(c) => `${pct(c[0], 1)} – ${pct(c[1], 1)}`} hint="Share of test tweets whose predicted intent equals the gold intent." />
        <StatTile size="md" label="macro-F1" value={metrics.macro_f1} format={(v) => fixed(v, 3)} ci={ciOf(metrics.ci95?.macro_f1)} ciFormat={(c) => formatCi(c, 3)} hint="Unweighted mean of per-intent F1: rare intents count as much as common ones." tone={key === "agent" ? "green" : "violet"} />
        <StatTile size="md" label="weighted-F1" value={metrics.weighted_f1} format={(v) => fixed(v, 3)} hint="Per-intent F1 weighted by support, so it tracks accuracy on the common intents." />
        <StatTile size="md" label="misclassified" value={total - correct} format={(v) => int(v)} tone={total - correct > 0 ? "rose" : "green"} sub={<span>of {int(total)} · {isNum(metrics.accuracy) ? pct(1 - metrics.accuracy, 1) : "—"} error rate</span>} hint="Off-diagonal mass of the confusion matrix." />
      </div>

      <section className="region px-5 py-5" aria-label="Confusion matrix">
        <ConfusionMatrix
          title={`Confusion matrix · ${systemLabelFor("intent", key)}`}
          labels={metrics.confusion.labels}
          matrix={metrics.confusion.matrix}
          examples={(gold, pred) => examples.get(`${gold}→${pred}`)}
          onCellClick={predSystem ? openCell : undefined}
        />
        {predSystem && <p className="mt-1 text-[12px] text-faint">Click a non-empty cell to open those tweets in the golden explorer.</p>}
      </section>

      <div className="grid gap-8 xl:grid-cols-2">
        <F1Bars title="F1 per intent" subtitle={ciNote} rows={f1Rows} macroF1={metrics.macro_f1} />
        <section className="flex min-w-0 flex-col gap-3" aria-label="Per-class metrics">
          <h3 className="t-display-20 text-text">Per-class precision, recall and F1</h3>
          <DataTable columns={columns} rows={rows} rowKey={(r) => r.id} initialSort={{ id: "f1", dir: "desc" }} density="compact" caption={`Per-class metrics for ${systemLabelFor("intent", key)}`} maxHeight={420} />
        </section>
      </div>
    </div>
  );
}
