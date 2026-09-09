import { SCORE_COLORS } from "@/components/ScoreDistribution";
import { cx } from "@/lib/cx";

export interface ScoreMarkProps {
  /** A 1–5 rubric score; null or undefined renders an em dash. */
  value: number | null | undefined;
  size?: "sm" | "lg";
  /** Dimension name for the accessible label. */
  label?: string;
  className?: string;
}

/** A judge score as a coloured dot (1 rose → 5 green, the ScoreDistribution ramp) plus a mono numeral. */
export function ScoreMark({ value, size = "sm", label, className }: ScoreMarkProps) {
  const has = typeof value === "number" && Number.isFinite(value);
  const color = has ? SCORE_COLORS[Math.min(5, Math.max(1, Math.round(value))) - 1] : undefined;
  return (
    <span className={cx("inline-flex items-center gap-1.5", className)} aria-label={label ? `${label}: ${has ? value : "not scored"}` : undefined} title={label}>
      <span aria-hidden="true" className={cx("shrink-0 rounded-full", size === "lg" ? "size-2.5" : "size-2", !has && "bg-faint")} style={color ? { background: color } : undefined} />
      <span className={cx(size === "lg" ? "numeral text-[28px]" : "t-mono text-[13px]", has ? "text-text" : "text-faint")}>{has ? value : "—"}</span>
    </span>
  );
}
