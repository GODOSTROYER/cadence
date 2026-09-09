import { SegmentedControl, type SegmentOption } from "@/components/SegmentedControl";
import { cx } from "@/lib/cx";
import { JUDGE_DIMENSION_HINTS, JUDGE_DIMENSION_LABELS } from "@/lib/labels";
import type { JudgeDimension } from "@/lib/types";

export const SCORE_VALUES: readonly number[] = [1, 2, 3, 4, 5];

const SCORE_OPTIONS: readonly SegmentOption<number>[] = SCORE_VALUES.map((v) => ({ value: v, label: String(v) }));

export interface ScoreRowProps {
  dimension: JudgeDimension;
  value: number | null;
  onChange: (value: number) => void;
  disabled?: boolean;
}

/**
 * One rubric dimension: label, the rubric anchor text, and a 1–5 segmented control. The wrapper carries
 * `data-score-group` so the page-level digit hotkeys know which dimension has focus.
 */
export function ScoreRow({ dimension, value, onChange, disabled = false }: ScoreRowProps) {
  const label = JUDGE_DIMENSION_LABELS[dimension];
  return (
    <div data-score-group={dimension} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <p className="text-[14px] font-medium text-text">{label}</p>
        <p className="mt-0.5 max-w-[52ch] text-[12px] leading-snug text-muted">{JUDGE_DIMENSION_HINTS[dimension]}</p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <SegmentedControl options={SCORE_OPTIONS} value={value} onChange={onChange} label={`${label}, 1 to 5`} disabled={disabled} />
        <span aria-hidden="true" className={cx("t-mono w-4 text-right text-[13px]", value === null ? "text-faint" : "text-text")}>
          {value ?? "–"}
        </span>
      </div>
    </div>
  );
}
