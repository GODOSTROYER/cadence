import { ArrowUpRight, Check } from "lucide-react";

import { Tooltip } from "@/components/Tooltip";
import { cx } from "@/lib/cx";
import { DECISION_LABELS, reasonLabel } from "@/lib/labels";
import type { Decision, ReasonCode } from "@/lib/types";

export interface DecisionPillProps {
  decision: Decision;
  /** Primary reason code; shown inline when `showReason` is set. */
  reasonCode?: ReasonCode | null;
  /** One-sentence human reason, shown on hover. */
  reason?: string | null;
  showReason?: boolean;
  size?: "sm" | "md";
  /** Outline-only variant for tables and comparisons. */
  quiet?: boolean;
  className?: string;
}

/** Green auto-handle / amber escalate pill; the reason sentence appears on hover or focus. */
export function DecisionPill({ decision, reasonCode, reason, showReason = false, size = "md", quiet = false, className }: DecisionPillProps) {
  const escalate = decision === "escalate";
  const label = DECISION_LABELS[decision];
  const inline = showReason && escalate && reasonCode ? reasonLabel(reasonCode) : null;
  const tip = reason ? (
    <span>
      {inline === null && reasonCode && <span className="t-mono block text-muted">{reasonCode}</span>}
      {reason}
    </span>
  ) : reasonCode && !inline ? (
    <span className="t-mono">{reasonCode}</span>
  ) : null;

  return (
    <Tooltip content={tip}>
      <span
        tabIndex={tip ? 0 : undefined}
        className={cx(
          "inline-flex max-w-full items-center gap-1.5 rounded-full border font-medium whitespace-nowrap",
          size === "sm" ? "h-[22px] px-2 text-[12px]" : "h-7 px-2.5 text-[13px]",
          escalate
            ? cx("border-amber/40 text-amber", !quiet && "bg-amber-tint")
            : cx("border-green/40 text-green", !quiet && "bg-green-tint"),
          className,
        )}
      >
        {escalate ? <ArrowUpRight className="size-3.5 shrink-0" aria-hidden="true" /> : <Check className="size-3.5 shrink-0" aria-hidden="true" />}
        <span>{label}</span>
        {inline && (
          <>
            <span aria-hidden="true" className="opacity-50">
              ·
            </span>
            <span className="truncate font-normal">{inline}</span>
          </>
        )}
      </span>
    </Tooltip>
  );
}
