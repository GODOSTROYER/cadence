import { Scale } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ScoreDistribution, type ScoreSeries } from "@/components/ScoreDistribution";
import { SegmentedControl } from "@/components/SegmentedControl";
import { cx } from "@/lib/cx";
import { ci as formatCi, fixed, int, pct } from "@/lib/format";
import { JUDGE_DIMENSION_HINTS, JUDGE_DIMENSION_LABELS, JUDGE_DIMENSIONS, JUDGE_FLAG_LABELS, JUDGE_FLAGS, systemLabel, systemShort } from "@/lib/labels";
import type { EvalSummary, JudgeDimension, JudgeFlag, MergedGoldenExample, ReplyQualityBlock, ReplyQualitySystem } from "@/lib/types";

import { ciOf, extra, fmtMaybe, isNum, type Maybe } from "./maybe";
import { StatTile } from "./StatTile";
import { judgedSystem, orderSystems } from "./systemKeys";

export interface ReplyQualityTabProps {
  summary: EvalSummary;
  golden: MergedGoldenExample[] | null;
}

type Dist = [number, number, number, number, number];

const EMPTY_DIST: Dist = [0, 0, 0, 0, 0];

/** Column headers short enough for the half-width table; the full label sits in the header's title. */
const FLAG_SHORT: Record<JudgeFlag, string> = {
  hallucinated_link_or_policy: "Hallucination",
  asks_sensitive_info: "Sensitive info",
  wrong_issue: "Wrong issue",
};

/** Tally 1–5 counts of one rubric dimension from the exported judge records of a judged system. */
function tallyDimension(rows: readonly MergedGoldenExample[], system: ReturnType<typeof judgedSystem>, dimension: JudgeDimension): Dist {
  const dist: Dist = [0, 0, 0, 0, 0];
  if (!system) return dist;
  for (const row of rows) {
    const score = row.judge[system]?.scores[dimension];
    if (isNum(score) && score >= 1 && score <= 5) dist[Math.round(score) - 1] = (dist[Math.round(score) - 1] ?? 0) + 1;
  }
  return dist;
}

function meanOf(system: ReplyQualitySystem, dimension: JudgeDimension): Maybe<number> {
  return (system.mean as Partial<Record<JudgeDimension, Maybe<number>>>)[dimension];
}

