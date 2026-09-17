import { ArrowRight, ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useAsync } from "@/hooks/useAsync";
import { getHealth } from "@/lib/api";
import { ErrorState } from "@/components/ErrorState";
import { PageTransition } from "@/components/PageTransition";

type Metric = { estimate: number | null; ci95: [number, number] | null };
type Metrics = Record<"accuracy" | "macro_f1" | "escalation_recall" | "auto_handle_rate", Metric> & Record<string, Metric>;
type System = { id: string; name: string; n: number; misses: number; metrics: Metrics };
interface Benchmark {
  run_id: string; execution_commit: string; dataset_hash: string; prompt_version: string; policy_version: string;
  evaluation_mode: string; n: number; models: string[]; source: string;
  review: { reviewer: string; review_outcome: string };
  systems: System[];
  judge: { system_means: { agent: number; simple_keyword: number }; preference_order_consistency: number; mean_overall_delta: number };
  replay: { changed_ids: string[]; judge_note: string; metrics: { metrics: Metrics } };
  supplemental_review: { status: string; reviewer: string; n_messages: number; n_ratings: number; weighted_kappa: number | null; exact_agreement: number; within_one: number; source: string };
  routing_experiment: { n: number; current: { escalation_recall: number; auto_handle_rate: number }; selective: { escalation_recall: number; auto_handle_rate: number }; source: string };
}
const REPO = "https://github.com/GODOSTROYER/cadence/blob/main/";
const percent = (v: number | null) => v == null ? "—" : `${(100 * v).toFixed(1)}%`;
const metric = (m: Metric, percentage = true) => m.estimate == null ? "—" : percentage ? percent(m.estimate) : m.estimate.toFixed(3);
const interval = (m: Metric, percentage = true) => m.ci95 ? m.ci95.map((v) => percentage ? percent(v) : v.toFixed(3)).join(" – ") : "Not available";
async function load(): Promise<Benchmark> {
  const response = await fetch(`${import.meta.env.BASE_URL}data/benchmark.json`);
  if (!response.ok) throw new Error("The benchmark export could not be loaded.");
  return response.json();
}
export function BenchmarkOverview() {
  const result = useAsync(load, []);
  const health = useAsync(getHealth, []);
  if (result.loading) return <p className="text-muted" role="status">Loading benchmark…</p>;
  if (!result.data || result.error) return <ErrorState error={result.error} what="the benchmark" onRetry={result.reload} />;
  const data = result.data;
  const agent = data.systems.find((s) => s.id === "agent")!;
  return <PageTransition className="flex flex-col gap-12 md:gap-16">
    <section className="grid items-center gap-8 pt-4 xl:grid-cols-[minmax(0,7fr)_minmax(0,4fr)] xl:gap-12">
      <div>
        <p className="eyebrow mb-6">Hiver SDE Intern take-home · Arnav Bule</p>
        <h1 className="t-display t-italic max-w-[20ch] text-[clamp(48px,5vw,80px)] leading-[1.04] text-balance">An AI support agent that knows when to stay quiet.</h1>
        <p className="mt-6 max-w-[58ch] text-[17px] leading-relaxed text-muted">Cadence classifies a customer tweet, drafts a reply from 27,627 real @SpotifyCares conversations, and decides when a human must step in.</p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link className="btn btn-primary w-full justify-center sm:w-auto" to="/agent">Try the live agent <ArrowRight className="size-4" /></Link>
          <a className="btn w-full justify-center sm:w-auto" href="#benchmark-results">Read the evidence</a>
          <Link className="btn w-full justify-center sm:w-auto" to="/method">How it works</Link>
        </div>
      </div>
      <dl className="divide-y divide-border border-y border-border text-sm">
        {[["benchmark", `${data.n} messages · four matched systems`], ["review", data.review.review_outcome], ["execution", data.execution_commit.slice(0, 9)], ["mode", data.evaluation_mode], ["live deployment", health.data?.deployment_commit?.slice(0, 9) ?? "Revision unavailable"], ["model", data.models.join(", ")]].map(([key, value]) => <div key={key} className="grid grid-cols-[105px_minmax(0,1fr)] gap-4 py-4"><dt className="t-mono text-xs text-faint">{key}</dt><dd className="break-words text-muted">{value}</dd></div>)}
      </dl>
    </section>
    <section id="benchmark-results" className="scroll-mt-8">
      <p className="eyebrow mb-3">01 · frozen benchmark</p>
      <h2 className="t-display t-italic text-4xl">One run. The complete comparison.</h2>
      <p className="mt-3 max-w-3xl text-muted">These results describe the frozen execution below. The live demo runs newer code. Later fixes have separate regression evidence.</p>
      <div className="mt-7 grid gap-4 sm:grid-cols-3">
        {[["Intent macro-F1", "macro_f1", false], ["Escalation recall", "escalation_recall", true], ["Auto-handle coverage", "auto_handle_rate", true]].map(([label, key, pct]) => <div key={String(key)} className="rounded-lg border border-border p-6"><p className="eyebrow">{label}</p><p className="t-display mt-3 text-5xl">{metric(agent.metrics[String(key)]!, Boolean(pct))}</p><p className="mt-3 text-xs text-muted">95% interval: {interval(agent.metrics[String(key)]!, Boolean(pct))}</p></div>)}
      </div>
      <div className="mt-7 overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[650px] text-left text-sm"><caption className="sr-only">Frozen benchmark comparison across the same 200 messages</caption><thead className="border-b border-border text-muted"><tr>{["System", "Accuracy", "Macro-F1", "Recall", "Auto", "Misses / auto"].map((h) => <th scope="col" className="p-4 font-medium" key={h}>{h}</th>)}</tr></thead><tbody>{data.systems.map((s) => { const auto = Math.round(s.metrics.auto_handle_rate.estimate! * s.n); return <tr key={s.id} className="border-b border-border last:border-0"><th scope="row" className="p-4 font-normal">{s.name}</th><td className="p-4">{metric(s.metrics.accuracy)}</td><td className="p-4">{metric(s.metrics.macro_f1, false)}</td><td className="p-4">{metric(s.metrics.escalation_recall)}</td><td className="p-4">{auto}/{s.n}</td><td className="p-4">{auto ? `${s.misses}/${auto}` : "N/A"}</td></tr>; })}</tbody></table>
      </div>
      <p className="mt-4 text-sm leading-relaxed text-muted">{agent.misses} of {Math.round(agent.metrics.auto_handle_rate.estimate! * agent.n)} automatic replies missed a required escalation. Retrieval did not establish a classification gain. The k0 agent’s citation veto forces zero automatic replies, so its coverage does not isolate retrieval’s safety benefit.</p>
    </section>
    <section className="grid gap-8 md:grid-cols-2">
      <div><p className="eyebrow mb-3">02 · reply evaluation</p><h2 className="t-display text-3xl">Judge results, with limits.</h2><p className="mt-4 leading-relaxed text-muted">Across both presentation orders, the agent averages {data.judge.system_means.agent.toFixed(2)}/5 and the keyword baseline {data.judge.system_means.simple_keyword.toFixed(2)}/5. Preference order consistency is {percent(data.judge.preference_order_consistency)}. The judge still approved known obsolete advice and an invented DM action.</p></div>
      <div><p className="eyebrow mb-3">03 · post-audit replay</p><h2 className="t-display text-3xl">Repairs are tracked separately.</h2><p className="mt-4 leading-relaxed text-muted">Holding replies replace {data.replay.changed_ids.length} frozen outputs after inspection. Replay recall is {metric(data.replay.metrics.metrics.escalation_recall)} at {metric(data.replay.metrics.metrics.auto_handle_rate)} coverage. This is retrospective regression evidence. The original judge scores do not transfer to changed replies.</p></div>
    </section>
    <section className="grid gap-8 md:grid-cols-2">
      <div><p className="eyebrow mb-3">04 · human verification complete</p><h2 className="t-display text-3xl">Reviewed by Arnav Bule.</h2><p className="mt-4 leading-relaxed text-muted">First reviewed by GPT-6 Astra at extra-high reasoning, then verified unchanged by Arnav Bule: {data.supplemental_review.n_ratings} reply ratings across {data.supplemental_review.n_messages} messages. Agreement with the original Gemini judge is κ {data.supplemental_review.weighted_kappa?.toFixed(3) ?? "undefined"}, with {percent(data.supplemental_review.exact_agreement)} exact agreement across both orders. This is human verification of AI-assisted ratings, with the initial scores visible.</p><a className="link mt-3 inline-block text-sm" href={`${REPO}${data.supplemental_review.source}`}>Review record and agreement</a></div>
      <div><p className="eyebrow mb-3">05 · routing development</p><h2 className="t-display text-3xl">A promising separate experiment.</h2><p className="mt-4 leading-relaxed text-muted">On {data.routing_experiment.n} new AI-labeled development messages, message-first routing achieved {percent(data.routing_experiment.selective.escalation_recall)} escalation recall at {percent(data.routing_experiment.selective.auto_handle_rate)} automatic coverage. The current agent achieved {percent(data.routing_experiment.current.escalation_recall)} recall at {percent(data.routing_experiment.current.auto_handle_rate)} coverage. Reply usefulness and fresh confirmation are still needed before changing production routing.</p><a className="link mt-3 inline-block text-sm" href={`${REPO}${data.routing_experiment.source}`}>Development comparison</a></div>
    </section>
    <details className="rounded-lg border border-border p-5"><summary className="cursor-pointer">Run identity and reproduction</summary><dl className="mt-5 grid gap-4 text-xs">{[["run_id", data.run_id], ["execution_commit", data.execution_commit], ["dataset_hash", data.dataset_hash], ["prompt_version", data.prompt_version], ["policy_version", data.policy_version]].map(([key,value]) => <div key={key}><dt className="text-muted">{key}</dt><dd className="t-mono mt-1 break-all">{value}</dd></div>)}</dl><p className="t-mono mt-5 break-words text-xs">python scripts/15_publish_benchmark.py --check</p><p className="mt-2 text-sm text-muted">Checks this export and the report table against the same frozen summary. Recorded reproduction makes no model calls.</p></details>
    <footer className="flex flex-wrap gap-5 border-t border-border pt-6 text-sm"><span>Cadence · Arnav Bule</span><a className="link" href={`${REPO}REPORT.md`}>Full report <ArrowUpRight className="inline size-3" /></a><a className="link" href={`${REPO}${data.source}`}>Source results</a><a className="link" href={`${REPO}docs/IMPROVEMENTS.md`}>Experiments and review</a></footer>
  </PageTransition>;
}
