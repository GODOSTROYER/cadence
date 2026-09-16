import { Flag } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { Chip } from "@/components/Chip";
import { Kbd } from "@/components/Kbd";
import { ScoreRow } from "@/components/rate/ScoreRow";
import { isApplePlatform, useRatingHotkeys } from "@/components/rate/useRatingHotkeys";
import { SegmentedControl, type SegmentOption } from "@/components/SegmentedControl";
import { describeError } from "@/lib/api";
import { cx } from "@/lib/cx";
import { JUDGE_DIMENSION_LABELS, JUDGE_DIMENSIONS, JUDGE_FLAG_LABELS, JUDGE_FLAGS, VERDICT_LABELS } from "@/lib/labels";
import type { JudgeDimension, JudgeFlag, JudgeFlags, JudgeScores, Verdict } from "@/lib/types";

/** The rater's work in progress; every field may still be unset. */
export interface RatingDraft {
  scores: Partial<Record<JudgeDimension, number>>;
  flags: JudgeFlags;
  verdict: Verdict | null;
  rationale: string;
  response_kind: "resolution" | "clarification" | "handoff" | "other";
}

/** A draft that passed validation: the rubric part of a `RatingSubmission` (CONTRACT §7). */
export interface CompletedRating {
  scores: JudgeScores;
  flags: JudgeFlags;
  verdict: Verdict;
  rationale: string;
  response_kind: RatingDraft["response_kind"];
}

const VERDICT_OPTIONS: readonly SegmentOption<Verdict>[] = [
  { value: "ship", label: VERDICT_LABELS.ship, hint: "Post as-is (S)" },
  { value: "edit", label: VERDICT_LABELS.edit, hint: "A human fixes it first (E)" },
  { value: "reject", label: VERDICT_LABELS.reject, hint: "Must not go out (R)" },
];

function emptyDraft(): RatingDraft {
  return {
    scores: {},
    flags: { hallucinated_link_or_policy: false, asks_sensitive_info: false, wrong_issue: false },
    verdict: null,
    rationale: "",
    response_kind: "other",
  };
}

function isDimension(value: string | undefined): value is JudgeDimension {
  return value !== undefined && (JUDGE_DIMENSIONS as readonly string[]).includes(value);
}

/** Edit and reject must say why; a ship may go without. */
function needsRationale(verdict: Verdict | null): boolean {
  return verdict === "edit" || verdict === "reject";
}

function unscoredDimensions(draft: RatingDraft): JudgeDimension[] {
  return JUDGE_DIMENSIONS.filter((d) => draft.scores[d] === undefined);
}

/** What still blocks submission, in the order the form reads. */
function missingParts(draft: RatingDraft): string[] {
  const parts: string[] = [];
  const unscored = unscoredDimensions(draft);
  if (unscored.length > 0) parts.push(`score ${unscored.map((d) => JUDGE_DIMENSION_LABELS[d].toLowerCase()).join(", ")}`);
  if (!draft.verdict) parts.push("pick a verdict");
  if (needsRationale(draft.verdict) && !draft.rationale.trim()) parts.push("say why (edit and reject need a rationale)");
  return parts;
}

function completeRating(draft: RatingDraft): CompletedRating | null {
  if (missingParts(draft).length > 0 || !draft.verdict) return null;
  const scores = Object.fromEntries(JUDGE_DIMENSIONS.map((d) => [d, draft.scores[d]])) as JudgeScores;
  return { scores, flags: draft.flags, verdict: draft.verdict, rationale: draft.rationale.trim(), response_kind: draft.response_kind };
}

/** The rubric's own rule (CONTRACT §7): ship needs overall ≥ 4 and no flags. Advisory, never blocking. */
function shipConflict(draft: RatingDraft): string | null {
  if (draft.verdict !== "ship") return null;
  const overall = draft.scores.overall;
  if (overall !== undefined && overall < 4) return `The rubric ships only at overall ≥ 4; you gave ${overall}. Keep it if you mean it.`;
  if (JUDGE_FLAGS.some((f) => draft.flags[f])) return "The rubric does not ship a flagged reply. Keep it if you mean it.";
  return null;
}

