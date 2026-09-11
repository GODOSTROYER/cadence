import { ArrowUpRight, Check } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { IntentBadge } from "@/components/IntentBadge";
import { cx } from "@/lib/cx";
import { fixed, int } from "@/lib/format";
import { reasonLabel, systemShortFor } from "@/lib/labels";
import type { MergedGoldenExample, SystemId } from "@/lib/types";

export interface ExampleListProps {
  /** Golden ids from `missed_examples` / `unnecessary_examples`. */
  ids: readonly string[];
  /** Golden rows to join against; null while the export is unavailable. */
  golden: MergedGoldenExample[] | null;
  /** Summary system key the list belongs to; its prediction system supplies the "what it did" line. */
  systemKey: string;
  predictionSystem: SystemId | undefined;
  tone: "rose" | "amber";
  title: string;
  description: string;
  /** Rows shown before the "show all" toggle (default 10). */
  limit?: number;
  className?: string;
}

const TONE_TEXT = { rose: "text-rose", amber: "text-amber" } as const;
const TONE_BORDER = { rose: "border-rose/40", amber: "border-amber/40" } as const;

/** Escalation errors joined against the golden set: text, gold reason, and what the system decided. */
export function ExampleList({ ids, golden, systemKey, predictionSystem, tone, title, description, limit = 10, className }: ExampleListProps) {
  const [expanded, setExpanded] = useState(false);
  const byId = new Map((golden ?? []).map((r) => [r.id, r]));
  const shown = expanded ? ids : ids.slice(0, limit);
  const missed = tone === "rose";

  return (
    <section className={cx("flex min-w-0 flex-col gap-3", className)} aria-label={title}>
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="t-display-20 text-text">
          {title} <span className={cx("t-mono text-[16px]", TONE_TEXT[tone])}>{int(ids.length)}</span>
        </h3>
        <p className="text-[12px] text-faint">{description}</p>
      </header>

      {ids.length === 0 ? (
        <EmptyState compact icon={<Check />} title={missed ? "No missed escalations" : "No unnecessary escalations"} description={`${systemShortFor("escalation", systemKey)} made none of these on the test split.`} />
      ) : (
        <ol className={cx("flex flex-col divide-y divide-border rounded-lg border", TONE_BORDER[tone])}>
          {shown.map((id) => {
            const row = byId.get(id);
            const pred = row && predictionSystem ? row.predictions[predictionSystem] : undefined;
            return (
              <li key={id}>
                <Link to={`/golden?id=${encodeURIComponent(id)}`} className="flex gap-3 px-4 py-3 transition-colors duration-[120ms] hover:bg-surface-2 focus-visible:outline-offset-[-2px]">
                  <span className="t-mono w-12 shrink-0 pt-0.5 text-[12px] text-muted">{id}</span>
                  <div className="min-w-0 flex-1">
                    {row ? (
                      <>
                        <p className="truncate-2 text-[13px] leading-snug text-text">{row.text}</p>
                        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[12px]">
                          <Chip size="sm" tone={tone} dot title={missed ? "Gold escalation reason" : "Gold decision"}>
                            {missed ? `gold: ${reasonLabel(row.gold.escalation_reason_code) || "escalate"}` : "gold: auto-handle"}
                          </Chip>
                          <IntentBadge id={row.gold.intent} size="sm" compact showName={false} />
                          {pred && (
                            <span className="text-muted">
                              {systemShortFor("escalation", systemKey)} said{" "}
                              <span className={missed ? "text-green" : "text-amber"}>{missed ? "auto-handle" : reasonLabel(pred.escalation?.reason_code) || "escalate"}</span>
                              {pred.intent !== row.gold.intent && <span> · read it as {pred.intent}</span>}
                              {typeof pred.intent_confidence === "number" && <span className="t-mono"> · conf {fixed(pred.intent_confidence, 2)}</span>}
                            </span>
                          )}
                        </div>
                      </>
                    ) : (
                      <p className="text-[13px] text-faint italic">Not in this export — open the golden explorer for the full record.</p>
                    )}
                  </div>
                  <ArrowUpRight className="mt-0.5 size-4 shrink-0 text-faint" aria-hidden="true" />
                </Link>
              </li>
            );
          })}
        </ol>
      )}

      {ids.length > limit && (
        <button type="button" className="btn btn-ghost btn-sm self-start" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
          {expanded ? "Show fewer" : `Show all ${int(ids.length)}`}
        </button>
      )}
    </section>
  );
}
