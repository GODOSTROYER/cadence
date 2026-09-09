import { GoldVsPredicted } from "@/components/failures/GoldVsPredicted";
import { ReplyPreview } from "@/components/ReplyPreview";
import { TweetBubble } from "@/components/TweetBubble";
import type { FailureExample } from "@/lib/types";

export interface FailureExampleCardProps {
  example: FailureExample;
  /** 0-based position within the failure mode. */
  index: number;
}

/** One real example: the tweet, gold vs predicted labels, the drafted reply and the one-line diagnosis. */
export function FailureExampleCard({ example, index }: FailureExampleCardProps) {
  return (
    <li className="region-plain flex flex-col gap-4 p-4 sm:p-5">
      <p className="t-mono text-[12px] text-faint">
        example {index + 1} · <span className="text-muted">{example.golden_id}</span>
      </p>
      <div className="grid gap-4 lg:grid-cols-2 lg:gap-5">
        <div className="flex min-w-0 flex-col gap-4">
          <TweetBubble text={example.text} compact />
          <GoldVsPredicted example={example} />
        </div>
        <ReplyPreview text={example.reply_draft} compact emptyLabel="No reply drafted: the system escalated without one" />
      </div>
      <p className="relative pl-4 text-[14px] leading-relaxed text-text">
        <span aria-hidden="true" className="absolute top-1 bottom-1 left-0 w-px bg-rose" />
        <span className="t-mono mr-2 text-[12px] text-rose">what went wrong</span>
        {example.why}
      </p>
    </li>
  );
}
