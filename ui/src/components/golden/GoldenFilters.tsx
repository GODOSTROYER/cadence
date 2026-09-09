import { Search, X } from "lucide-react";
import { forwardRef, type KeyboardEvent } from "react";

import { Chip } from "@/components/Chip";
import { Kbd } from "@/components/Kbd";
import { SegmentedControl } from "@/components/SegmentedControl";
import { cx } from "@/lib/cx";
import { int, pct } from "@/lib/format";
import { intentMeta, intentShort } from "@/lib/intents";
import { systemLabel, systemShort } from "@/lib/labels";
import type { IntentId, SystemId } from "@/lib/types";

import { CORRECTNESS, DECISION_FILTERS, hasActiveFilters, SPLIT_FILTERS, type Correctness, type DecisionFilter, type GoldenQuery, type RowStats, type SplitFilter } from "./query";

export interface GoldenFiltersProps {
  query: GoldenQuery;
  onChange: (patch: Partial<GoldenQuery>) => void;
  onReset: () => void;
  /** Gold intents present in the data, in taxonomy order. */
  intents: readonly IntentId[];
  /** Systems present in the data. */
  systems: readonly SystemId[];
  stats: RowStats;
  total: number;
  /** Move focus to the first table row (ArrowDown from the search box). */
  onSearchArrowDown: () => void;
  className?: string;
}

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent);

const CORRECT_LABELS: Record<Correctness, string> = { all: "All", correct: "Correct", incorrect: "Wrong" };
const DECISION_LABELS: Record<DecisionFilter, string> = { all: "All", escalate: "Escalate", auto_handle: "Auto-handle", mismatch: "Mismatch" };
const SPLIT_LABELS: Record<SplitFilter, string> = { all: "All", dev: "Dev", test: "Test" };

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="eyebrow text-[11px]">{label}</span>
      {children}
    </div>
  );
}

/** Search box (⌘K / Ctrl K), compared-system switcher and the four filters, plus the match count line. */
export const GoldenFilters = forwardRef<HTMLInputElement, GoldenFiltersProps>(function GoldenFilters(
  { query, onChange, onReset, intents, systems, stats, total, onSearchArrowDown, className },
  ref,
) {
  const onSearchKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      if (query.q) onChange({ q: "" });
      else e.currentTarget.blur();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      onSearchArrowDown();
    }
  };
  const active = hasActiveFilters(query);

  return (
    <div className={cx("flex flex-col gap-4", className)}>
      <div className="region flex flex-col gap-4 px-5 py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <label className="relative flex min-w-0 flex-1 items-center">
            <span className="sr-only">Search the golden set</span>
            <Search className="pointer-events-none absolute left-3 size-4 text-faint" aria-hidden="true" />
            <input
              ref={ref}
              type="search"
              value={query.q}
              onChange={(e) => onChange({ q: e.target.value })}
              onKeyDown={onSearchKey}
              placeholder="Search text, id, thread, notes…"
              autoComplete="off"
              spellCheck={false}
              className="h-9 w-full rounded-md border border-border-strong bg-bg pr-24 pl-9 text-[14px] text-text placeholder:text-faint [&::-webkit-search-cancel-button]:hidden"
              aria-describedby="golden-search-hint"
            />
            <span id="golden-search-hint" className="pointer-events-none absolute right-2.5 flex items-center gap-1" aria-label={`${IS_MAC ? "Command" : "Control"} K focuses the search`}>
              <Kbd>{IS_MAC ? "⌘" : "Ctrl"}</Kbd>
              <Kbd>K</Kbd>
            </span>
          </label>
          <Field label="compare against gold">
            <SegmentedControl label="Compared system" size="sm" value={query.system} onChange={(system) => onChange({ system })} options={systems.map((s) => ({ value: s, label: systemShort(s), hint: systemLabel(s) }))} />
          </Field>
        </div>

        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <Field label="gold intent">
            <select value={query.intent} onChange={(e) => onChange({ intent: e.target.value })} aria-label="Gold intent" className="h-8 max-w-[240px] rounded-md border border-border bg-surface px-2 text-[13px] text-text">
              <option value="">All intents</option>
              {intents.map((id) => (
                <option key={id} value={id}>
                  {intentMeta(id).name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="split">
            <SegmentedControl label="Split" size="sm" value={query.split} onChange={(split) => onChange({ split })} options={SPLIT_FILTERS.map((s) => ({ value: s, label: SPLIT_LABELS[s] }))} />
          </Field>
          <Field label={`intent · ${systemShort(query.system)} vs gold`}>
            <SegmentedControl label="Intent correctness" size="sm" value={query.correct} onChange={(correct) => onChange({ correct })} options={CORRECTNESS.map((c) => ({ value: c, label: CORRECT_LABELS[c] }))} />
          </Field>
          <Field label="gold decision">
            <SegmentedControl
              label="Decision"
              size="sm"
              value={query.decision}
              onChange={(decision) => onChange({ decision })}
              options={DECISION_FILTERS.map((d) => ({ value: d, label: DECISION_LABELS[d], hint: d === "mismatch" ? `${systemShort(query.system)} decided differently from gold` : undefined }))}
            />
          </Field>
          {query.pred && (
            <Field label="predicted intent">
              <Chip size="md" onClick={() => onChange({ pred: "" })} icon={<X />} title="Remove the predicted-intent filter" mono>
                {intentShort(query.pred)}
              </Chip>
            </Field>
          )}
          <button type="button" className="btn btn-ghost btn-sm ml-auto self-end" onClick={onReset} disabled={!active}>
            Reset filters
          </button>
        </div>
      </div>

      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[13px] text-muted" role="status" aria-live="polite">
        <span>
          <span className="t-mono text-text">{int(stats.shown)}</span> of {int(total)} tweets
        </span>
        <span aria-hidden="true" className="text-faint">·</span>
        <span>
          {systemShort(query.system)} intent correct on <span className="t-mono text-text">{int(stats.intentCorrect)}</span>
          {stats.withPrediction > 0 && <span className="t-mono text-faint"> ({pct(stats.intentCorrect / stats.withPrediction)})</span>}
        </span>
        <span aria-hidden="true" className="text-faint">·</span>
        <span>
          <span className={cx("t-mono", stats.decisionErrors > 0 ? "text-amber" : "text-text")}>{int(stats.decisionErrors)}</span> decision mismatches
        </span>
        {stats.withPrediction < stats.shown && (
          <span className="text-faint">
            · {int(stats.shown - stats.withPrediction)} without a {systemShort(query.system)} prediction
          </span>
        )}
      </p>
    </div>
  );
});
