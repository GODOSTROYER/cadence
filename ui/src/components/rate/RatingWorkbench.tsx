import { RatingForm, type CompletedRating } from "@/components/rate/RatingForm";
import { RatingEvidence, RatingItemView } from "@/components/rate/RatingItemView";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cx } from "@/lib/cx";
import type { RatingQueueItem } from "@/lib/types";

/** Grid shared with the loading skeleton so data arrival causes no layout shift. */
export const WORKBENCH_GRID = "grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-8 xl:grid-cols-[minmax(0,1fr)_380px]";

export interface RatingWorkbenchProps {
  item: RatingQueueItem;
  /** From the golden example when known; the tweet's timestamp. */
  createdAt?: string | null;
  /** From the golden example when known; what the brand actually replied. */
  historicalReply?: string | null;
  onSubmit?: (rating: CompletedRating) => void;
  submitting?: boolean;
  error?: unknown;
  /** Preview: nothing interactive. */
  disabled?: boolean;
  className?: string;
}

/**
 * One blind pair: tweet and reply on the left, the form beneath them, evidence in a sticky right column
 * (stacked between them on narrow screens, so the evidence is read before scoring). Remount with a
 * `key` per pair to reset the form.
 */
export function RatingWorkbench({ item, createdAt, historicalReply, onSubmit, submitting, error, disabled = false, className }: RatingWorkbenchProps) {
  const wide = useMediaQuery("(min-width: 1024px)");
  return (
    <div className={cx(WORKBENCH_GRID, className)}>
      <RatingItemView item={item} createdAt={createdAt} className="min-w-0 lg:col-start-1" />
      <RatingEvidence
        evidence={item.evidence}
        historicalReply={historicalReply}
        className="min-w-0 overflow-x-hidden lg:sticky lg:top-10 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:max-h-[calc(100vh-5rem)] lg:self-start lg:overflow-y-auto lg:pr-1"
      />
      <RatingForm
        autoFocus={wide && !disabled}
        disabled={disabled}
        onSubmit={onSubmit}
        submitting={submitting}
        error={error}
        className="min-w-0 lg:col-start-1"
      />
    </div>
  );
}
