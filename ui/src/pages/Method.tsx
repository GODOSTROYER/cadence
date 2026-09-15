import { DecisionPill } from "@/components/DecisionPill";
import { ErrorState } from "@/components/ErrorState";
import { IntentBadge } from "@/components/IntentBadge";
import { MetricTile } from "@/components/MetricTile";
import { PageHeader } from "@/components/PageHeader";
import { PageTransition, Reveal } from "@/components/PageTransition";
import { Skeleton, SkeletonText } from "@/components/Skeleton";
import { useAsync } from "@/hooks/useAsync";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { PipelineDiagram } from "@/components/PipelineDiagram";
import { getIntents, getPolicy, getPublicSummary } from "@/lib/api";
import { fixed, formatDate, int, pct } from "@/lib/format";
import { JUDGE_DIMENSION_HINTS, JUDGE_DIMENSION_LABELS, JUDGE_DIMENSIONS, reasonLabel } from "@/lib/labels";
import type { DatasetFacts, EscalationPolicy, IntentDefinition, PublicSummary } from "@/lib/types";

/** CONTRACT §2 measured facts, used when eval_summary.meta.dataset is absent. */
const DATASET_FALLBACK: DatasetFacts = {
  n_openers: 26068,
  n_brand_tweets: 43265,
  n_rows_total: 2811774,
  n_brands: 108,
  date_from: "2017-04-07",
  date_to: "2017-12-13",
  share_english: 0.93,
  share_with_link: 0.14,
  share_single_reply: 0.72,
  n_resolved_links: 150,
};

const MONTH = new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric", timeZone: "UTC" });

