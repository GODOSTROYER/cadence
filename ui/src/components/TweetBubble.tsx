import { Link2 } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "@/lib/cx";
import { formatDateTime, relativeDate } from "@/lib/format";

export interface TweetBubbleProps {
  text: string;
  createdAt?: string | null;
  /** Handle shown after the name (default "@customer"). */
  handle?: string;
  /** Display name; the avatar initial derives from it. */
  name?: string;
  /** Brand voice: green avatar and handle, right-aligned meta. */
  brand?: boolean;
  /** Extra row under the text (labels, actions). */
  footer?: ReactNode;
  compact?: boolean;
  className?: string;
}

/** Render `<url>` placeholders as a link chip and `@user` mentions in muted colour. */
function renderTokens(text: string): ReactNode[] {
  const parts = text.split(/(<url>|@user\b)/g);
  return parts.map((part, i) => {
    if (part === "<url>") {
      return (
        <span key={i} className="mx-0.5 inline-flex h-[18px] items-center gap-1 rounded-[4px] border border-border px-1 align-[-3px] font-mono text-[11px] text-muted" title="link or media (URL removed during cleaning)">
          <Link2 className="size-3" aria-hidden="true" />
          link
        </span>
      );
    }
    if (part === "@user") return <span key={i} className="text-sky">@user</span>;
    return <span key={i}>{part}</span>;
  });
}

/** A customer message styled like a tweet: avatar circle, handle, relative date, body. */
export function TweetBubble({ text, createdAt, handle = "@customer", name = "Customer", brand = false, footer, compact = false, className }: TweetBubbleProps) {
  const initial = name.trim().charAt(0).toUpperCase() || "?";
  return (
    <article className={cx("region-plain flex gap-3 bg-surface", compact ? "px-3.5 py-3" : "px-4 py-3.5", className)}>
      <span
        aria-hidden="true"
        className={cx(
          "flex shrink-0 items-center justify-center rounded-full font-medium",
          compact ? "size-8 text-[12px]" : "size-10 text-[14px]",
          brand ? "bg-green text-bg" : "bg-surface-2 text-muted",
        )}
      >
        {initial}
      </span>
      <div className="min-w-0 flex-1">
        <header className="flex flex-wrap items-baseline gap-x-2 text-[13px]">
          <span className="font-medium text-text">{name}</span>
          <span className={cx("t-mono", brand ? "text-green" : "text-muted")}>{handle}</span>
          {createdAt && (
            <time dateTime={createdAt} title={formatDateTime(createdAt)} className="t-mono ml-auto text-[12px] text-faint">
              {relativeDate(createdAt)}
            </time>
          )}
        </header>
        <p className={cx("mt-1 break-words whitespace-pre-wrap text-text", compact ? "text-[14px] leading-relaxed" : "text-[15px] leading-relaxed")}>{renderTokens(text)}</p>
        {footer && <div className="mt-2.5">{footer}</div>}
      </div>
    </article>
  );
}