export interface RatingFormProps {
  onSubmit?: (rating: CompletedRating) => void;
  submitting?: boolean;
  /** Error from the last submit attempt, shown inline; the draft is kept so the rater can retry. */
  error?: unknown;
  /** Preview: everything rendered, nothing interactive. */
  disabled?: boolean;
  /** Focus the first score on mount. Off on phones so the tweet stays in view. */
  autoFocus?: boolean;
  className?: string;
}

/**
 * Scores, flags, verdict, rationale and submit for one blind pair. Owns the draft; remount it (with a
 * `key`) to reset. Digits 1–5 score the focused dimension, or the first unscored one, and move focus on.
 */
export function RatingForm({ onSubmit, submitting = false, error, disabled = false, autoFocus = false, className }: RatingFormProps) {
  const [draft, setDraft] = useState<RatingDraft>(emptyDraft);
  const root = useRef<HTMLFormElement | null>(null);
  const rationaleRef = useRef<HTMLTextAreaElement | null>(null);
  const submitRef = useRef<HTMLButtonElement | null>(null);

  const focusRadio = useCallback((groupSelector: string, preventScroll = false) => {
    root.current?.querySelector<HTMLElement>(`${groupSelector} [role="radio"][tabindex="0"]`)?.focus({ preventScroll });
  }, []);
  const focusDimension = useCallback((d: JudgeDimension) => focusRadio(`[data-score-group="${d}"]`), [focusRadio]);
  const focusVerdict = useCallback(() => focusRadio("[data-verdict-group]"), [focusRadio]);

  useEffect(() => {
    if (autoFocus && !disabled) focusRadio("[data-score-group]", true);
  }, [autoFocus, disabled, focusRadio]);

  const setScore = (d: JudgeDimension, value: number) => setDraft((s) => ({ ...s, scores: { ...s.scores, [d]: value } }));
  const toggleFlag = (f: JudgeFlag) => setDraft((s) => ({ ...s, flags: { ...s.flags, [f]: !s.flags[f] } }));
  const setVerdict = (verdict: Verdict) => setDraft((s) => ({ ...s, verdict }));
  const setRationale = (rationale: string) => setDraft((s) => ({ ...s, rationale }));

  /** Take the rater to the first thing a given draft still lacks. */
  const focusFirstMissing = (d: RatingDraft) => {
    const unscored = unscoredDimensions(d)[0];
    if (unscored) focusDimension(unscored);
    else if (!d.verdict) focusVerdict();
    else if (needsRationale(d.verdict) && !d.rationale.trim()) rationaleRef.current?.focus();
    else submitRef.current?.focus();
  };

  const missing = missingParts(draft);
  const completed = completeRating(draft);
  const conflict = shipConflict(draft);
  const busy = disabled || submitting;

  const trySubmit = () => {
    if (busy) return;
    if (completed) onSubmit?.(completed);
    else focusFirstMissing(draft);
  };

  useRatingHotkeys(!disabled, {
    onDigit: (value, target) => {
      const focused = target?.closest<HTMLElement>("[data-score-group]")?.dataset.scoreGroup;
      const dimension = isDimension(focused) ? focused : unscoredDimensions(draft)[0];
      if (!dimension) return;
      setScore(dimension, value);
      const next = JUDGE_DIMENSIONS[JUDGE_DIMENSIONS.indexOf(dimension) + 1];
      if (next) focusDimension(next);
      else focusVerdict();
    },
    onVerdict: (verdict) => {
      setVerdict(verdict);
      focusFirstMissing({ ...draft, verdict });
    },
    onSubmit: trySubmit,
  });

  const scored = JUDGE_DIMENSIONS.length - unscoredDimensions(draft).length;
  const rationaleState = needsRationale(draft.verdict) ? "required" : "optional for ship";
  const modifier = isApplePlatform() ? "⌘" : "Ctrl";

  return (
    <form
      ref={root}
      aria-label="Rating form"
      aria-disabled={disabled || undefined}
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        trySubmit();
      }}
      className={cx("region flex flex-col gap-6 px-5 py-5 sm:px-6", className)}
    >
      <section aria-labelledby="rating-scores">
        <div className="flex items-baseline justify-between gap-3">
          <h3 id="rating-scores" className="eyebrow">
            scores · 1 worst, 5 best
          </h3>
          <span className="t-mono text-[12px] text-faint">{scored} / 5</span>
        </div>
        <div className="mt-1 flex flex-col divide-y divide-border">
          {JUDGE_DIMENSIONS.map((d) => (
            <ScoreRow key={d} dimension={d} value={draft.scores[d] ?? null} onChange={(v) => setScore(d, v)} disabled={disabled} />
          ))}
        </div>
      </section>

      <label className="flex flex-col gap-2 text-sm">What does this reply provide?
        <select className="rounded border border-border bg-bg p-3" disabled={disabled} value={draft.response_kind} onChange={(e) => setDraft((s) => ({ ...s, response_kind: e.target.value as RatingDraft["response_kind"] }))}>
          <option value="other">Other / no useful next step</option>
          <option value="resolution">A resolution or troubleshooting step</option>
          <option value="clarification">A clarifying question</option>
          <option value="handoff">A human handoff</option>
        </select>
      </label>
      <section aria-labelledby="rating-flags" className="flex flex-col gap-3">
        <h3 id="rating-flags" className="eyebrow">
          flags · any one of these blocks a ship
        </h3>
        <div role="group" aria-label="Flags" className="flex flex-wrap gap-2">
          {JUDGE_FLAGS.map((f) => {
            const on = draft.flags[f];
            return (
              <Chip key={f} onClick={() => toggleFlag(f)} aria-pressed={on} tone={on ? "rose" : "neutral"} icon={<Flag />} disabled={disabled}>
                {JUDGE_FLAG_LABELS[f]}
              </Chip>
            );
          })}
        </div>
      </section>

      <section aria-labelledby="rating-verdict" className="flex flex-col gap-3">
        <h3 id="rating-verdict" className="eyebrow">
          verdict
        </h3>
        <div data-verdict-group className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <SegmentedControl options={VERDICT_OPTIONS} value={draft.verdict} onChange={setVerdict} label="Verdict" disabled={disabled} />
          <p className="text-[12px] leading-snug text-muted">Ship posts as-is · Edit needs a human first · Reject must not go out</p>
        </div>
        {conflict && (
          <p role="status" className="text-[12px] leading-snug text-amber">
            {conflict}
          </p>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <label htmlFor="rating-rationale" className="eyebrow">
          rationale · {rationaleState}
        </label>
        <textarea
          id="rating-rationale"
          ref={rationaleRef}
          rows={3}
          value={draft.rationale}
          onChange={(e) => setRationale(e.target.value)}
          disabled={disabled}
          placeholder="One line: what is right or wrong with this reply, and what you would change."
          className="w-full resize-y rounded-md border border-border-strong bg-bg px-4 py-3 text-[14px] leading-relaxed text-text placeholder:text-faint disabled:cursor-not-allowed disabled:opacity-80"
        />
      </section>

      <footer className="hairline-t flex flex-col gap-3 pt-4">
        <p className="text-[12px] leading-snug text-muted" aria-live="polite">
          {disabled ? (
            "Preview: the controls are disabled in this build."
          ) : error ? (
            <span className="text-rose">{describeError(error)}</span>
          ) : missing.length > 0 ? (
            `Still needed: ${missing.join(" · ")}.`
          ) : (
            "Ready. Submitting saves this rating and loads the next pair."
          )}
        </p>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="hidden flex-wrap items-center gap-x-1 gap-y-1.5 text-[12px] text-faint md:inline-flex" aria-hidden="true">
            <Kbd>1</Kbd>–<Kbd>5</Kbd> score
            <span className="mx-1">·</span>
            <Kbd>Tab</Kbd> next
            <span className="mx-1">·</span>
            <Kbd>S</Kbd>
            <Kbd>E</Kbd>
            <Kbd>R</Kbd> verdict
            <span className="mx-1">·</span>
            <Kbd>{modifier}</Kbd>
            <Kbd>↵</Kbd> submit
          </span>
          <button ref={submitRef} type="submit" className="btn btn-primary ml-auto" disabled={busy || !completed}>
            {submitting ? "Saving…" : "Submit rating"}
          </button>
        </div>
      </footer>
    </form>
  );
}
