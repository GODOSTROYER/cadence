import { Check, X } from "lucide-react";
import type { ReactNode } from "react";

import { Chip } from "@/components/Chip";
import { DecisionPill } from "@/components/DecisionPill";
import { IntentBadge } from "@/components/IntentBadge";
import { cx } from "@/lib/cx";
import { reasonLabel, SENTIMENT_LABELS } from "@/lib/labels";
import type { Annotation, MergedGoldenExample } from "@/lib/types";

import { sentimentTone } from "./sentiment";

export interface GoldLabelsPanelProps {
  row: MergedGoldenExample;
}

interface FieldRow {
  label: string;
  a: ReactNode;
  b: ReactNode;
  same: boolean;
}

function yesNo(v: boolean): string {
  return v ? "yes" : "no";
}

function fieldRows(a: Annotation, b: Annotation): FieldRow[] {
  return [
    {
      label: "intent",
      same: a.intent === b.intent,
      a: <IntentBadge id={a.intent} size="sm" compact showName={false} />,
      b: <IntentBadge id={b.intent} size="sm" compact showName={false} />,
    },
    { label: "escalate", same: a.should_escalate === b.should_escalate, a: yesNo(a.should_escalate), b: yesNo(b.should_escalate) },
    {
      label: "reason",
      same: a.escalation_reason_code === b.escalation_reason_code,
      a: reasonLabel(a.escalation_reason_code) || "—",
      b: reasonLabel(b.escalation_reason_code) || "—",
    },
    { label: "sentiment", same: a.sentiment === b.sentiment, a: SENTIMENT_LABELS[a.sentiment], b: SENTIMENT_LABELS[b.sentiment] },
    { label: "media-only", same: a.media_only === b.media_only, a: yesNo(a.media_only), b: yesNo(b.media_only) },
  ];
}

/** Adjudicated gold labels, then the two annotation passes side by side with disagreements in amber. */
export function GoldLabelsPanel({ row }: GoldLabelsPanelProps) {
  const { gold, agreement, adjudicated } = row;
  const rows = fieldRows(row.annotations.a, row.annotations.b);

  return (
    <div className="flex flex-col gap-4">
      <dl className="grid gap-x-6 gap-y-4 text-[13px] sm:grid-cols-2">
        <div>
          <dt className="text-faint">Intent</dt>
          <dd className="mt-1">
            <IntentBadge id={gold.intent} />
          </dd>
          {gold.secondary_intent && (
            <dd className="mt-1 text-[12px] text-muted">
              secondary <span className="t-mono">{gold.secondary_intent}</span>
            </dd>
          )}
        </div>
        <div>
          <dt className="text-faint">Decision</dt>
          <dd className="mt-1">
            <DecisionPill size="sm" decision={gold.should_escalate ? "escalate" : "auto_handle"} reasonCode={gold.escalation_reason_code} showReason reason={gold.should_escalate ? `A human must take this: ${reasonLabel(gold.escalation_reason_code) || "escalation"}.` : "Grounded self-serve reply can post without review."} />
          </dd>
        </div>
        <div>
          <dt className="text-faint">Sentiment</dt>
          <dd className="mt-1">
            <Chip size="sm" dot tone={sentimentTone(gold.sentiment)}>
              {SENTIMENT_LABELS[gold.sentiment]}
            </Chip>
          </dd>
        </div>
        <div>
          <dt className="text-faint">Media-only</dt>
          <dd className="mt-1 text-text">{gold.media_only ? "yes — the text alone does not identify the issue" : "no"}</dd>
        </div>
      </dl>

      {gold.notes && (
        <p className="text-[13px] leading-relaxed text-muted italic">
          <span className="text-faint not-italic">{adjudicated ? "adjudication note" : "notes"} · </span>
          {gold.notes}
        </p>
      )}

      <div className="table-wrap">
        <table className="table text-[12px] [&_td]:py-2 [&_th]:py-2">
          <caption className="sr-only">The two annotation passes compared field by field</caption>
          <thead>
            <tr>
              <th scope="col">Field</th>
              <th scope="col">Pass A</th>
              <th scope="col">Pass B</th>
              <th scope="col" className="text-center">
                Agree
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <td className="text-faint">{r.label}</td>
                <td className={cx(!r.same && "text-amber")}>{r.a}</td>
                <td className={cx(!r.same && "text-amber")}>{r.b}</td>
                <td className="text-center">
                  {r.same ? <Check className="inline size-3.5 text-green" aria-label="agree" /> : <X className="inline size-3.5 text-amber" aria-label="disagree" />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <Chip size="sm" dot tone={agreement.intent ? "green" : "amber"}>
          intent {agreement.intent ? "agreed" : "disagreed"}
        </Chip>
        <Chip size="sm" dot tone={agreement.should_escalate ? "green" : "amber"}>
          escalation {agreement.should_escalate ? "agreed" : "disagreed"}
        </Chip>
        {adjudicated ? (
          <Chip size="sm" tone="amber" mono title="A disagreement was resolved in a third pass; the gold labels above are the resolution.">
            adjudicated
          </Chip>
        ) : (
          <span className="text-faint">both passes agreed, no adjudication</span>
        )}
        <span className="t-mono ml-auto text-faint" title="Stratified sampling bucket">
          {row.sampling_bucket}
        </span>
      </div>
    </div>
  );
}
