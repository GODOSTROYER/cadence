import type { ReactNode } from "react";

import { Skeleton } from "@/components/Skeleton";
import { Tooltip } from "@/components/Tooltip";
import { useCountUp } from "@/hooks/useCountUp";
import { cx } from "@/lib/cx";
import { ci as formatCi, delta as formatDelta } from "@/lib/format";
import type { CI95 } from "@/lib/types";

export type MetricTone = "neutral" | "green" | "amber" | "rose" | "sky" | "violet";

export interface MetricDelta {
  /** Signed difference in the metric's own units. */
  value: number;
  /** What the comparison is against, e.g. "vs nearest neighbour". */
  label: string;
  /** Override the sign → colour mapping (default: positive is good). */
  positiveIsGood?: boolean;
  format?: (v: number) => string;
}

export interface MetricTileProps {
  label: string;
  /** Numeric value (animated with a count-up on first view). */
  value: number;
  /** Formatter for the numeral (default: two decimals). */
  format?: (v: number) => string;
  /** 95% CI shown as the subtitle. */
  ci?: CI95;
  ciFormat?: (interval: CI95) => string;
  /** Delta subtitle (used instead of, or in addition to, the CI). */
  delta?: MetricDelta;
  /** Free-form subtitle when neither CI nor delta fits. */
  sub?: ReactNode;
  /** Explains how the number was computed (tooltip on the label). */
  hint?: string;
  /** Recent values for a tiny sparkline. */
  sparkline?: number[];
  tone?: MetricTone;
  size?: "lg" | "md" | "sm";
  loading?: boolean;
  className?: string;
}

const NUMERAL_SIZE: Record<NonNullable<MetricTileProps["size"]>, string> = {
  lg: "text-[56px] sm:text-[64px]",
  md: "text-[40px]",
  sm: "text-[28px]",
};

const TONE_TEXT: Record<MetricTone, string> = {
  neutral: "text-text",
  green: "text-green",
  amber: "text-amber",
  rose: "text-rose",
  sky: "text-sky",
  violet: "text-violet",
};

function Sparkline({ values, tone }: { values: number[]; tone: MetricTone }) {
  if (values.length < 2) return null;
  const w = 88;
  const h = 24;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${((i / (values.length - 1)) * w).toFixed(1)},${(h - ((v - min) / span) * (h - 2) - 1).toFixed(1)}`);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" className={cx("shrink-0", tone === "neutral" ? "text-muted" : TONE_TEXT[tone])}>
      <polyline points={pts.join(" ")} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** Serif numeral with its label and a CI or delta underneath (ui/DESIGN.md). */
export function MetricTile({
  label,
  value,
  format = (v) => v.toFixed(2),
  ci,
  ciFormat = (interval) => formatCi(interval),
  delta,
  sub,
  hint,
  sparkline,
  tone = "neutral",
  size = "lg",
  loading = false,
  className,
}: MetricTileProps) {
  const shown = useCountUp(value, 600, !loading);
  const deltaGood = delta ? (delta.positiveIsGood ?? true) === delta.value >= 0 : true;

  return (
    <div className={cx("region flex min-w-0 flex-col gap-3 px-6 py-5", className)}>
      <div className="flex items-center justify-between gap-3">
        <Tooltip content={hint}>
          <p className={cx("eyebrow truncate", hint && "cursor-help underline decoration-dotted decoration-faint underline-offset-3")}>{label}</p>
        </Tooltip>
        {sparkline && !loading && <Sparkline values={sparkline} tone={tone} />}
      </div>
      {loading ? (
        <Skeleton height={size === "lg" ? 64 : size === "md" ? 40 : 28} width="60%" radius={8} />
      ) : (
        <p className={cx("numeral truncate", NUMERAL_SIZE[size], TONE_TEXT[tone])} aria-label={`${label}: ${format(value)}`}>
          {format(shown)}
        </p>
      )}
      <div className="flex min-h-5 flex-wrap items-baseline gap-x-3 gap-y-1 text-[13px] text-muted">
        {loading ? (
          <Skeleton height={13} width="45%" />
        ) : (
          <>
            {ci && (
              <span>
                <span className="text-faint">95% CI</span> <span className="t-mono text-muted">{ciFormat(ci)}</span>
              </span>
            )}
            {delta && (
              <span className={cx("t-mono", deltaGood ? "text-green" : "text-rose")}>
                {(delta.format ?? ((v: number) => formatDelta(v)))(delta.value)} <span className="font-sans text-muted">{delta.label}</span>
              </span>
            )}
            {sub}
          </>
        )}
      </div>
    </div>
  );
}
