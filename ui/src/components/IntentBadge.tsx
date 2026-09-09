import { cx } from "@/lib/cx";
import { intentMeta } from "@/lib/intents";
import type { IntentId } from "@/lib/types";

export interface IntentBadgeProps {
  id: IntentId;
  /** Show the snake_case id in mono (default true). */
  showId?: boolean;
  /** Show the human name (default true); `compact` uses the short name. */
  showName?: boolean;
  compact?: boolean;
  size?: "sm" | "md";
  /** Strike through when this prediction is wrong; dims the badge. */
  wrong?: boolean;
  className?: string;
}

/** Colour dot + mono id + name. The single way an intent is rendered anywhere in the UI. */
export function IntentBadge({ id, showId = true, showName = true, compact = false, size = "md", wrong = false, className }: IntentBadgeProps) {
  const meta = intentMeta(id);
  return (
    <span
      className={cx("inline-flex min-w-0 items-center gap-2", size === "sm" ? "text-[12px]" : "text-[13px]", wrong && "opacity-70", className)}
      title={`${meta.name} (${meta.id})`}
    >
      <span aria-hidden="true" className="size-2 shrink-0 rounded-full" style={{ background: meta.color }} />
      {showId && <span className={cx("t-mono truncate text-muted", wrong && "line-through decoration-rose")}>{meta.id}</span>}
      {showName && <span className={cx("truncate text-text", showId && "hidden sm:inline")}>{compact ? meta.short : meta.name}</span>}
    </span>
  );
}
