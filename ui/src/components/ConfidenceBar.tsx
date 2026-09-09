import { cx } from "@/lib/cx";
import { fixed } from "@/lib/format";

export interface ConfidenceBarProps {
  /** Intent confidence in [0, 1]; null when the system does not produce one. */
  value: number | null;
  /** Escalation threshold; drawn as a tick, and the fill turns amber below it. */
  threshold?: number;
  label?: string;
  showValue?: boolean;
  className?: string;
}

/** Thin confidence bar with the threshold tick. Below threshold means "escalate (low_confidence)". */
export function ConfidenceBar({ value, threshold, label = "Intent confidence", showValue = true, className }: ConfidenceBarProps) {
  const has = typeof value === "number" && Number.isFinite(value);
  const v = has ? Math.max(0, Math.min(1, value)) : 0;
  const below = has && typeof threshold === "number" && v < threshold;

  return (
    <div className={cx("flex min-w-0 items-center gap-3", className)}>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={has ? v : undefined}
        aria-valuetext={has ? `${fixed(v, 2)}${below ? " (below threshold)" : ""}` : "not available"}
        className="relative h-1.5 min-w-0 flex-1 overflow-visible rounded-full bg-surface-2"
      >
        <span
          className={cx("absolute inset-y-0 left-0 rounded-full transition-[width] duration-500 ease-out", below ? "bg-amber" : "bg-green", !has && "bg-faint")}
          style={{ width: `${has ? v * 100 : 0}%` }}
        />
        {typeof threshold === "number" && (
          <span
            aria-hidden="true"
            title={`threshold ${fixed(threshold, 2)}`}
            className="absolute -top-1 -bottom-1 w-px bg-text/60"
            style={{ left: `${threshold * 100}%` }}
          />
        )}
      </div>
      {showValue && <span className={cx("t-mono w-9 shrink-0 text-right text-[13px]", has ? "text-text" : "text-faint")}>{has ? fixed(v, 2) : "—"}</span>}
    </div>
  );
}
