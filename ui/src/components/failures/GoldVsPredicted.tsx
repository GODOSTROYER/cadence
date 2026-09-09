import { DecisionPill } from "@/components/DecisionPill";
import { IntentBadge } from "@/components/IntentBadge";
import { cx } from "@/lib/cx";
import type { Decision, FailureExample } from "@/lib/types";

interface DecisionOutcome {
  label: string;
  tone: "rose" | "amber";
}

/** Name the decision error the way the evaluation does: the missed escalation is the costly one. */
function decisionOutcome(gold: Decision, pred: Decision): DecisionOutcome | null {
  if (gold === pred) return null;
  return gold === "escalate" ? { label: "missed escalation", tone: "rose" } : { label: "needless escalation", tone: "amber" };
}

const TONE_TAG: Record<DecisionOutcome["tone"], string> = {
  rose: "border-rose/40 text-rose",
  amber: "border-amber/40 text-amber",
};

export interface GoldVsPredictedProps {
  example: FailureExample;
  className?: string;
}

/** Gold labels above the prediction, with the mismatch named: wrong intent, missed or needless escalation. */
export function GoldVsPredicted({ example, className }: GoldVsPredictedProps) {
  const intentWrong = example.gold_intent !== example.pred_intent;
  const outcome = decisionOutcome(example.gold_decision, example.pred_decision);
  return (
    <dl className={cx("grid grid-cols-[72px_minmax(0,1fr)] gap-x-3 gap-y-2.5 text-[13px]", className)}>
      <dt className="t-mono pt-0.5 text-[12px] text-faint">gold</dt>
      <dd className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <IntentBadge id={example.gold_intent} size="sm" compact className="shrink-0" />
        <DecisionPill decision={example.gold_decision} size="sm" quiet />
      </dd>
      <dt className="t-mono pt-0.5 text-[12px] text-faint">predicted</dt>
      <dd className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <IntentBadge id={example.pred_intent} size="sm" compact wrong={intentWrong} className="shrink-0" />
        <DecisionPill decision={example.pred_decision} size="sm" quiet={outcome === null} />
        {intentWrong && <span className="tag border-rose/40 text-rose">wrong intent</span>}
        {outcome && <span className={cx("tag", TONE_TAG[outcome.tone])}>{outcome.label}</span>}
        {!intentWrong && !outcome && <span className="tag">labels correct · the reply is the failure</span>}
      </dd>
    </dl>
  );
}
