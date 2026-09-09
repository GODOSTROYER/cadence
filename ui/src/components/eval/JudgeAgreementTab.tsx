import { UserRoundCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { AgreementScatter } from "@/components/AgreementScatter";
import { Callout } from "@/components/Callout";
import { EmptyState } from "@/components/EmptyState";
import { IS_STATIC } from "@/lib/api";
import { cx } from "@/lib/cx";
import { delta, fixed, int, pct } from "@/lib/format";
import { JUDGE_DIMENSION_HINTS, JUDGE_DIMENSION_LABELS, JUDGE_DIMENSIONS } from "@/lib/labels";
import type { EvalSummary, JudgeAgreementBlock } from "@/lib/types";

import { extra, fmtMaybe, isNum, type Maybe } from "./maybe";
import { StatTile } from "./StatTile";

export interface JudgeAgreementTabProps {
  summary: EvalSummary;
}

/** Landis & Koch bands, used only as a reading aid in the tile hint. */
function kappaBand(k: Maybe<number>): string {
  if (!isNum(k)) return "undefined";
  if (k < 0.2) return "slight";
  if (k < 0.4) return "fair";
  if (k < 0.6) return "moderate";
  if (k < 0.8) return "substantial";
  return "almost perfect";
}

/** κ / ρ / exact / within-1 tiles, human-vs-judge scatter, per-dimension table and the protocol note. */
export function JudgeAgreementTab({ summary }: JudgeAgreementTabProps) {
  const block = summary.judge_agreement as JudgeAgreementBlock | null;
  const judge = summary.meta.judge_model ?? "the judge model";

  if (!block || !Array.isArray(block.pairs) || block.pairs.length === 0) {
    return (
      <EmptyState
        icon={<UserRoundCheck />}
        title="Human ratings are pending"
        description={
          <>
            Judge agreement compares {judge}'s scores with a person's blind ratings of the same replies. No rated pairs exist yet, so κ, ρ and the scatter cannot be computed. The protocol: {int(60)} (message, reply) pairs, 20 per system, system identity hidden behind an A/B/C alias, scored on the same five dimensions; the block fills in once ratings are saved and the evaluation re-runs.
          </>
        }
        action={
          IS_STATIC ? undefined : (
            <Link to="/rate" className="btn btn-primary">
              Rate replies
            </Link>
          )
        }
      />
    );
  }

  const bias = extra<number>(block, "judge_minus_human_mean");
  const systems = [...new Set(block.pairs.map((p) => p.system))];

  return (
    <div className="flex flex-col gap-8">
      <p className="eyebrow">
        {int(block.n)} human-rated replies · {systems.length} systems · human vs {judge} on the same 1–5 scale
      </p>

      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          size="md"
          label="weighted κ · overall"
          value={block.weighted_kappa_overall}
          format={(v) => fixed(v, 2)}
          tone="sky"
          hint={`Quadratic-weighted Cohen's kappa on the overall score: ${kappaBand(block.weighted_kappa_overall)} agreement (Landis & Koch). Chance-corrected; a two-point miss costs four times a one-point miss.`}
          sub={<span>{kappaBand(block.weighted_kappa_overall)} agreement</span>}
        />
        <StatTile size="md" label="Spearman ρ · overall" value={block.spearman_overall} format={(v) => fixed(v, 2)} tone="sky" hint="Rank correlation of human and judge overall scores. Undefined (shown as a dash) when either rater gives every reply the same score." />
        <StatTile size="md" label="exact agreement" value={block.exact_agreement} format={(v) => pct(v)} hint="Share of pairs where human and judge gave the identical overall score." />
        <StatTile
          size="md"
          label="within one point"
          value={block.within_one}
          format={(v) => pct(v)}
          hint="Share of pairs where the two overall scores differ by at most one."
          sub={isNum(bias) ? <span>judge − human <span className={cx("t-mono", Math.abs(bias) < 0.25 ? "text-muted" : "text-amber")}>{delta(bias, 2)}</span> on average</span> : undefined}
        />
      </div>

      <div className="grid gap-8 xl:grid-cols-[1.3fr_1fr]">
        <section className="region px-5 py-5" aria-label="Human versus judge scatter">
          <AgreementScatter pairs={block.pairs} title="Human against judge, overall score" subtitle="Each point is one rated reply, jittered so ties stay visible; the dashed diagonal is perfect agreement. Colour is the system that wrote the reply." />
        </section>

        <section className="flex min-w-0 flex-col gap-3" aria-label="Agreement per dimension">
          <h3 className="t-display-20 text-text">Agreement per dimension</h3>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Dimension</th>
                  <th scope="col" className="num">weighted κ</th>
                  <th scope="col" className="num">Spearman ρ</th>
                  <th scope="col" className="num hidden sm:table-cell">n</th>
                </tr>
              </thead>
              <tbody>
                {JUDGE_DIMENSIONS.map((d) => {
                  const row = block.per_dimension[d] as { weighted_kappa: Maybe<number>; spearman: Maybe<number>; n?: number } | undefined;
                  return (
                    <tr key={d}>
                      <td className="whitespace-nowrap" title={JUDGE_DIMENSION_HINTS[d]}>
                        <span className={cx(d === "overall" ? "font-medium text-text" : "text-text")}>{JUDGE_DIMENSION_LABELS[d]}</span>
                      </td>
                      <td className={cx("num", isNum(row?.weighted_kappa) ? (row!.weighted_kappa! < 0.4 ? "text-amber" : "text-text") : "text-faint")} title={row ? `${kappaBand(row.weighted_kappa)} agreement` : undefined}>
                        {fmtMaybe(row?.weighted_kappa, (v) => fixed(v, 2))}
                      </td>
                      <td className={cx("num", isNum(row?.spearman) ? "text-text" : "text-faint")} title={isNum(row?.spearman) ? undefined : "Undefined: one rater's scores are constant on this dimension"}>
                        {fmtMaybe(row?.spearman, (v) => fixed(v, 2))}
                      </td>
                      <td className="num hidden text-muted sm:table-cell">{isNum(row?.n) ? int(row!.n!) : int(block.n)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[12px] leading-snug text-faint">A dash means the statistic is undefined on this data (for example, every safety score was a 5). Low κ on tone is expected: it is the most subjective dimension.</p>
        </section>
      </div>

      <Callout tone="sky" eyebrow="protocol" title="How the judge was calibrated">
        <ul>
          <li>
            <strong>Blind, stratified sample.</strong> {int(block.n)} (message, reply) pairs, 20 per system, presented one at a time with the system identity hidden behind an A/B/C alias resolved server-side.
          </li>
          <li>
            <strong>Same rubric.</strong> The human scored grounded, resolves, tone, safe and overall on the same 1–5 scale and the same three flags as {judge}; the judge's rating for each pair was produced earlier, in its comparative call over all three replies.
          </li>
          <li>
            <strong>Statistics.</strong> Quadratic-weighted Cohen's κ, Spearman ρ, exact and within-one agreement on overall; κ and ρ per dimension. Undefined values are reported as null, never as zero.
          </li>
          <li>
            <strong>What it does not show.</strong> {int(block.n)} pairs bound κ loosely, and the human is the project author who also wrote the rubric; treat the judge as a consistent scorer aligned with one reader, not as ground truth.
          </li>
        </ul>
      </Callout>
    </div>
  );
}
