import { ChevronDown, ChevronUp, SearchX } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { Chip } from "@/components/Chip";
import { Drawer } from "@/components/Drawer";
import { EmptyState } from "@/components/EmptyState";
import { Kbd } from "@/components/Kbd";
import { SegmentedControl } from "@/components/SegmentedControl";
import { TweetBubble } from "@/components/TweetBubble";
import { int } from "@/lib/format";
import { intentMeta } from "@/lib/intents";
import { SENTIMENT_LABELS, SPLIT_LABELS, systemLabel, systemShort } from "@/lib/labels";
import type { MergedGoldenExample, SystemId } from "@/lib/types";

import { GoldLabelsPanel } from "./GoldLabelsPanel";
import { JudgePanel } from "./JudgePanel";
import { PredictionPanel } from "./PredictionPanel";
import { SYSTEM_ORDER } from "./query";
import { sentimentTone } from "./sentiment";
import { ThreadView } from "./ThreadView";

export interface GoldenDrawerProps {
  /** The row to show; null when `requestedId` is set but no such row exists. */
  row: MergedGoldenExample | null;
  /** The `?id=` in the URL; the drawer is open whenever this is set. */
  requestedId: string | null;
  onClose: () => void;
  /** Move to the previous (-1) or next (+1) row in the table's visible order. */
  onStep: (delta: 1 | -1) => void;
  /** Zero-based index of the row in the visible order and the visible total. */
  position: { index: number; total: number } | null;
  /** System the table is comparing; the prediction panel starts on it. */
  system: SystemId;
  threshold?: number;
}

function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3 border-b border-border py-5 first:pt-0 last:border-b-0 last:pb-0" aria-label={title}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="eyebrow">{title}</h3>
        {aside}
      </header>
      {children}
    </section>
  );
}

function isEditable(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable;
}

/** Full golden record: message, historical thread, gold labels with both passes, every system's output, judge rationale. */
export function GoldenDrawer({ row, requestedId, onClose, onStep, position, system, threshold }: GoldenDrawerProps) {
  const open = requestedId !== null;
  const [predSystem, setPredSystem] = useState<SystemId>(system);

  useEffect(() => {
    setPredSystem(system);
  }, [system]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isEditable(e.target)) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        onStep(e.key === "ArrowDown" ? 1 : -1);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onStep]);

  const available = SYSTEM_ORDER.filter((s) => row?.predictions[s]);
  const shownSystem = row && !row.predictions[predSystem] ? available[0] ?? predSystem : predSystem;
  const judgedCount = row ? Object.keys(row.judge).length : 0;

  const stepper = position && (
    <div className="flex shrink-0 items-center gap-1">
      <span className="t-mono mr-1 hidden text-[12px] text-faint sm:inline" aria-live="polite">
        {int(position.index + 1)} / {int(position.total)}
      </span>
      <button type="button" className="btn btn-ghost size-9 justify-center px-0" aria-label="Previous tweet (arrow up)" onClick={() => onStep(-1)} disabled={position.index <= 0}>
        <ChevronUp className="size-4" />
      </button>
      <button type="button" className="btn btn-ghost size-9 justify-center px-0" aria-label="Next tweet (arrow down)" onClick={() => onStep(1)} disabled={position.index >= position.total - 1}>
        <ChevronDown className="size-4" />
      </button>
    </div>
  );

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={680}
      eyebrow={row ? `${row.id} · ${row.thread_id} · ${SPLIT_LABELS[row.split]} split` : requestedId ?? ""}
      title={row ? intentMeta(row.gold.intent).name : "Not in this export"}
      actions={stepper}
    >
      {!row ? (
        <EmptyState compact icon={<SearchX />} title={`No example ${requestedId ?? ""}`} description="The id is not in the exported golden set. It may belong to a newer run; re-export the UI data or pick a row from the table." />
      ) : (
        <div className="flex flex-col">
          <Section title="customer message">
            <TweetBubble
              text={row.text}
              createdAt={row.created_at}
              footer={
                <div className="flex flex-wrap items-center gap-1.5">
                  <Chip size="sm" dot tone={sentimentTone(row.gold.sentiment)} title="Gold sentiment">
                    {SENTIMENT_LABELS[row.gold.sentiment]}
                  </Chip>
                  {row.gold.media_only && (
                    <Chip size="sm" tone="amber" mono title="The text alone does not identify the issue">
                      media-only
                    </Chip>
                  )}
                  {row.text !== row.text_raw && (
                    <span className="text-[11px] text-faint" title={row.text_raw}>
                      cleaned · handles and links normalised
                    </span>
                  )}
                </div>
              }
            />
          </Section>

          <Section title="what SpotifyCares said in 2017">
            <ThreadView row={row} />
          </Section>

          <Section title="gold labels · two passes, adjudicated">
            <GoldLabelsPanel row={row} />
          </Section>

          <Section
            title="predictions"
            aside={
              available.length > 1 && (
                <SegmentedControl label="Prediction system" size="sm" value={shownSystem} onChange={setPredSystem} options={available.map((s) => ({ value: s, label: systemShort(s), hint: systemLabel(s) }))} />
              )
            }
          >
            <PredictionPanel row={row} system={shownSystem} threshold={threshold} />
          </Section>

          <Section title={`judge · ${judgedCount ? `${int(judgedCount)} systems scored` : "not scored"}`}>
            <JudgePanel row={row} />
          </Section>

          <p className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-faint">
            <span className="flex items-center gap-1">
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> previous / next
            </span>
            <span className="flex items-center gap-1">
              <Kbd>esc</Kbd> close
            </span>
          </p>
        </div>
      )}
    </Drawer>
  );
}