/** Ship-rate tiles, head-to-head win rates, score distributions per dimension, and the mean / flag tables. */
export function ReplyQualityTab({ summary, golden }: ReplyQualityTabProps) {
  const block = summary.reply_quality as ReplyQualityBlock | null;
  const [dimension, setDimension] = useState<JudgeDimension>("overall");
  const keys = useMemo(() => orderSystems(Object.keys(block?.systems ?? {})), [block]);

  const judgedRows = useMemo(() => (golden ?? []).filter((r) => r.split === "test" && Object.keys(r.judge).length > 0), [golden]);
  const canTally = judgedRows.length > 0 && keys.some((k) => judgedSystem(k));

  if (!block || keys.length === 0) {
    return (
      <EmptyState
        icon={<Scale />}
        title="No judge scores yet"
        description={
          <>
            Reply quality needs <code className="t-mono text-text">results/judge_scores.jsonl</code>. Run <code className="t-mono text-text">make judge</code> (or replay it from the committed LLM cache) and re-export; the distributions, ship rates and flag rates appear here.
          </>
        }
      />
    );
  }

  const series: ScoreSeries[] = keys.map((k) => {
    const s = block.systems[k];
    const dist: Dist = dimension === "overall" ? (s?.dist_overall ?? EMPTY_DIST) : tallyDimension(judgedRows, judgedSystem(k), dimension);
    const mean = s ? meanOf(s, dimension) : null;
    return { id: k, label: systemShort(k), dist, mean: isNum(mean) ? mean : undefined };
  });

  const pairwise = block.pairwise ?? { agent_vs_nn_win_rate: null, agent_vs_trivial_win_rate: null };
  const n = extra<number>(block.systems.agent ?? block.systems[keys[0] ?? ""], "n");

  return (
    <div className="flex flex-col gap-8">
      <p className="eyebrow">
        {summary.meta.judge_model ?? "the judge"} scores every test reply on five 1–5 dimensions{isNum(n) ? ` · ${int(n)} replies per system` : ""} · ship = overall ≥ 4 and no flags
      </p>

      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
        {keys.map((k) => {
          const s = block.systems[k];
          if (!s) return null;
          const overallCi = ciOf(s.ci95?.overall);
          return (
            <StatTile
              key={k}
              size="md"
              label={`ship rate · ${systemShort(k)}`}
              value={s.ship_rate}
              format={(v) => pct(v)}
              tone={k === "agent" ? "green" : "violet"}
              hint={`${systemLabel(k)}: share of judged replies the judge would post as-is.`}
              sub={
                <span>
                  mean overall <span className="t-mono text-text">{fmtMaybe(meanOf(s, "overall"), (v) => fixed(v, 2))}</span>
                  {overallCi && (
                    <>
                      {" "}
                      <span className="text-faint">CI</span> <span className="t-mono">{formatCi(overallCi)}</span>
                    </>
                  )}
                </span>
              }
            />
          );
        })}
      </div>

      <section className="region-plain grid gap-6 px-5 py-5 sm:grid-cols-[1fr_1fr_minmax(0,1.4fr)] sm:items-center" aria-label="Head-to-head win rates">
        <div>
          <p className="eyebrow">agent beats nearest neighbour</p>
          <p className={cx("numeral mt-2 text-[40px]", isNum(pairwise.agent_vs_nn_win_rate) ? "text-green" : "text-faint")}>{fmtMaybe(pairwise.agent_vs_nn_win_rate, (v) => pct(v))}</p>
        </div>
        <div>
          <p className="eyebrow">agent beats template</p>
          <p className={cx("numeral mt-2 text-[40px]", isNum(pairwise.agent_vs_trivial_win_rate) ? "text-green" : "text-faint")}>{fmtMaybe(pairwise.agent_vs_trivial_win_rate, (v) => pct(v))}</p>
        </div>
        <p className="text-[13px] leading-relaxed text-muted">
          Head-to-head share of test tweets where the judge ranked the agent's reply above the baseline's in the same comparative call (ties count half). The three replies are shuffled and anonymised as A/B/C in every call to blunt position bias.
        </p>
      </section>

      <section className="region flex flex-col gap-4 px-5 py-5" aria-label="Score distributions">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SegmentedControl
            label="Rubric dimension"
            size="sm"
            value={dimension}
            onChange={setDimension}
            options={JUDGE_DIMENSIONS.map((d) => ({ value: d, label: JUDGE_DIMENSION_LABELS[d], hint: JUDGE_DIMENSION_HINTS[d], disabled: d !== "overall" && !canTally }))}
          />
          <p className="text-[12px] text-faint">
            {dimension === "overall"
              ? "Counts from the summary."
              : `Counts tallied from the ${int(judgedRows.length)} exported test rows with judge records; means from the summary.`}
          </p>
        </div>
        <ScoreDistribution series={series} dimension={dimension} title={`${JUDGE_DIMENSION_LABELS[dimension]} · 1 to 5, per system`} subtitle={JUDGE_DIMENSION_HINTS[dimension]} />
      </section>

      <div className="grid gap-8 xl:grid-cols-2">
        <section className="flex min-w-0 flex-col gap-3" aria-label="Mean score per dimension">
          <h3 className="t-display-20 text-text">Mean score per dimension</h3>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">System</th>
                  {JUDGE_DIMENSIONS.map((d) => (
                    <th key={d} scope="col" className="num" title={JUDGE_DIMENSION_HINTS[d]}>
                      {JUDGE_DIMENSION_LABELS[d]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => {
                  const s = block.systems[k];
                  if (!s) return null;
                  return (
                    <tr key={k}>
                      <td className={cx("whitespace-nowrap", k === "agent" ? "font-medium text-text" : "text-muted")} title={systemLabel(k)}>
                        {systemShort(k)}
                      </td>
                      {JUDGE_DIMENSIONS.map((d) => (
                        <td key={d} className={cx("num", d === "overall" && "text-text")}>
                          {fmtMaybe(meanOf(s, d), (v) => fixed(v, 2))}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="flex min-w-0 flex-col gap-3" aria-label="Flag rates">
          <h3 className="t-display-20 text-text">Flag rates</h3>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">System</th>
                  {JUDGE_FLAGS.map((f) => (
                    <th key={f} scope="col" className="num" title={JUDGE_FLAG_LABELS[f]}>
                      {FLAG_SHORT[f]}
                    </th>
                  ))}
                  <th scope="col" className="num">Ship</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => {
                  const s = block.systems[k];
                  if (!s) return null;
                  return (
                    <tr key={k}>
                      <td className={cx("whitespace-nowrap", k === "agent" ? "font-medium text-text" : "text-muted")} title={systemLabel(k)}>
                        {systemShort(k)}
                      </td>
                      {JUDGE_FLAGS.map((f) => {
                        const rate = (s.flag_rates as Partial<Record<string, Maybe<number>>>)[f];
                        return (
                          <td key={f} className={cx("num", isNum(rate) && rate >= 0.1 ? "text-rose" : isNum(rate) && rate > 0 ? "text-amber" : "text-muted")}>
                            {fmtMaybe(rate, (v) => pct(v, 1))}
                          </td>
                        );
                      })}
                      <td className="num text-text">{fmtMaybe(s.ship_rate, (v) => pct(v))}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[12px] leading-snug text-faint">Any flag blocks a ship verdict. The template's high wrong-issue rate is by construction: one reply for every message.</p>
        </section>
      </div>
    </div>
  );
}
