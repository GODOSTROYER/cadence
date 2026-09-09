import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import type { TooltipProps } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";

import { AXIS, ChartFrame, ChartTipBox, GRID } from "@/components/ChartFrame";
import { systemShort } from "@/lib/labels";
import { systemColor, TOKENS } from "@/lib/palette";
import type { AgreementPair } from "@/lib/types";

export interface AgreementScatterProps {
  pairs: AgreementPair[];
  title?: string;
  subtitle?: string;
  className?: string;
}

interface Point extends AgreementPair {
  x: number;
  y: number;
}

/** Deterministic jitter in [-0.2, 0.2] from the pair's id and system, so re-renders are stable. */
function jitter(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return ((h % 1000) / 1000 - 0.5) * 0.4;
}

function Tip({ active, payload }: TooltipProps<ValueType, NameType>) {
  const p = payload?.[0]?.payload as Point | undefined;
  if (!active || !p) return null;
  return (
    <ChartTipBox
      title={<span className="t-mono">{p.id}</span>}
      rows={[
        { label: "System", value: systemShort(p.system), color: systemColor(p.system) },
        { label: "Human", value: String(p.human) },
        { label: "Judge", value: String(p.judge) },
      ]}
    />
  );
}

/** Human vs judge overall scores with jitter and the identity line; colour = system. */
export function AgreementScatter({ pairs, title, subtitle, className }: AgreementScatterProps) {
  const systems = [...new Set(pairs.map((p) => p.system))];
  const points: Point[] = pairs.map((p) => ({ ...p, x: p.human + jitter(`${p.id}:${p.system}:h`), y: p.judge + jitter(`${p.id}:${p.system}:j`) }));
  const exact = pairs.filter((p) => p.human === p.judge).length;

  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      height={300}
      className={className}
      summary={`Human versus judge overall scores for ${pairs.length} rated replies; ${exact} agree exactly. Points on the diagonal mean agreement.`}
      actions={
        <ul className="hidden items-center gap-3 sm:flex" aria-hidden="true">
          {systems.map((s) => (
            <li key={s} className="flex items-center gap-1.5 text-[12px] text-muted">
              <span className="size-2 rounded-full" style={{ background: systemColor(s) }} />
              {systemShort(s)}
            </li>
          ))}
        </ul>
      }
      chart={
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid {...GRID} />
            <XAxis type="number" dataKey="x" name="Human" domain={[0.5, 5.5]} ticks={[1, 2, 3, 4, 5]} {...AXIS} label={{ value: "human", position: "insideBottomRight", offset: -4, fill: TOKENS.faint, fontSize: 11 }} />
            <YAxis type="number" dataKey="y" name="Judge" domain={[0.5, 5.5]} ticks={[1, 2, 3, 4, 5]} width={36} {...AXIS} label={{ value: "judge", angle: -90, position: "insideLeft", offset: 12, fill: TOKENS.faint, fontSize: 11 }} />
            <ZAxis range={[36, 36]} />
            <ReferenceLine segment={[{ x: 0.5, y: 0.5 }, { x: 5.5, y: 5.5 }]} stroke={TOKENS.faint} strokeDasharray="3 4" ifOverflow="visible" />
            <Tooltip cursor={false} content={<Tip />} />
            {systems.map((s) => (
              <Scatter key={s} name={systemShort(s)} data={points.filter((p) => p.system === s)} fill={systemColor(s)} fillOpacity={0.8} isAnimationActive={false} />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      }
      table={
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Example</th>
              <th scope="col">System</th>
              <th scope="col" className="num">Human</th>
              <th scope="col" className="num">Judge</th>
              <th scope="col" className="num">Δ</th>
            </tr>
          </thead>
          <tbody>
            {pairs.map((p) => (
              <tr key={`${p.id}-${p.system}`}>
                <td className="t-mono text-muted">{p.id}</td>
                <td>{systemShort(p.system)}</td>
                <td className="num">{p.human}</td>
                <td className="num">{p.judge}</td>
                <td className="num">{p.judge - p.human}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    />
  );
}
