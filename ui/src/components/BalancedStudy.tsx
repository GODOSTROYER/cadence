import { ErrorState } from "@/components/ErrorState";
import { useAsync } from "@/hooks/useAsync";

type Arm = "agent" | "quality" | "balanced";
type Counts = {
  automatic: number; useful_automatic: number; useful_resolution: number;
  useful_clarification: number; missed_escalations: number; flagged_automatic: number;
};
interface Study {
  current: {
    n: number; counts: Record<Arm, Counts>;
    runtime: Record<Arm, { p95_ms: number; prompt_tokens: number; output_tokens: number }>;
    technical_gates_pass: boolean; promote: boolean; decision: string; source: string;
  };
  review_note: string;
  latency_note: string;
}
const arms: [Arm, string][] = [["agent", "Reference"], ["quality", "Quality candidate"], ["balanced", "Balanced candidate"]];
async function load(): Promise<Study> {
  const response = await fetch(`${import.meta.env.BASE_URL}data/balanced.json`);
  if (!response.ok) throw new Error("The coverage comparison could not be loaded.");
  return response.json();
}

export function BalancedStudy() {
  const result = useAsync(load, []);
  if (result.loading) return <p className="text-muted" role="status">Loading coverage comparison…</p>;
  if (!result.data || result.error) return <ErrorState error={result.error} what="the coverage comparison" onRetry={result.reload} />;
  const { current: run, review_note, latency_note } = result.data;
  return <section aria-labelledby="balanced-title" className="scroll-mt-8" id="coverage-comparison">
    <p className="eyebrow mb-3">07 · coverage and safety</p>
    <h2 id="balanced-title" className="t-display t-italic text-4xl">Help more. Check the tradeoff.</h2>
    <p className="mt-4 max-w-3xl leading-relaxed text-muted">Three implementations, the same {run.n} new messages. The balanced candidate pairs a broader set of verified answers with a check of the exact reply. Useful help and missed escalations decide acceptance together.</p>
    <div className="mt-7 grid gap-4 lg:grid-cols-3">
      {arms.map(([id, label]) => {
        const counts = run.counts[id], runtime = run.runtime[id];
        return <article key={id} className="min-w-0 rounded-lg border border-border p-6">
          <h3 className="eyebrow">{label}</h3>
          <p className="t-display mt-4 text-5xl">{counts.useful_automatic}<span className="text-2xl text-muted"> / {run.n}</span></p>
          <p className="mt-2 text-sm text-muted">useful automatic replies</p>
          <dl className="mt-6 divide-y divide-border text-sm">
            {[["All automatic replies", `${counts.automatic} / ${run.n}`], ["Resolution-style replies", counts.useful_resolution],
              ["Useful clarifications", counts.useful_clarification], ["Missed escalations", counts.missed_escalations],
              ["Flagged automatic replies", counts.flagged_automatic], ["Response time · p95", `${(runtime.p95_ms / 1000).toFixed(2)} s`],
              ["Input + output tokens", (runtime.prompt_tokens + runtime.output_tokens).toLocaleString("en-US")]].map(([key, value]) =>
              <div className="flex items-baseline justify-between gap-4 py-3" key={key}><dt className="text-muted">{key}</dt><dd className="t-mono shrink-0">{value}</dd></div>)}
          </dl>
        </article>;
      })}
    </div>
    <p className="mt-5 max-w-4xl text-sm leading-relaxed text-muted">A useful reply must pass the reviewer’s grounding, safety and next-step checks. Necessary clarifications count as useful help; they are shown separately from resolution-style replies. These are reviewer judgments, not observed customer outcomes. Handoffs and social acknowledgments do not count.</p>
    <p className="mt-3 max-w-4xl text-sm leading-relaxed text-muted">{latency_note}</p>
    <div className="mt-6 rounded-lg border border-border p-5 md:p-6">
      <p className="font-medium">{run.technical_gates_pass ? "Technical acceptance passed." : "Technical acceptance did not pass."} {run.decision}</p>
      <p className="mt-3 max-w-4xl text-sm leading-relaxed text-muted">{review_note}</p>
      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-3 text-sm">
        <a className="link" href={`https://github.com/GODOSTROYER/cadence/blob/main/${run.source}`}>Every acceptance gate</a>
        <a className="link" href="https://github.com/GODOSTROYER/cadence/blob/main/docs/BALANCED_ACCEPTANCE.md">Methods and development history</a>
      </div>
    </div>
  </section>;
}
