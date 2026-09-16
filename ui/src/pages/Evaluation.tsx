import { motion } from "framer-motion";
import { useCallback, useEffect } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import { ErrorState } from "@/components/ErrorState";
import { BenchmarkOverview } from "@/components/BenchmarkOverview";
import { EscalationTab } from "@/components/eval/EscalationTab";
import { IntentTab } from "@/components/eval/IntentTab";
import { JudgeAgreementTab } from "@/components/eval/JudgeAgreementTab";
import { extra } from "@/components/eval/maybe";
import { ReplyQualityTab } from "@/components/eval/ReplyQualityTab";
import { MetricTile } from "@/components/MetricTile";
import { PageHeader } from "@/components/PageHeader";
import { PageTransition } from "@/components/PageTransition";
import { Skeleton } from "@/components/Skeleton";
import { Tabs, type TabItem } from "@/components/Tabs";
import { useAsync } from "@/hooks/useAsync";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { describeError, getGolden, getResults } from "@/lib/api";
import { int } from "@/lib/format";
import type { EvalSummary } from "@/lib/types";

const TAB_IDS = ["intent", "escalation", "reply", "judge"] as const;
type TabId = (typeof TAB_IDS)[number];

const TABS: readonly TabItem<TabId>[] = [
  { id: "intent", label: "Intent" },
  { id: "escalation", label: "Escalation" },
  { id: "reply", label: "Reply quality" },
  { id: "judge", label: "Judge agreement" },
];

const TAB_TITLE: Record<TabId, string> = {
  intent: "Intent",
  escalation: "Escalation",
  reply: "Reply quality",
  judge: "Judge agreement",
};

function parseTab(value: string | null | undefined): TabId | null {
  return TAB_IDS.find((t) => t === value) ?? null;
}

function EvaluationSkeleton() {
  return (
    <div className="flex flex-col gap-8" aria-busy="true" aria-label="Loading evaluation">
      <div className="hairline-b flex gap-6 pb-3">
        {TABS.map((t) => (
          <Skeleton key={t.id} height={14} width={t.label.length * 8 + 8} />
        ))}
      </div>
      <Skeleton height={32} width={360} radius={6} />
      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <MetricTile key={i} label="loading" value={0} size="md" loading />
        ))}
      </div>
      <Skeleton height={360} radius={8} />
    </div>
  );
}

function summaryEyebrow(summary: EvalSummary | null): string {
  if (!summary) return "evaluation · intent / escalation / reply quality / judge agreement";
  const boot = extra<number>(summary.meta, "n_boot") ?? 1000;
  return `evaluation · test split n=${int(summary.meta.n_test)} · 95% bootstrap CI (${int(boot)} resamples, seed 42) · agent ${summary.meta.agent_model ?? "—"} · judge ${summary.meta.judge_model ?? "—"}`;
}

/**
 * Four tabs over `eval_summary.json`. The active tab lives in `?tab=` (a `#hash` is accepted on
 * arrival and normalised), and the selected system in `?system=`, so any view is linkable.
 */
export default function Evaluation() {
  const [params, setParams] = useSearchParams();
  const historical = params.get("view") === "historical";
  return <div className="flex flex-col gap-8">
    <div className="flex flex-wrap gap-2" aria-label="Evaluation version">
      {[false, true].map((value) => <button key={String(value)} className="btn" aria-pressed={historical === value} onClick={() => setParams((previous) => { previous.set("view", value ? "historical" : "revised"); return previous; })}>{value ? "Historical charts" : "Revised benchmark"}</button>)}
    </div>
    {historical ? <HistoricalEvaluation /> : <BenchmarkOverview />}
  </div>;
}

function HistoricalEvaluation() {
  const results = useAsync(getResults, []);
  const golden = useAsync(getGolden, []);
  const [params, setParams] = useSearchParams();
  const { hash } = useLocation();

  const tab: TabId = parseTab(params.get("tab")) ?? parseTab(hash.replace(/^#/, "")) ?? "intent";
  const system = params.get("system");
  useDocumentTitle(`Evaluation · ${TAB_TITLE[tab]}`);

  useEffect(() => {
    const fromHash = parseTab(hash.replace(/^#/, ""));
    if (fromHash && !params.get("tab")) {
      setParams(
        (prev) => {
          prev.set("tab", fromHash);
          return prev;
        },
        { replace: true },
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- normalise the hash once on arrival
  }, [hash]);

  const setTab = useCallback(
    (id: TabId) => {
      setParams(
        (prev) => {
          prev.set("tab", id);
          return prev;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const setSystem = useCallback(
    (id: string) => {
      setParams(
        (prev) => {
          prev.set("system", id);
          return prev;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const summary = results.data;
  const notes = summary ? extra<string[]>(summary.meta, "notes") ?? [] : [];

  return (
    <PageTransition>
      <PageHeader
        eyebrow={summaryEyebrow(summary)}
        title="Historical evaluation"
        description="Archived results on the original, repeatedly inspected test split. These figures describe an earlier agent and dataset; use Revised benchmark for the frozen 200-example comparison."
      />

      {results.loading && <EvaluationSkeleton />}
      {!results.loading && (results.error || !summary) && <ErrorState error={results.error} what="the evaluation results" onRetry={results.reload} />}

      {summary && (
        <div className="flex flex-col gap-8">
          {/* pb-px absorbs the tab buttons' -1px bottom margin, which otherwise leaves a 1px vertical scrollbar in the strip. */}
          <Tabs tabs={TABS} value={tab} onChange={setTab} label="Evaluation sections" className="pb-px" />

          {golden.error !== null && tab !== "judge" && (
            <p className="text-[12px] text-amber" role="status">
              Example lookups are unavailable ({describeError(golden.error)}); metrics still come from the summary.
            </p>
          )}

          <motion.div key={tab} role="tabpanel" aria-label={TAB_TITLE[tab]} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}>
            {tab === "intent" && <IntentTab summary={summary} golden={golden.data} system={system} onSystemChange={setSystem} />}
            {tab === "escalation" && <EscalationTab summary={summary} golden={golden.data} system={system} onSystemChange={setSystem} />}
            {tab === "reply" && <ReplyQualityTab summary={summary} golden={golden.data} />}
            {tab === "judge" && <JudgeAgreementTab summary={summary} />}
          </motion.div>

          {notes.length > 0 && (
            <section className="hairline-t pt-5" aria-label="Run notes">
              <p className="eyebrow mb-2">run notes</p>
              <ul className="flex flex-col gap-1 text-[12px] text-faint">
                {notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </PageTransition>
  );
}
