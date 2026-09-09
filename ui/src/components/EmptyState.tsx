import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  /** Primary action (button or link). */
  action?: ReactNode;
  tone?: "neutral" | "rose" | "amber";
  /** Compact variant for table bodies and side panels. */
  compact?: boolean;
  className?: string;
}

/** Explains what is missing and what to do about it. Also used for error states with tone="rose". */
export function EmptyState({ icon, title, description, action, tone = "neutral", compact = false, className }: EmptyStateProps) {
  return (
    <div
      role={tone === "rose" ? "alert" : undefined}
      className={cx(
        "region-plain flex flex-col items-center justify-center text-center",
        compact ? "gap-2 px-5 py-8" : "gap-3 px-6 py-14",
        tone === "rose" && "border-rose/40",
        tone === "amber" && "border-amber/40",
        className,
      )}
    >
      {icon && (
        <span
          aria-hidden="true"
          className={cx(
            "flex size-10 items-center justify-center rounded-full border border-border [&>svg]:size-[18px]",
            tone === "rose" ? "text-rose" : tone === "amber" ? "text-amber" : "text-muted",
          )}
        >
          {icon}
        </span>
      )}
      <h3 className={cx("t-display text-text", compact ? "text-[20px]" : "text-[24px]")}>{title}</h3>
      {description && <div className="measure text-[13px] leading-relaxed text-muted">{description}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
