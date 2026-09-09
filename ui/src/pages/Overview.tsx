import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { Callout } from "@/components/Callout";
import { ErrorState } from "@/components/ErrorState";
import { MetricTile } from "@/components/MetricTile";
import { PageTransition, Reveal } from "@/components/PageTransition";
import { Skeleton, SkeletonText } from "@/components/Skeleton";
import { Tooltip } from "@/components/Tooltip";
import { useAsync } from "@/hooks/useAsync";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { getResults } from "@/lib/api";
import { cx } from "@/lib/cx";
import { ciPct, fixed, int, pct } from "@/lib/format";
import { intentMeta } from "@/lib/intents";
import { systemShort } from "@/lib/labels";
import { systemColor } from "@/lib/palette";
import type { EvalSummary } from "@/lib/types";

const DATASET_FALLBACK = { n_openers: 26068, date_from: "2017-04-07", date_to: "2017-12-13" };

/** The hero ornament: the test set's intent mix, one bar per intent, like a level meter. Data, not decoration. */
function IntentMeter({ support, labels }: { support: Record<string, number>; labels: string[] }) {
  const reduced = useReducedMotion();
  const max = Math.max(1, ...labels.map((l) => support[l] ?? 0));
  const total = labels.reduce((acc, l) => acc + (support[l] ?? 0), 0);
  return (
    <figure className="flex flex-col gap-3" aria-label={`Intent mix of the ${total} test messages`}>
      <ul className="flex h-[132px] items-end gap-[6px] sm:gap-2" role="list">
        {labels.map((id, i) => {
          const n = support[id] ?? 0;
          const meta = intentMeta(id);
          return (
            <li key={id} className="flex h-full flex-1 items-end">
              <Tooltip content={<span><span className="block text-text">{meta.name}</span><span className="t-mono text-muted">{n} of {total} · {pct(n / total)}</span></span>}>
                <motion.span
                  tabIndex={0}
                  role="img"
                  aria-label={`${meta.name}: ${n} messages`}
                  className="block w-full min-w-[10px] rounded-t-[3px] rounded-b-[2px]"
                  style={{ background: meta.color, height: `${(n / max) * 100}%` }}
                  initial={reduced ? false : { scaleY: 0, opacity: 0 }}
                  animate={{ scaleY: 1, opacity: 1 }}
                  transition={{ duration: 0.5, delay: 0.15 + i * 0.03, ease: [0.2, 0.8, 0.2, 1] }}
                />
              </Tooltip>
            </li>
          );
        })}
      </ul>
      <figcaption className="eyebrow flex items-center justify-between">
        <span>what the test set asks about</span>
        <span className="text-faint">{int(total)} messages</span>
      </figcaption>
    </figure>
  );
}

interface CompareRow {
  id: string;
  value: number;
  ci?: [number, number];
}

