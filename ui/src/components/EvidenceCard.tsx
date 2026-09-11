import { ArrowDown, ExternalLink, Quote } from "lucide-react";

import { cx } from "@/lib/cx";
import { fixed } from "@/lib/format";
import type { Evidence } from "@/lib/types";

export interface EvidenceCardProps {
  evidence: Evidence;
  /** 1-based rank in the retrieved list. */
  rank?: number;
  /** Highlight as cited (defaults to `evidence.cited`). */
  highlighted?: boolean;
  compact?: boolean;
  className?: string;
}

function hostOf(url: string): string {
  try {
    const u = new URL(url);
    return u.host.replace(/^www\./, "") + (u.pathname.length > 1 ? u.pathname.replace(/\/$/, "") : "");
  } catch {
    return url;
  }
}

/** A retrieved historical thread: customer text → brand reply, BM25 score, thread id, links. */
export function EvidenceCard({ evidence, rank, highlighted, compact = false, className }: EvidenceCardProps) {
  const cited = highlighted ?? evidence.cited;
  return (
    <article
      className={cx(
        "region-plain relative flex flex-col gap-2.5 bg-surface",
        compact ? "px-3.5 py-3" : "px-4 py-3.5",
        cited ? "border-green/40" : "border-border",
        className,
      )}
      aria-label={`Evidence ${rank ?? ""} thread ${evidence.thread_id}${cited ? ", cited" : ""}`}
    >
      {cited && <span aria-hidden="true" className="absolute top-3 bottom-3 left-0 w-px bg-green" />}
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
        {typeof rank === "number" && <span className="t-mono text-faint">#{rank}</span>}
        <span className="t-mono text-muted">{evidence.thread_id}</span>
        <span className="t-mono text-faint">
          BM25 <span className="text-muted">{fixed(evidence.score, 1)}</span>
        </span>
        {cited && (
          <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-green/40 bg-green-tint px-2 py-px font-mono text-[11px] text-green">
            <Quote className="size-3" aria-hidden="true" />
            cited
          </span>
        )}
      </header>
      <blockquote className={cx("border-l border-border pl-3 text-muted", compact ? "text-[13px]" : "text-[13px] leading-relaxed")}>{evidence.customer_text}</blockquote>
      <ArrowDown className="size-3.5 text-faint" aria-hidden="true" />
      <p className={cx("text-text", compact ? "text-[13px]" : "text-[14px] leading-relaxed")}>{evidence.brand_reply}</p>
      {evidence.resolved_links.length > 0 && (
        <ul className="flex min-w-0 flex-wrap gap-1.5" aria-label="Resolved links">
          {evidence.resolved_links.map((url, i) => (
            <li key={`${url}-${i}`} className="min-w-0 max-w-full">
              <a href={url} target="_blank" rel="noreferrer noopener" className="tag max-w-full gap-1 hover:border-border-strong hover:text-text" title={url}>
                <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
                <span className="min-w-0 truncate">{hostOf(url)}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
