import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS, ChartFrame, DefaultChartTip, GRID } from "@/components/ChartFrame";
import { fixed, pct } from "@/lib/format";
import { TOKENS } from "@/lib/palette";
import type { ThresholdPoint } from "@/lib/types";

export interface ThresholdChartProps {
  sweep: ThresholdPoint[];
  /** The threshold chosen on the dev split; drawn as an amber marker. */
  chosen: number;
  title?: string;
  subtitle?: string;
  /** Also plot precision (dashed violet). */
  showPrecision?: boolean;
  className?: string;
}

/** Recall vs auto-handle rate across the confidence threshold, with the chosen threshold marked. */
export function ThresholdChart({ sweep, chosen, title, subtitle, showPrecision = true, className }: ThresholdChartProps) {
  const data = [...sweep].sort((a, b) => a.threshold - b.threshold);
  const at = data.find((p) => Math.abs(p.threshold - chosen) < 1e-6);

  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      height={280}
      className={className}
      summary={`Escalation recall and auto-handle rate as the confidence threshold moves from ${fixed(data[0]?.threshold ?? 0, 2)} to ${fixed(data[data.length - 1]?.threshold ?? 1, 2)}. At the chosen threshold ${fixed(chosen, 2)}, recall is ${at ? pct(at.recall) : "n/a"} and auto-handle rate ${at ? pct(at.auto_handle_rate) : "n/a"}.`}
      actions={
        <ul className="hidden items-center gap-3 sm:flex" aria-hidden="true">
          <li className="flex items-center gap-1.5 text-[12px] text-muted"><span className="h-px w-3 bg-green" />recall</li>
          <li className="flex items-center gap-1.5 text-[12px] text-muted"><span className="h-px w-3 bg-sky" />auto-handle</li>
          {showPrecision && <li className="flex items-center gap-1.5 text-[12px] text-muted"><span className="h-px w-3 border-t border-dashed border-violet" />precision</li>}
        </ul>
      }
      chart={
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 12, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid {...GRID} vertical={false} />
            <XAxis dataKey="threshold" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v: number) => fixed(v, 2)} {...AXIS} />
            <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v: number) => pct(v)} width={44} {...AXIS} />
            <Tooltip content={<DefaultChartTip valueFormatter={(v) => pct(v, 1)} />} labelFormatter={(v) => `threshold ${fixed(Number(v), 2)}`} />
            <ReferenceLine x={chosen} stroke={TOKENS.amber} strokeDasharray="2 3" label={{ value: `chosen ${fixed(chosen, 2)}`, position: "top", fill: TOKENS.amber, fontSize: 11, fontFamily: "var(--font-mono)" }} />
            <Line type="monotone" dataKey="recall" name="recall" stroke={TOKENS.green} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />
            <Line type="monotone" dataKey="auto_handle_rate" name="auto-handle rate" stroke={TOKENS.sky} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />
            {showPrecision && <Line type="monotone" dataKey="precision" name="precision" stroke={TOKENS.violet} strokeWidth={1.5} strokeDasharray="4 4" dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />}
          </LineChart>
        </ResponsiveContainer>
      }
      table={
        <table className="table">
          <thead>
            <tr>
              <th scope="col" className="num">Threshold</th>
              <th scope="col" className="num">Recall</th>
              <th scope="col" className="num">Precision</th>
              <th scope="col" className="num">Auto-handle</th>
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.threshold} aria-selected={Math.abs(p.threshold - chosen) < 1e-6 || undefined}>
                <td className="num">{fixed(p.threshold, 2)}{Math.abs(p.threshold - chosen) < 1e-6 && <span className="ml-2 font-sans text-amber">chosen</span>}</td>
                <td className="num">{pct(p.recall, 1)}</td>
                <td className="num">{pct(p.precision, 1)}</td>
                <td className="num">{pct(p.auto_handle_rate, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    />
  );
}
