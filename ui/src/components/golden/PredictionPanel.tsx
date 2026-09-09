import { Check, ChevronRight, X } from "lucide-react";

import { Chip } from "@/components/Chip";
import { ConfidenceBar } from "@/components/ConfidenceBar";
import { DecisionPill } from "@/components/DecisionPill";
import { EmptyState } from "@/components/EmptyState";
import { EvidenceCard } from "@/components/EvidenceCard";
import { IntentBadge } from "@/components/IntentBadge";
import { ReplyPreview } from "@/components/ReplyPreview";
import { compact as compactNumber, int, ms as formatMs } from "@/lib/format";
import { intentShort } from "@/lib/intents";
import { ruleFlagLabel, SENTIMENT_LABELS, systemShort } from "@/lib/labels";
import type { MergedGoldenExample, SystemId } from "@/lib/types";

import { compareRow } from "./query";
import { sentimentTone } from "./sentiment";

export interface PredictionPanelProps {
  row: MergedGoldenExample;
  system: SystemId;
  /** Confidence threshold drawn on the bar; omitted when the summary has not loaded. */
  threshold?: number;
}

const EMPTY_REPLY: Partial<Record<SystemId, string>> = {
  llm_zero_shot: "The zero-shot baseline classifies only; it drafts no reply.",
};

/** One system's full output for the row: intent vs gold, confidence, decision and reason, reply, evidence, trace. */
export function PredictionPanel({ row, system, threshold }: PredictionPanelProps) {
  const cmp = compareRow(row, system);
  const pred = cmp.pred;

  if (!pred) {
    return <EmptyState compact title={`No ${systemShort(system)} prediction`} description="This system produced no row for the example (for instance a cache miss while replaying without an API key)." />;
  }

  const cited = pred.evidence.filter((e) => e.cited).length;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex min-w-0 items-center gap-2">
          {cmp.intentCorrect ? <Check className="size-4 shrink-0 text-green" aria-label="intent matches gold" /> : <X className="size-4 shrink-0 text-rose" aria-label="intent differs from gold" />}
          <IntentBadge id={pred.intent} wrong={cmp.intentCorrect === false} />
        </span>
        <span className="flex items-center gap-2">
          {pred.secondary_intent && (
            <Chip size="sm" mono title="secondary intent">
              + {pred.secondary_intent}
            </Chip>
          )}
          <Chip size="sm" dot tone={sentimentTone(pred.sentiment)}>
            {SENTIMENT_LABELS[pred.sentiment]}
          </Chip>
        </span>
      </div>
      {cmp.intentCorrect === false && (
        <p className="text-[12px] text-rose">
          Gold intent is {intentShort(row.gold.intent)} <span className="t-mono">({row.gold.intent})</span>.
        </p>
      )}

      <ConfidenceBar value={pred.intent_confidence} threshold={threshold} />

      <div className="hairline-t flex flex-col gap-2 pt-4">
        <div className="flex flex-wrap items-center gap-2">
          <DecisionPill decision={pred.decision} reasonCode={pred.escalation?.reason_code ?? null} showReason />
          {pred.trace?.forced_by_rules && (
            <Chip size="sm" tone="amber" mono title="A deterministic rule forced this decision; the model could not override it">
              forced by rules
            </Chip>
          )}
          {cmp.decisionError === null ? (
            <Chip size="sm" tone="green" dot>
              matches gold
            </Chip>
          ) : (
            <Chip size="sm" tone={cmp.decisionError === "missed" ? "rose" : "amber"} dot>
              {cmp.decisionError === "missed" ? "missed escalation" : "unnecessary escalation"}
            </Chip>
          )}
        </div>
        <p className="text-[13px] leading-relaxed text-muted">{pred.escalation?.reason ?? "Auto-handled: no rule fired and no escalation reason was recorded."}</p>
        {pred.rule_flags.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label="Rule flags">
            {pred.rule_flags.map((f) => (
              <li key={f}>
                <span className="tag" title={ruleFlagLabel(f)}>
                  {f}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ReplyPreview compact text={pred.reply_draft} emptyLabel={EMPTY_REPLY[system] ?? "No reply drafted"} />

      {pred.grounding_notes && (
        <div className="region-plain px-4 py-3">
          <p className="eyebrow mb-1.5">grounding notes</p>
          <p className="text-[13px] leading-relaxed text-muted">{pred.grounding_notes}</p>
          {pred.citations.length > 0 && <p className="t-mono mt-1.5 text-[12px] text-faint">cites {pred.citations.join(", ")}</p>}
        </div>
      )}

      {pred.evidence.length === 0 ? (
        <p className="text-[12px] text-faint">No retrieval for this system.</p>
      ) : (
        <details className="group" open={pred.evidence.length <= 2}>
          <summary className="flex cursor-pointer list-none items-center gap-1 text-[12px] text-muted hover:text-text [&::-webkit-details-marker]:hidden">
            <ChevronRight className="size-3.5 transition-transform duration-[120ms] group-open:rotate-90" aria-hidden="true" />
            evidence · {int(pred.evidence.length)} retrieved, {int(cited)} cited
          </summary>
          <ul className="mt-3 flex flex-col gap-2">
            {pred.evidence.map((ev, i) => (
              <li key={ev.thread_id}>
                <EvidenceCard evidence={ev} rank={i + 1} compact />
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Chip size="sm" mono>
          {pred.model}
        </Chip>
        <Chip size="sm" mono tone={pred.cached ? "violet" : "green"} title={pred.cached ? "Served from the committed LLM cache" : "Fresh model call"}>
          {pred.cached ? "cached" : "live call"}
        </Chip>
        <Chip size="sm" mono>
          {formatMs(pred.latency_ms)}
        </Chip>
        {pred.trace && pred.trace.prompt_tokens > 0 && (
          <Chip size="sm" mono title="prompt → output tokens">
            {compactNumber(pred.trace.prompt_tokens)} → {int(pred.trace.output_tokens)} tok
          </Chip>
        )}
      </div>
    </div>
  );
}
