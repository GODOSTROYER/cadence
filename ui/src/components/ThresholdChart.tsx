import { CartesianGrid, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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
          <LineChart data={data} margin={{ top: 12, right: 16, bottom: 14, left: 0 }}>
            <CartesianGrid {...GRID} vertical={false} />
            <XAxis dataKey="threshold" type="number" domain={["dataMin", "dataMax"]} ticks={[0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]} tickFormatter={(v: number) => fixed(v, 1, true)} label={{ value: "confidence threshold", position: "insideBottomRight", fill: TOKENS.faint, fontSize: 11, fontFamily: "var(--font-mono)", dy: 12 }} {...AXIS} />
            <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v: number) => pct(v)} width={44} {...AXIS} />
            <Tooltip content={<DefaultChartTip valueFormatter={(v) => pct(v, 1)} />} labelFormatter={(v) => `threshold ${fixed(Number(v), 2)}`} />
            <ReferenceLine x={chosen} stroke={TOKENS.amber} strokeDasharray="2 3" label={{ value: `chosen ${fixed(chosen, 2)}`, position: chosen > 0.7 ? "insideTopRight" : "insideTopLeft", fill: TOKENS.amber, fontSize: 11, fontFamily: "var(--font-mono)", dx: chosen > 0.7 ? -6 : 6 }} />
            <Line type="linear" dataKey="recall" name="recall" stroke={TOKENS.green} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />
            <Line type="linear" dataKey="auto_handle_rate" name="auto-handle rate" stroke={TOKENS.sky} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />
            {showPrecision && <Line type="linear" dataKey="precision" name="precision" stroke={TOKENS.violet} strokeWidth={1.5} strokeDasharray="4 4" dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />}
            {at && (
              <>
                <ReferenceDot x={chosen} y={at.recall} r={4} fill={TOKENS.green} stroke={TOKENS.bg} strokeWidth={1.5} label={{ value: `recall ${pct(at.recall)}`, position: "left", fill: TOKENS.green, fontSize: 11, fontFamily: "var(--font-mono)", dx: -4, dy: at.recall > 0.85 ? 12 : 0 }} />
                <ReferenceDot x={chosen} y={at.auto_handle_rate} r={4} fill={TOKENS.sky} stroke={TOKENS.bg} strokeWidth={1.5} label={{ value: `auto-handle ${pct(at.auto_handle_rate)}`, position: "left", fill: TOKENS.sky, fontSize: 11, fontFamily: "var(--font-mono)", dx: -4, dy: at.auto_handle_rate < 0.1 ? -10 : 0 }} />
              </>
            )}
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
