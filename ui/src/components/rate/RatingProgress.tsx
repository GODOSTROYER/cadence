import { cx } from "@/lib/cx";
import { int } from "@/lib/format";

export interface RatingProgressProps {
  /** Pairs rated so far (earlier sessions included). */
  done: number;
  /** Pairs in the whole blind subset. */
  total: number;
  className?: string;
}

/** "12 / 60 rated" in serif numerals over a hairline-thin progress bar. */
export function RatingProgress({ done, total, className }: RatingProgressProps) {
  const ratio = total > 0 ? Math.min(1, done / total) : 0;
  const remaining = Math.max(0, total - done);
  return (
    <div className={cx("flex flex-col gap-2", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="flex items-baseline gap-2">
          <span className="numeral text-[40px] text-text">{int(done)}</span>
          <span className="numeral text-[20px] text-faint">/ {int(total)}</span>
          <span className="eyebrow">rated</span>
        </p>
        <p className="t-mono text-[12px] text-muted">{remaining === 0 ? "all done" : `${int(remaining)} to go`}</p>
      </div>
      <div
        role="progressbar"
        aria-label="Rating progress"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        aria-valuetext={`${done} of ${total} rated`}
        className="h-0.5 w-full overflow-hidden rounded-full bg-surface-2"
      >
        <span className="block h-full rounded-full bg-green transition-[width] duration-300 ease-out" style={{ width: `${ratio * 100}%` }} />
      </div>
    </div>
  );
}
