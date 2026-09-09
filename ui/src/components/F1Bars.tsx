import { Bar, BarChart, Cell, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipProps } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";

import { AXIS, ChartFrame, ChartTipBox } from "@/components/ChartFrame";
import { fixed } from "@/lib/format";
import { intentColor, intentShort } from "@/lib/intents";
import type { CI95, IntentId } from "@/lib/types";

export interface F1Row {
  id: IntentId;
  f1: number;
  support: number;
  precision?: number;
  recall?: number;
  ci?: CI95;
}

export interface F1BarsProps {
  rows: F1Row[];
  title?: string;
  subtitle?: string;
  /** Sort descending by F1 (default true). */
  sort?: boolean;
  /** Reference line for the macro-F1, drawn as a dashed tick label. */
  macroF1?: number;
  className?: string;
}

interface Datum {
  id: string;
  label: string;
  f1: number;
  support: number;
  precision: number | undefined;
  recall: number | undefined;
  err: [number, number];
}

function Tip({ active, payload }: TooltipProps<ValueType, NameType>) {
  const d = payload?.[0]?.payload as Datum | undefined;
  if (!active || !d) return null;
  const rows = [
    { label: "F1", value: fixed(d.f1, 3) },
    ...(d.precision !== undefined ? [{ label: "Precision", value: fixed(d.precision, 3) }] : []),
    ...(d.recall !== undefined ? [{ label: "Recall", value: fixed(d.recall, 3) }] : []),
    { label: "Support", value: String(d.support) },
  ];
  if (d.err[0] || d.err[1]) rows.push({ label: "95% CI", value: `${fixed(d.f1 - d.err[0], 2)} – ${fixed(d.f1 + d.err[1], 2)}` });
  return <ChartTipBox title={<span className="t-mono">{d.id}</span>} rows={rows} />;
}

/** Per-intent F1 as horizontal bars with CI whiskers, plus a table alternative. */
export function F1Bars({ rows, title, subtitle, sort = true, macroF1, className }: F1BarsProps) {
  const data: Datum[] = [...rows]
    .sort((a, b) => (sort ? b.f1 - a.f1 : 0))
    .map((r) => ({
      id: r.id,
      label: intentShort(r.id),
      f1: r.f1,
      support: r.support,
      precision: r.precision,
      recall: r.recall,
      err: r.ci ? [Math.max(0, r.f1 - r.ci[0]), Math.max(0, r.ci[1] - r.f1)] : [0, 0],
    }));
  const height = Math.max(200, data.length * 28 + 40);

  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      height={height}
      className={className}
      summary={`Per-intent F1 scores${macroF1 !== undefined ? `, macro-F1 ${fixed(macroF1, 2)}` : ""}: ${data.map((d) => `${d.label} ${fixed(d.f1, 2)}`).join(", ")}.`}
      chart={
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 4 }} barCategoryGap={6}>
            <XAxis type="number" domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} {...AXIS} />
            <YAxis type="category" dataKey="label" width={86} {...AXIS} tick={{ ...AXIS.tick, fontFamily: "var(--font-sans)" }} />
            <Tooltip cursor={{ fill: "rgba(255,255,255,0.03)" }} content={<Tip />} />
            <Bar dataKey="f1" radius={[0, 3, 3, 0]} isAnimationActive={false} label={{ position: "right", fill: "#8B8F98", fontSize: 12, fontFamily: "var(--font-mono)", formatter: (v: number) => fixed(v, 2) }}>
              {data.map((d) => (
                <Cell key={d.id} fill={intentColor(d.id)} fillOpacity={0.85} />
              ))}
              <ErrorBar dataKey="err" direction="x" width={4} strokeWidth={1} stroke="#ECEDEF" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      }
      table={
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Intent</th>
              <th scope="col" className="num">F1</th>
              {data.some((d) => d.precision !== undefined) && <th scope="col" className="num">Precision</th>}
              {data.some((d) => d.recall !== undefined) && <th scope="col" className="num">Recall</th>}
              <th scope="col" className="num">95% CI</th>
              <th scope="col" className="num">Support</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.id}>
                <td>
                  <span className="t-mono text-muted">{d.id}</span>
                </td>
                <td className="num">{fixed(d.f1, 3)}</td>
                {data.some((x) => x.precision !== undefined) && <td className="num">{d.precision !== undefined ? fixed(d.precision, 3) : "—"}</td>}
                {data.some((x) => x.recall !== undefined) && <td className="num">{d.recall !== undefined ? fixed(d.recall, 3) : "—"}</td>}
                <td className="num">{d.err[0] || d.err[1] ? `${fixed(d.f1 - d.err[0], 2)} – ${fixed(d.f1 + d.err[1], 2)}` : "—"}</td>
                <td className="num">{d.support}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    />
  );
}