/** Agent vs baselines on one task: horizontal bars, agent green, baselines violet. */
function CompareStrip({ title, rows, format, note }: { title: string; rows: CompareRow[]; format: (v: number) => string; note?: string }) {
  const max = Math.max(...rows.map((r) => r.value), 1e-9);
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <h3 className="t-display-20 text-text">{title}</h3>
      <ul className="flex flex-col gap-2">
        {rows.map((r) => (
          <li key={r.id} className="grid grid-cols-[minmax(0,128px)_1fr_48px] items-center gap-3 text-[13px]">
            <span className={cx("truncate", r.id === "agent" ? "font-medium text-text" : "text-muted")} title={systemShort(r.id)}>
              {systemShort(r.id)}
            </span>
            <span className="relative h-1.5 overflow-hidden rounded-full bg-surface-2">
              <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${(r.value / max) * 100}%`, background: systemColor(r.id) }} />
            </span>
            <span className={cx("t-mono text-right", r.id === "agent" ? "text-text" : "text-muted")}>{format(r.value)}</span>
          </li>
        ))}
      </ul>
      {note && <p className="text-[12px] leading-snug text-faint">{note}</p>}
    </div>
  );
}

/** Rows for the given systems, in `order`, skipping systems missing from the summary. */
function pickRows<T>(systems: Record<string, T>, order: string[], value: (s: T) => number): CompareRow[] {
  return order.flatMap((id) => {
    const s = systems[id];
    return s ? [{ id, value: value(s) }] : [];
  });
}

function OverviewSkeleton() {
  return (
    <div className="flex flex-col gap-10" aria-busy="true" aria-label="Loading overview">
      <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr] lg:items-end">
        <div className="flex flex-col gap-5">
          <Skeleton height={88} width={320} radius={10} />
          <Skeleton height={22} width="70%" />
          <SkeletonText lines={2} lastWidth="55%" />
        </div>
        <Skeleton height={160} radius={8} />
      </div>
      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <MetricTile key={i} label="loading" value={0} loading />
        ))}
      </div>
      <Skeleton height={220} radius={10} />
    </div>
  );
}

function OverviewContent({ summary }: { summary: EvalSummary }) {
  const { meta, headline, intent, escalation, reply_quality: reply } = summary;
  const dataset = meta.dataset ?? DATASET_FALLBACK;
  const yearFrom = dataset.date_from.slice(0, 4);
  const nnGap = headline.judge_overall_mean - headline.judge_overall_mean_nn;
  const caveats = meta.caveats ?? [];
  const escalate = escalation.systems.agent;

  return (
    <PageTransition className="flex flex-col gap-12">
      <Reveal>
        <section className="hairline-b grid gap-10 pb-12 lg:grid-cols-[1.25fr_1fr] lg:items-end">
          <div className="min-w-0">
            <h1 className="t-display t-display-96 t-italic text-text">Cadence</h1>
            <p className="mt-4 text-[20px] leading-snug text-text sm:text-[24px]">An evaluated AI support agent for @SpotifyCares.</p>
            <p className="measure mt-4 text-[15px] leading-relaxed text-muted">
              It drafts public replies grounded in {int(dataset.n_openers)} real SpotifyCares conversations from {yearFrom}, decides whether a
              human must take over, and reports how often it gets both wrong. Every number below comes from {int(meta.n_test)} held-out,
              hand-labelled tweets; {int(meta.n_dev)} more were used only to tune the threshold.
            </p>
          </div>
          <IntentMeter support={intent.support} labels={intent.labels} />
        </section>
      </Reveal>

      <Reveal>
        <section aria-labelledby="headline" className="flex flex-col gap-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="headline" className="eyebrow">
              headline numbers · test split n={meta.n_test} · 95% bootstrap CI
            </h2>
            <Link to="/eval" className="link text-[13px] text-muted">
              Full evaluation
            </Link>
          </div>
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
            <MetricTile
              label="intent macro-F1"
              value={headline.intent_macro_f1}
              format={(v) => fixed(v, 2)}
              ci={headline.ci95.intent_macro_f1}
              hint="Unweighted mean of per-intent F1 across every intent, so rare intents count as much as common ones."
            />
            <MetricTile
              label="escalation recall"
              value={headline.escalation_recall}
              format={(v) => pct(v)}
              ci={headline.ci95.escalation_recall}
              ciFormat={ciPct}
              tone="amber"
              hint="Share of tweets a human should handle that the agent did escalate. The costly error is the miss, so this is the number to watch."
              sub={escalate ? <span className="t-mono text-rose">{escalate.missed_escalations} missed</span> : undefined}
            />
            <MetricTile
              label="auto-handle rate"
              value={headline.auto_handle_rate}
              format={(v) => pct(v)}
              ci={headline.ci95.auto_handle_rate}
              ciFormat={ciPct}
              tone="green"
              hint="Share of tweets the agent would post a reply to without human review."
            />
            <MetricTile
              label="judge overall · 1–5"
              value={headline.judge_overall_mean}
              format={(v) => fixed(v, 2)}
              ci={headline.ci95.judge_overall_mean}
              tone="sky"
              delta={{ value: nnGap, label: "vs nearest-neighbour reply" }}
              hint={`Mean holistic score from ${meta.judge_model} across grounded, resolves, tone and safe. The nearest-neighbour baseline reuses the closest historical brand reply verbatim.`}
            />
          </div>
        </section>
      </Reveal>

      {caveats.length > 0 && (
        <Reveal>
          <Callout title="What is misleading about these numbers" eyebrow="read before quoting them">
            <ul>
              {caveats.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </Callout>
        </Reveal>
      )}

      <Reveal>
        <section aria-labelledby="baselines" className="flex flex-col gap-5">
          <h2 id="baselines" className="eyebrow">
            agent against the baselines · same {meta.n_test} tweets
          </h2>
          <div className="region grid gap-8 px-6 py-6 md:grid-cols-3 md:gap-10">
            <CompareStrip
              title="Intent macro-F1"
              format={(v) => fixed(v, 2)}
              rows={pickRows(intent.systems, ["agent", "llm_zero_shot", "simple_tfidf_lr", "simple_keyword", "trivial_majority"], (s) => s.macro_f1)}
              note="Zero-shot uses the same taxonomy in the prompt but no retrieval; TF-IDF is out-of-fold over the golden set."
            />
            <CompareStrip
              title="Escalation recall"
              format={(v) => pct(v)}
              rows={pickRows(escalation.systems, ["agent", "llm_zero_shot", "simple_rules", "trivial_always_escalate", "trivial_never_escalate"], (s) => s.recall)}
              note={`Always-escalate is perfect recall with a ${pct(escalation.systems.trivial_always_escalate?.auto_handle_rate ?? 0)} auto-handle rate; the agent keeps ${pct(headline.auto_handle_rate)} of tweets self-served.`}
            />
            <CompareStrip
              title="Reply quality · judge overall"
              format={(v) => fixed(v, 2)}
              rows={Object.entries(reply.systems).map(([id, s]) => ({ id, value: s.mean.overall })).sort((a, b) => b.value - a.value)}
              note={`Agent wins ${pct(reply.pairwise.agent_vs_nn_win_rate)} of head-to-heads against the nearest-neighbour reply and ${pct(reply.pairwise.agent_vs_trivial_win_rate)} against the template.`}
            />
          </div>
        </section>
      </Reveal>

      <Reveal>
        <section className="region-plain flex flex-col gap-5 px-6 py-7 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div className="min-w-0">
            <h2 className="t-display-28 t-italic text-text">Now poke at it.</h2>
            <p className="measure mt-1.5 text-[14px] text-muted">
              Run the agent on real tweets and watch the rules fire, the evidence arrive and the reply get drafted, step by step.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Link to="/failures" className="btn">
              Where it fails
            </Link>
            <Link to="/agent" className="btn btn-primary">
              Open the playground
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </div>
        </section>
      </Reveal>

      <p className="t-mono text-[12px] text-faint">
        results generated {meta.generated_at.slice(0, 10)} · agent {meta.agent_model} · judge {meta.judge_model} · cache hit rate {pct(meta.cache_hit_rate)} · sha{" "}
        {meta.git_sha.slice(0, 9)}
      </p>
    </PageTransition>
  );
}

export default function Overview() {
  useDocumentTitle("Overview");
  const { data, error, loading, reload } = useAsync(getResults, []);

  if (loading) return <OverviewSkeleton />;
  if (error || !data) return <ErrorState error={error} what="the evaluation results" onRetry={reload} />;
  return <OverviewContent summary={data} />;
}
