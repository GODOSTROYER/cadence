import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import { EvidenceCard } from "@/components/EvidenceCard";
import { ReplyPreview } from "@/components/ReplyPreview";
import { TweetBubble } from "@/components/TweetBubble";
import { cx } from "@/lib/cx";
import type { Evidence, RatingQueueItem } from "@/lib/types";

export interface RatingItemViewProps {
  item: RatingQueueItem;
  /** When the golden example is known: the tweet's timestamp. */
  createdAt?: string | null;
  className?: string;
}

/** The pair under judgement: the customer's tweet and the reply to rate. Never names the system. */
export function RatingItemView({ item, createdAt, className }: RatingItemViewProps) {
  return (
    <div className={cx("flex flex-col gap-3", className)}>
      <p className="eyebrow">the tweet</p>
      <TweetBubble text={item.text} createdAt={createdAt ?? null} />
      <p className="eyebrow mt-3">the reply to rate</p>
      <ReplyPreview text={item.reply_draft} emptyLabel="This reply is empty: the system drafted nothing" />
    </div>
  );
}

export interface RatingEvidenceProps {
  evidence: Evidence[];
  /** What the brand actually replied in this thread; collapsed by default so it does not anchor the scores. */
  historicalReply?: string | null;
  className?: string;
}

/**
 * Retrieved threads a grounded reply may draw on. The "cited" highlight is suppressed on purpose:
 * only one system cites evidence, so showing it would unblind the rater.
 */
export function RatingEvidence({ evidence, historicalReply, className }: RatingEvidenceProps) {
  const [showHistorical, setShowHistorical] = useState(false);
  return (
    <aside className={cx("flex flex-col gap-3", className)} aria-label="Evidence">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="eyebrow">retrieved evidence · {evidence.length}</p>
        <p className="text-[12px] text-faint">what a grounded reply may draw on</p>
      </div>
      {evidence.length > 0 ? (
        <ol className="flex flex-col gap-3" aria-label="Retrieved threads">
          {evidence.map((e, i) => (
            <li key={`${e.thread_id}-${i}`}>
              <EvidenceCard evidence={e} rank={i + 1} highlighted={false} compact />
            </li>
          ))}
        </ol>
      ) : (
        <p className="region-plain px-4 py-5 text-center text-[13px] text-faint italic">No evidence attached. Judge grounding against general brand practice.</p>
      )}
      {historicalReply && (
        <div className="hairline-t pt-3">
          <button type="button" className="btn btn-ghost btn-sm -ml-2" aria-expanded={showHistorical} onClick={() => setShowHistorical((s) => !s)}>
            {showHistorical ? <ChevronDown className="size-3.5" aria-hidden="true" /> : <ChevronRight className="size-3.5" aria-hidden="true" />}
            {showHistorical ? "Hide" : "Show"} what the brand actually replied
          </button>
          {showHistorical && <TweetBubble className="mt-2" text={historicalReply} brand name="SpotifyCares" handle="@SpotifyCares" compact />}
        </div>
      )}
    </aside>
  );
}
