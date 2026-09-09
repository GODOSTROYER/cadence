import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";

import { useTypewriter } from "@/hooks/useTypewriter";
import { cx } from "@/lib/cx";

export const TWEET_LIMIT = 280;
const SIGNATURE = /\s\/AI$/;

export interface ReplyPreviewProps {
  text: string;
  /** Type the reply in at ~8ms/char (click anywhere on the body to skip). */
  animate?: boolean;
  /** Called once the typed-in text is fully revealed. */
  onTyped?: () => void;
  /** Who the reply is to (shown as "Replying to …"). */
  replyingTo?: string;
  /** Quiet variant for comparisons in tables/drawers. */
  compact?: boolean;
  /** Label when there is no draft (e.g. the zero-shot baseline). */
  emptyLabel?: string;
  className?: string;
}

/** 280-char tweet-composer look for a drafted reply: counter, copy, highlighted "/AI" signature. */
export function ReplyPreview({ text, animate = false, onTyped, replyingTo = "@customer", compact = false, emptyLabel = "No reply drafted", className }: ReplyPreviewProps) {
  const { shown, typing, skip } = useTypewriter(text, animate);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!typing && animate && text) onTyped?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire once when typing finishes
  }, [typing]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  const signed = SIGNATURE.test(text);
  const body = signed && !typing ? shown.replace(SIGNATURE, "") : shown;
  const over = text.length > TWEET_LIMIT;

  if (!text) {
    return (
      <div className={cx("region-plain flex items-center justify-center px-4 py-6 text-[13px] text-faint italic", className)}>{emptyLabel}</div>
    );
  }

  return (
    <div className={cx("region-plain flex flex-col bg-surface", className)}>
      <div className="flex items-center gap-2 px-4 pt-3 text-[12px] text-muted">
        <span aria-hidden="true" className="flex size-5 items-center justify-center rounded-full bg-green text-[10px] font-semibold text-bg">
          S
        </span>
        <span className="font-medium text-text">SpotifyCares</span>
        <span className="t-mono text-green">@SpotifyCares</span>
        <span className="text-faint">·</span>
        <span className="truncate">Replying to {replyingTo}</span>
      </div>
      <p
        onClick={typing ? skip : undefined}
        title={typing ? "Click to skip typing" : undefined}
        className={cx(
          "px-4 pt-2 pb-3 break-words whitespace-pre-wrap text-text",
          compact ? "text-[14px] leading-relaxed" : "text-[16px] leading-relaxed",
          typing && "cursor-pointer",
        )}
        aria-live={animate ? "polite" : undefined}
        aria-busy={typing || undefined}
      >
        <span className={cx(typing && "caret")}>{body}</span>
        {signed && !typing && <span className="t-mono ml-1 rounded-[4px] bg-green-tint px-1 py-0.5 text-[13px] text-green">/AI</span>}
      </p>
      <footer className="hairline-t flex items-center justify-between gap-3 px-4 py-2">
        <span className={cx("t-mono text-[12px]", over ? "text-rose" : "text-faint")} aria-label={`${text.length} of ${TWEET_LIMIT} characters`}>
          {typing ? shown.length : text.length} / {TWEET_LIMIT}
          {over && <span className="ml-2 font-sans">over the limit</span>}
          {typing && <span className="ml-2 font-sans text-faint">click to skip</span>}
        </span>
        <button type="button" onClick={copy} className="btn btn-ghost btn-sm -mr-2" aria-label="Copy reply">
          {copied ? <Check className="size-3.5 text-green" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </footer>
    </div>
  );
}
