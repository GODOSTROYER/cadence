import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipProps } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";

import { AXIS, ChartFrame, ChartTipBox } from "@/components/ChartFrame";
import { fixed, pct } from "@/lib/format";
import { TOKENS } from "@/lib/palette";

export interface ScoreSeries {
  id: string;
  label: string;
  /** Counts of scores 1..5. */
  dist: [number, number, number, number, number];
  mean?: number;
}

export interface ScoreDistributionProps {
  series: ScoreSeries[];
  /** Which rubric dimension these counts describe, for the title/summary. */
  dimension?: string;
  title?: string;
  subtitle?: string;
  className?: string;
}

/** 1 → rose … 5 → green: a score ramp, not a categorical palette. */
export const SCORE_COLORS: readonly string[] = [TOKENS.rose, "#E8926B", TOKENS.faint, TOKENS.sky, TOKENS.green];

interface Datum {
  id: string;
  label: string;
  total: number;
  mean: number | undefined;
  s1: number;
  s2: number;
  s3: number;
  s4: number;
  s5: number;
}

function Tip({ active, payload }: TooltipProps<ValueType, NameType>) {
  const d = payload?.[0]?.payload as Datum | undefined;
  if (!active || !d) return null;
  const counts = [d.s1, d.s2, d.s3, d.s4, d.s5];
  return (
    <ChartTipBox
      title={d.label}
      rows={[
        ...counts.map((n, i) => ({ label: `Score ${i + 1}`, value: `${n} (${pct(d.total ? n / d.total : 0)})`, color: SCORE_COLORS[i] })),
        ...(d.mean !== undefined ? [{ label: "Mean", value: fixed(d.mean, 2) }] : []),
      ]}
    />
  );
}

/** Stacked 1–5 score bars, one row per system, 100% width; table alternative built in. */
export function ScoreDistribution({ series, dimension = "overall", title, subtitle, className }: ScoreDistributionProps) {
  const data: Datum[] = series.map((s) => {
    const total = s.dist.reduce((a, b) => a + b, 0) || 1;
    const [s1, s2, s3, s4, s5] = s.dist.map((n) => (n / total) * 100) as [number, number, number, number, number];
    return { id: s.id, label: s.label, total, mean: s.mean, s1, s2, s3, s4, s5 };
  });
  const height = Math.max(120, series.length * 44 + 36);

  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      height={height}
      className={className}
      summary={`Distribution of ${dimension} scores 1 to 5 per system: ${series
        .map((s) => `${s.label} ${s.dist.map((n, i) => `${i + 1}:${n}`).join(" ")}`)
        .join("; ")}.`}
      actions={
        <ul className="hidden items-center gap-2 sm:flex" aria-hidden="true">
          {SCORE_COLORS.map((c, i) => (
            <li key={i} className="flex items-center gap-1 font-mono text-[11px] text-muted">
              <span className="size-2 rounded-[2px]" style={{ background: c }} />
              {i + 1}
            </li>
          ))}
        </ul>
      }
      chart={
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" stackOffset="none" margin={{ top: 0, right: 8, bottom: 0, left: 0 }} barCategoryGap={10}>
            <XAxis type="number" domain={[0, 100]} hide />
            <YAxis type="category" dataKey="label" width={130} {...AXIS} tick={{ ...AXIS.tick, fontFamily: "var(--font-sans)", fill: TOKENS.text }} />
            <Tooltip cursor={{ fill: "rgba(255,255,255,0.03)" }} content={<Tip />} />
            {(["s1", "s2", "s3", "s4", "s5"] as const).map((key, i) => (
              <Bar key={key} dataKey={key} stackId="score" fill={SCORE_COLORS[i]} isAnimationActive={false} radius={i === 0 ? [3, 0, 0, 3] : i === 4 ? [0, 3, 3, 0] : 0} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      }
      table={
        <table className="table">
          <thead>
            <tr>
              <th scope="col">System</th>
              {[1, 2, 3, 4, 5].map((s) => (
                <th key={s} scope="col" className="num">
                  {s}
                </th>
              ))}
              <th scope="col" className="num">Mean</th>
            </tr>
          </thead>
          <tbody>
            {series.map((s) => (
              <tr key={s.id}>
                <td>{s.label}</td>
                {s.dist.map((n, i) => (
                  <td key={i} className="num">
                    {n}
                  </td>
                ))}
                <td className="num">{s.mean !== undefined ? fixed(s.mean, 2) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    />
  );
}
