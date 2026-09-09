import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { PageTransition, Reveal } from "@/components/PageTransition";
import { Skeleton, SkeletonText } from "@/components/Skeleton";
import { useAsync } from "@/hooks/useAsync";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { getDecisions } from "@/lib/api";
import type { DecisionEntry } from "@/lib/types";

function DecisionsSkeleton() {
  return (
    <ol className="flex flex-col divide-y divide-border" aria-busy="true" aria-label="Loading decisions">
      {[0, 1, 2, 3, 4].map((i) => (
        <li key={i} className="grid gap-4 py-8 md:grid-cols-[72px_1fr]">
          <Skeleton height={40} width={48} radius={6} />
          <div className="flex flex-col gap-4">
            <Skeleton height={28} width="55%" />
            <SkeletonText lines={2} lastWidth="80%" />
            <SkeletonText lines={2} lastWidth="60%" />
          </div>
        </li>
      ))}
    </ol>
  );
}

function DecisionItem({ d }: { d: DecisionEntry }) {
  return (
    <Reveal as="li" id={`d-${d.n}`} className="grid gap-3 py-8 md:grid-cols-[72px_1fr] md:gap-6">
      <a href={`#d-${d.n}`} className="numeral text-[40px] text-faint transition-colors duration-[120ms] hover:text-green md:text-[48px]" aria-label={`Decision ${d.n}`}>
        {String(d.n).padStart(2, "0")}
      </a>
      <div className="min-w-0">
        <h2 className="t-display-28 text-text">{d.title}</h2>
        <p className="measure-wide mt-3 text-[16px] leading-relaxed text-text">{d.decision}</p>
        <p className="measure-wide mt-3 text-[14px] leading-relaxed text-muted">
          <span className="t-mono mr-2 text-[12px] text-faint">why</span>
          {d.why}
        </p>
      </div>
    </Reveal>
  );
}

export default function Decisions() {
  useDocumentTitle("Decisions");
  const { data, error, loading, reload } = useAsync(getDecisions, []);

  return (
    <>
      <PageHeader
        eyebrow={data ? `decision log · ${data.length} entries` : "decision log"}
        title="Decisions that were not obvious"
        description="The calls that shaped the agent and the evaluation, each with the reasoning at the time. Parsed from DECISION_LOG.md."
      />
      {loading && <DecisionsSkeleton />}
      {!loading && (error || !data) && <ErrorState error={error} what="the decision log" onRetry={reload} />}
      {!loading && data && (
        <PageTransition>
          <ol className="hairline-t flex flex-col divide-y divide-border">
            {data.map((d) => (
              <DecisionItem key={d.n} d={d} />
            ))}
          </ol>
        </PageTransition>
      )}
    </>
  );
}
