import { ChevronRight } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { TweetBubble } from "@/components/TweetBubble";
import { int } from "@/lib/format";
import type { MergedGoldenExample } from "@/lib/types";

export interface ThreadViewProps {
  row: MergedGoldenExample;
}

/** The first historical brand reply as a brand tweet, with the full public thread behind a disclosure. */
export function ThreadView({ row }: ThreadViewProps) {
  const first = row.historical_thread.find((t) => t.role === "brand");
  const reply = row.historical_brand_reply || first?.text || "";

  if (!reply) {
    return <EmptyState compact title="No public brand reply" description="The thread carries no recorded SpotifyCares reply, so there is no historical answer to compare against." />;
  }

  return (
    <div className="flex flex-col gap-3">
      <TweetBubble
        brand
        compact
        name="SpotifyCares"
        handle="@SpotifyCares"
        text={reply}
        createdAt={first?.created_at}
        footer={first?.agent_sig ? <span className="t-mono text-[11px] text-faint">signed /{first.agent_sig} · initials are stripped before the agent ever sees a reply</span> : undefined}
      />
      {row.historical_thread.length > 2 && (
        <details className="group">
          <summary className="flex cursor-pointer list-none items-center gap-1 text-[12px] text-muted hover:text-text [&::-webkit-details-marker]:hidden">
            <ChevronRight className="size-3.5 transition-transform duration-[120ms] group-open:rotate-90" aria-hidden="true" />
            full public thread · {int(row.historical_thread.length)} turns
          </summary>
          <ol className="mt-3 flex flex-col gap-2" aria-label="Thread turns">
            {row.historical_thread.map((t) => (
              <li key={t.tweet_id}>
                <TweetBubble
                  compact
                  brand={t.role === "brand"}
                  name={t.role === "brand" ? "SpotifyCares" : "Customer"}
                  handle={t.role === "brand" ? "@SpotifyCares" : "@customer"}
                  text={t.text}
                  createdAt={t.created_at}
                  footer={t.agent_sig ? <span className="t-mono text-[11px] text-faint">/{t.agent_sig}</span> : undefined}
                />
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
