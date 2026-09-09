import { Check, Minus, X } from "lucide-react";

import { cx } from "@/lib/cx";
import { ms as formatMs } from "@/lib/format";

export type StepStatus = "pending" | "active" | "done" | "skipped" | "error";

export interface TimelineStep {
  id: string;
  label: string;
  /** Short detail under the label (e.g. "6 threads", "forced escalate"). */
  detail?: string;
  /** Latency; omitted while pending. */
  ms?: number | null;
  status: StepStatus;
}

export interface StepTimelineProps {
  steps: TimelineStep[];
  /** Stack vertically (default: horizontal on ≥640px, vertical below). */
  vertical?: boolean;
  className?: string;
}

function Indicator({ status }: { status: StepStatus }) {
  const base = "flex size-5 shrink-0 items-center justify-center rounded-full border transition-colors duration-[120ms]";
  switch (status) {
    case "done":
      return (
        <span className={cx(base, "border-green bg-green text-bg")}>
          <Check className="size-3" strokeWidth={3} aria-hidden="true" />
        </span>
      );
    case "active":
      return (
        <span className={cx(base, "step-active border-green bg-surface")}>
          <span className="size-1.5 rounded-full bg-green" />
        </span>
      );
    case "error":
      return (
        <span className={cx(base, "border-rose bg-rose-tint text-rose")}>
          <X className="size-3" strokeWidth={3} aria-hidden="true" />
        </span>
      );
    case "skipped":
      return (
        <span className={cx(base, "border-dashed border-faint text-faint")}>
          <Minus className="size-3" aria-hidden="true" />
        </span>
      );
    default:
      return <span className={cx(base, "border-faint bg-transparent")} />;
  }
}

const STATUS_TEXT: Record<StepStatus, string> = {
  pending: "pending",
  active: "running",
  done: "done",
  skipped: "skipped",
  error: "failed",
};

/** rules → retrieve → LLM → decide, with latency and status per step. Steps light up in order. */
export function StepTimeline({ steps, vertical = false, className }: StepTimelineProps) {
  return (
    <ol
      aria-label="Agent pipeline steps"
      className={cx("flex gap-0", vertical ? "flex-col" : "flex-col sm:flex-row sm:items-start", className)}
    >
      {steps.map((s, i) => {
        const last = i === steps.length - 1;
        const reached = s.status === "done" || s.status === "active";
        return (
          <li key={s.id} className={cx("flex min-w-0", vertical ? "flex-row" : "flex-row sm:flex-1 sm:flex-col")}>
            <div className={cx("flex", vertical ? "flex-col items-center" : "flex-col items-center sm:w-full sm:flex-row")}>
              <Indicator status={s.status} />
              {!last && (
                <span
                  aria-hidden="true"
                  className={cx(
                    "transition-colors duration-300",
                    vertical ? "my-1 h-6 w-px" : "my-1 h-6 w-px sm:mx-2 sm:my-0 sm:h-px sm:flex-1",
                    reached && steps[i + 1]?.status !== "pending" ? "bg-green/60" : "bg-border-strong",
                  )}
                />
              )}
            </div>
            <div className={cx("min-w-0 pb-4", vertical ? "pl-3" : "pl-3 sm:mt-2 sm:pr-4 sm:pl-0")}>
              <p className={cx("text-[13px] font-medium", s.status === "pending" ? "text-faint" : s.status === "error" ? "text-rose" : "text-text")}>
                {s.label}
                <span className="sr-only">, {STATUS_TEXT[s.status]}</span>
              </p>
              <p className="t-mono mt-0.5 text-[12px] text-muted">
                {typeof s.ms === "number" ? formatMs(s.ms) : s.status === "active" ? "…" : s.status === "skipped" ? "skipped" : "—"}
              </p>
              {s.detail && <p className="mt-0.5 text-[12px] leading-snug text-muted">{s.detail}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
