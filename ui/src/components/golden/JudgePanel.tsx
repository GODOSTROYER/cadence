import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { cx } from "@/lib/cx";
import { formatDateTime } from "@/lib/format";
import { JUDGE_DIMENSION_HINTS, JUDGE_DIMENSION_LABELS, JUDGE_FLAG_LABELS, JUDGE_FLAGS, systemLabel, systemShort, VERDICT_LABELS } from "@/lib/labels";
import { systemColor } from "@/lib/palette";
import type { JudgedSystemId, MergedGoldenExample } from "@/lib/types";

import { ScoreMark } from "./ScoreMark";
import { verdictTone } from "./sentiment";

export interface JudgePanelProps {
  row: MergedGoldenExample;
}

const JUDGED: readonly JudgedSystemId[] = ["agent", "simple", "trivial"];
const SUB_DIMENSIONS = ["grounded", "resolves", "tone", "safe"] as const;

/** The judge's verdict, scores, flags and rationale for every judged system on this example. */
export function JudgePanel({ row }: JudgePanelProps) {
  const systems = JUDGED.filter((s) => row.judge[s]);

  if (systems.length === 0) {
    return <EmptyState compact title="Not judged" description={row.split === "dev" ? "Dev-split examples tune the threshold and prompt; only the test split is judged." : "No judge record for this example in the export."} />;
  }

  return (
    <ul className="flex flex-col gap-3" aria-label="Judge scores per system">
      {systems.map((s) => {
        const j = row.judge[s];
        if (!j) return null;
        const flags = JUDGE_FLAGS.filter((f) => j.flags[f]);
        return (
          <li key={s} className={cx("region-plain flex flex-col gap-3 px-4 py-3", s === "agent" ? "border-green/30" : "border-border")}>
            <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
              <span className="flex min-w-0 items-center gap-2">
                <span aria-hidden="true" className="size-2 shrink-0 rounded-full" style={{ background: systemColor(s) }} />
                <span className="text-[13px] font-medium text-text">{systemShort(s)}</span>
                <span className="hidden truncate text-[12px] text-faint sm:inline">{systemLabel(s)}</span>
              </span>
              <span className="flex items-center gap-3">
                <Chip size="sm" tone={verdictTone(j.verdict)} dot>
                  {VERDICT_LABELS[j.verdict]}
                </Chip>
                <ScoreMark value={j.scores.overall} size="lg" label={JUDGE_DIMENSION_LABELS.overall} />
              </span>
            </header>
            <dl className="grid grid-cols-4 gap-2">
              {SUB_DIMENSIONS.map((d) => (
                <div key={d} title={JUDGE_DIMENSION_HINTS[d]}>
                  <dt className="text-[11px] text-faint">{JUDGE_DIMENSION_LABELS[d]}</dt>
                  <dd className="mt-0.5">
                    <ScoreMark value={j.scores[d]} label={JUDGE_DIMENSION_LABELS[d]} />
                  </dd>
                </div>
              ))}
            </dl>
            {flags.length > 0 && (
              <ul className="flex flex-wrap gap-1.5" aria-label="Judge flags">
                {flags.map((f) => (
                  <li key={f}>
                    <span className="tag border-rose/40 text-rose">{JUDGE_FLAG_LABELS[f]}</span>
                  </li>
                ))}
              </ul>
            )}
            {j.rationale && <blockquote className="border-l border-border pl-3 text-[13px] leading-relaxed text-muted">{j.rationale}</blockquote>}
            <p className="t-mono text-[11px] text-faint">
              rated by {j.rater} · {formatDateTime(j.rated_at)}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