/** "2017-10" → "Oct 2017". */
function monthLabel(ym: string): string {
  const d = new Date(`${ym}-01T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? ym : MONTH.format(d);
}

const REPRODUCE_STEPS: { cmd: string; what: string; time: string }[] = [
  { cmd: "make setup", what: "Install the Python package and the UI dependencies.", time: "2 min" },
  { cmd: "make reproduce", what: "Verify archived inputs and cached receipts, then recompute historical metrics and CIs. Zero model calls; this does not execute the revised agent.", time: "seconds" },
  { cmd: "make ui && make serve", what: "Build this dashboard and serve it with the API on http://127.0.0.1:8000.", time: "2 min" },
  { cmd: "GEMINI_API_KEY=… make run judge eval", what: "Optional: rerun with fresh Gemini calls instead of the cache. Rate-limited to the free tier, so allow about an hour.", time: "optional" },
];

function MethodSkeleton() {
  return (
    <div className="flex flex-col gap-10" aria-busy="true" aria-label="Loading method">
      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <MetricTile key={i} label="loading" value={0} size="md" loading />
        ))}
      </div>
      <Skeleton height={250} radius={8} />
      <SkeletonText lines={6} />
    </div>
  );
}

function Section({ id, eyebrow, title, lede, children }: { id: string; eyebrow: string; title: string; lede?: string; children: React.ReactNode }) {
  return (
    <Reveal>
      <section id={id} aria-labelledby={`${id}-title`} className="flex flex-col gap-5 scroll-mt-6">
        <div>
          <p className="eyebrow mb-2">{eyebrow}</p>
          <h2 id={`${id}-title`} className="t-display-28 text-text">
            {title}
          </h2>
          {lede && <p className="measure-wide mt-2 text-[14px] leading-relaxed text-muted">{lede}</p>}
        </div>
        {children}
      </section>
    </Reveal>
  );
}

function MethodContent({ summary, intents, policy }: { summary: PublicSummary; intents: IntentDefinition[]; policy: EscalationPolicy }) {
  const data = summary.meta.dataset ?? DATASET_FALLBACK;
  const support = summary.intent.support;

  return (
    <PageTransition className="flex flex-col gap-14">
      <Section id="data" eyebrow="01 · the data" title="Where the agent's knowledge comes from" lede={`Kaggle's Customer Support on Twitter dump: ${int(data.n_rows_total)} tweets across ${data.n_brands} brands. Only @SpotifyCares threads are used; a customer's first tweet plus every public brand reply forms one conversation.`}>
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
          <MetricTile size="md" label="conversations" value={data.n_openers} format={(v) => int(v)} sub={<span>customer openers that got a brand reply</span>} />
          <MetricTile size="md" label="brand replies" value={data.n_brand_tweets} format={(v) => int(v)} sub={<span>{pct(data.share_single_reply)} of threads get exactly one</span>} />
          <MetricTile size="md" label="in English" value={data.share_english} format={(v) => pct(v)} sub={<span>{pct(data.share_with_link)} carry a link or image</span>} />
          <MetricTile size="md" label="golden set" value={summary.meta.n_golden} format={(v) => int(v)} sub={<span className="t-mono">{summary.meta.n_dev} dev · {summary.meta.n_test} test</span>} />
        </div>
        <dl className="region-plain grid gap-x-8 gap-y-3 px-6 py-5 text-[13px] sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <dt className="text-faint">Period</dt>
            <dd className="t-mono text-text">
              {formatDate(data.date_from)} → {formatDate(data.date_to)}
              {data.bulk_from && data.bulk_to && typeof data.bulk_share === "number" && (
                <span className="block font-sans text-muted">
                  {pct(data.bulk_share, 1)} of openers fall in {monthLabel(data.bulk_from)} – {monthLabel(data.bulk_to)}; the earlier tail is a handful of stray threads.
                </span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-faint">Cleaning</dt>
            <dd className="text-muted">Spotify handles stripped, other handles → @user, links → &lt;url&gt;, agent initials captured then removed.</dd>
          </div>
          <div>
            <dt className="text-faint">Links resolved</dt>
            <dd className="text-muted">Top {data.n_resolved_links} t.co short links followed once so replies can cite real help-article URLs.</dd>
          </div>
          <div>
            <dt className="text-faint">Sampling</dt>
            <dd className="text-muted">Historical stratified sample: two AI label passes with adjudication ({summary.annotator_agreement.n_disagreements} disagreements). The test examples were inspected across multiple runs.</dd>
          </div>
          <div>
            <dt className="text-faint">Labels</dt>
            <dd className="text-muted">Intent, should-escalate + reason code, sentiment, media-only. AI agreement κ intent {fixed(summary.annotator_agreement.intent_kappa, 2)}, escalation {fixed(summary.annotator_agreement.escalation_kappa, 2)}. No human agreement measurement.</dd>
          </div>
          <div>
            <dt className="text-faint">Leakage guard</dt>
            <dd className="text-muted">The historical run excluded each example's own thread but still had near-duplicate leakage. The revised benchmark excludes all locked threads, overlapping tweet components and near duplicates.</dd>
          </div>
        </dl>
      </Section>

      <Section id="pipeline" eyebrow="02 · the pipeline" title="One message, four steps" lede="Rules run first and can force an escalation the model cannot undo. Retrieval supplies precedent, the model drafts, and the final decision combines all three signals.">
        <div className="region px-5 py-6">
          <PipelineDiagram threshold={summary.meta.threshold} />
        </div>
      </Section>

      <Section id="taxonomy" eyebrow="03 · intent taxonomy" title={`${intents.length} intents, stable ids`} lede="Drafted from a first read of the openers, then validated against counts. Every intent carries the decision the policy expects when nothing else fires.">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Intent</th>
                <th scope="col">Covers</th>
                <th scope="col" className="hidden lg:table-cell">Example</th>
                <th scope="col">Default</th>
                <th scope="col" className="num">test n</th>
              </tr>
            </thead>
            <tbody>
              {intents.map((it) => (
                <tr key={it.id}>
                  <td className="whitespace-nowrap">
                    <IntentBadge id={it.id} compact />
                  </td>
                  <td className="max-w-[44ch] text-muted">
                    <p className="line-clamp-3 leading-snug" title={it.description}>
                      {it.description}
                    </p>
                  </td>
                  <td className="hidden max-w-[32ch] text-muted italic lg:table-cell">{it.examples[0] ? `“${it.examples[0]}”` : "—"}</td>
                  <td>
                    <DecisionPill size="sm" quiet decision={it.default_decision} reasonCode={it.default_reason_code} showReason={false} reason={it.default_reason_code ? reasonLabel(it.default_reason_code) : "Grounded self-serve reply"} />
                  </td>
                  <td className="num">{support[it.id] ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="policy" eyebrow="04 · escalation policy" title="When a human must take over" lede={`Auto-handle means the reply can post without review: grounded in brand practice, no account access, no money, no policy exception. Anything else escalates with exactly one primary reason. Messages under ${policy.min_words_for_auto_handle} words, or with confidence below ${fixed(policy.confidence_threshold, 2)}, escalate by construction.`}>
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Escalation reason codes</caption>
              <thead>
                <tr>
                  <th scope="col">Reason code</th>
                  <th scope="col">When</th>
                </tr>
              </thead>
              <tbody>
                {policy.reason_codes.map((rc) => (
                  <tr key={rc.id}>
                    <td className="whitespace-nowrap">
                      <span className="block text-text">{rc.name}</span>
                      <span className="t-mono text-[12px] text-faint">{rc.id}</span>
                    </td>
                    <td className="text-muted">{rc.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-wrap self-start">
            <table className="table">
              <caption className="sr-only">Deterministic rules</caption>
              <thead>
                <tr>
                  <th scope="col">Rule flag</th>
                  <th scope="col">Effect</th>
                  <th scope="col" className="num">patterns</th>
                </tr>
              </thead>
              <tbody>
                {policy.rules.map((r) => (
                  <tr key={r.flag}>
                    <td className="t-mono whitespace-nowrap text-text">{r.flag}</td>
                    <td className="text-muted">
                      {r.force_escalate ? (
                        <span>
                          forces <span className="text-amber">escalate</span> · {reasonLabel(r.reason_code)}
                        </span>
                      ) : (
                        "recorded only"
                      )}
                    </td>
                    <td className="num">{r.n_patterns}</td>
                  </tr>
                ))}
                {policy.soft_flags.map((s) => (
                  <tr key={s.flag}>
                    <td className="t-mono whitespace-nowrap text-muted">{s.flag}</td>
                    <td className="text-muted">soft flag · never decides on its own</td>
                    <td className="num">{s.n_patterns}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Section>

      <Section
        id="judge"
        eyebrow="05 · reply quality"
        title="How replies are judged"
        lede={`${summary.meta.judge_model} scores the agent, the nearest-neighbour reply and the template in one comparative call per example, shuffled and anonymised as A/B/C. The judge is a different model from the agent (${summary.meta.agent_model}). ${
          summary.judge_agreement && summary.judge_agreement.n > 0
            ? `A human rated ${int(summary.judge_agreement.n)} pairs blind to calibrate it.`
            : "No human ratings exist yet, so the judge is uncalibrated: its scores are LLM opinion until pairs are rated on the Rate page and the evaluation re-runs."
        }`}
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Dimension</th>
                <th scope="col">1 – 5 means</th>
              </tr>
            </thead>
            <tbody>
              {JUDGE_DIMENSIONS.map((d) => (
                <tr key={d}>
                  <td className="whitespace-nowrap text-text">{JUDGE_DIMENSION_LABELS[d]}</td>
                  <td className="text-muted">{JUDGE_DIMENSION_HINTS[d]}</td>
                </tr>
              ))}
              <tr>
                <td className="whitespace-nowrap text-text">Flags</td>
                <td className="text-muted">Hallucinated link or policy · asks for sensitive info · wrong issue. Any flag blocks a “ship” verdict.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="reproduce" eyebrow="06 · reproduce" title="Fifteen minutes, no API key" lede="Archived call receipts and predictions are committed. The reproduce command verifies their provenance and recalculates historical metrics offline. Revised experiments and AI-review limitations are reported separately in the repository.">
        <ol className="region-plain divide-y divide-border">
          {REPRODUCE_STEPS.map((s, i) => (
            <li key={s.cmd} className="grid gap-2 px-5 py-4 sm:grid-cols-[28px_minmax(0,300px)_1fr_auto] sm:items-baseline sm:gap-5">
              <span className="t-mono text-[13px] text-faint">{String(i + 1).padStart(2, "0")}</span>
              <code className="t-mono block overflow-x-auto rounded-[4px] bg-bg px-2 py-1 text-[13px] text-text whitespace-nowrap">{s.cmd}</code>
              <span className="text-[13px] leading-relaxed text-muted">{s.what}</span>
              <span className="t-mono text-[12px] text-faint">{s.time}</span>
            </li>
          ))}
        </ol>
        <p className="text-[12px] text-faint">
          Results shown here were generated {summary.meta.generated_at.slice(0, 10)} from commit {summary.meta.git_sha.slice(0, 9)} with a {pct(summary.meta.cache_hit_rate)} cache hit
          rate; {int(summary.cost.n_llm_calls)} LLM calls and {int(summary.cost.total_prompt_tokens)} prompt tokens in {fixed(summary.cost.wall_minutes, 0)} minutes end to end.
        </p>
      </Section>
    </PageTransition>
  );
}

export default function Method() {
  useDocumentTitle("Method & data");
  const results = useAsync(getPublicSummary, []);
  const intents = useAsync(getIntents, []);
  const policy = useAsync(getPolicy, []);
  const loading = results.loading || intents.loading || policy.loading;
  const error = results.error ?? intents.error ?? policy.error;
  const reload = () => {
    results.reload();
    intents.reload();
    policy.reload();
  };

  return (
    <>
      <PageHeader
        eyebrow="method & data"
        title="How Cadence was built and measured"
        description="The corpus, the pipeline, the taxonomy and policy it enforces, how replies are judged, and the commands that reproduce every number on this site."
      />
      {loading ? <MethodSkeleton /> : error || !results.data || !intents.data || !policy.data ? <ErrorState error={error} what="the method data" onRetry={reload} /> : <MethodContent summary={results.data} intents={intents.data} policy={policy.data} />}
    </>
  );
}
