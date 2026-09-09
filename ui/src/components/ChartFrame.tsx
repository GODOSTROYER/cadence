import { useState, type ReactNode } from "react";
import type { TooltipProps } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";

import { SegmentedControl } from "@/components/SegmentedControl";
import { cx } from "@/lib/cx";
import { TOKENS } from "@/lib/palette";

export type ChartView = "chart" | "table";

export interface ChartFrameProps {
  /** Small serif title; omit for an unlabelled chart inside a labelled region. */
  title?: ReactNode;
  subtitle?: ReactNode;
  /** One-sentence description of what the chart shows, used as the chart's aria-label. */
  summary: string;
  chart: ReactNode;
  /** Accessible table alternative (rendered when the toggle says "Table"). */
  table: ReactNode;
  defaultView?: ChartView;
  /** Height of the chart area in px (default 260). */
  height?: number;
  actions?: ReactNode;
  className?: string;
}

/** Wraps every chart: title row, Chart/Table toggle, fixed-height chart area with an aria label. */
export function ChartFrame({ title, subtitle, summary, chart, table, defaultView = "chart", height = 260, actions, className }: ChartFrameProps) {
  const [view, setView] = useState<ChartView>(defaultView);
  return (
    <section className={cx("flex min-w-0 flex-col gap-3", className)} aria-label={typeof title === "string" ? title : undefined}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {title && <h3 className="t-display-20 text-text">{title}</h3>}
          {subtitle && <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-2">
          {actions}
          <SegmentedControl
            size="sm"
            label="Chart or table view"
            value={view}
            onChange={setView}
            options={[
              { value: "chart", label: "Chart" },
              { value: "table", label: "Table" },
            ]}
          />
        </div>
      </header>
      {view === "chart" ? (
        <div role="img" aria-label={summary} className="min-w-0" style={{ height }}>
          {chart}
        </div>
      ) : (
        <div className="table-wrap" style={{ maxHeight: Math.max(height, 200) }}>
          {table}
        </div>
      )}
    </section>
  );
}

/** Shared recharts axis styling. */
export const AXIS = {
  tick: { fill: TOKENS.muted, fontSize: 12, fontFamily: "var(--font-mono)" },
  axisLine: { stroke: TOKENS.border },
  tickLine: false as const,
};

export const GRID = { stroke: TOKENS.border, strokeDasharray: "2 4" };

export interface ChartTipRow {
  label: ReactNode;
  value: ReactNode;
  color?: string;
}

/** Dark, hairline tooltip body shared by every recharts chart. */
export function ChartTipBox({ title, rows }: { title?: ReactNode; rows: ChartTipRow[] }) {
  return (
    <div className="rounded-md border border-border-strong bg-surface-2 px-3 py-2 text-[12px]">
      {title && <p className="mb-1 font-medium text-text">{title}</p>}
      <ul className="flex flex-col gap-0.5">
        {rows.map((r, i) => (
          <li key={i} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-muted">
              {r.color && <span aria-hidden="true" className="size-2 rounded-full" style={{ background: r.color }} />}
              {r.label}
            </span>
            <span className="t-mono text-text">{r.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export interface DefaultChartTipProps extends TooltipProps<ValueType, NameType> {
  /** Formats numeric series values (default: two decimals). */
  valueFormatter?: (v: number) => string;
}

/** Default recharts tooltip renderer: one row per series in the payload. */
export function DefaultChartTip({ active, payload, label, valueFormatter }: DefaultChartTipProps) {
  if (!active || !payload?.length) return null;
  return (
    <ChartTipBox
      title={label}
      rows={payload.map((p) => ({
        label: String(p.name ?? p.dataKey ?? ""),
        value: typeof p.value === "number" ? (valueFormatter ? valueFormatter(p.value) : p.value.toFixed(2)) : String(p.value ?? ""),
        color: typeof p.color === "string" ? p.color : undefined,
      }))}
    />
  );
}
