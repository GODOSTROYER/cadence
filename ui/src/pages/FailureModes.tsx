import { useEffect, useMemo } from "react";
import { useLocation } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FailureIndex } from "@/components/failures/FailureIndex";
import { FailureSection } from "@/components/failures/FailureSection";
import { useActiveSection } from "@/components/failures/useActiveSection";
import { PageHeader } from "@/components/PageHeader";
import { PageTransition } from "@/components/PageTransition";
import { Skeleton, SkeletonText } from "@/components/Skeleton";
import { useAsync } from "@/hooks/useAsync";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { getFailures, getResults } from "@/lib/api";
import { plural } from "@/lib/format";
import type { FailureMode } from "@/lib/types";

const LAYOUT = "lg:grid lg:grid-cols-[200px_minmax(0,1fr)] lg:gap-12";

function FailureModesSkeleton() {
  return (
    <div className={LAYOUT} aria-busy="true" aria-label="Loading failure modes">
      <div className="hidden lg:flex lg:flex-col lg:gap-2">
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} height={36} radius={6} />
        ))}
      </div>
      <div className="hairline-t flex flex-col divide-y divide-border">
        {[0, 1].map((i) => (
          <div key={i} className="grid gap-5 py-10 md:grid-cols-[96px_minmax(0,1fr)] md:gap-8">
            <Skeleton height={64} width={84} radius={8} />
            <div className="flex flex-col gap-5">
              <Skeleton height={32} width="60%" radius={6} />
              <Skeleton height={13} width={240} />
              <SkeletonText lines={3} lastWidth="70%" />
              <Skeleton height={236} radius={8} />
              <Skeleton height={236} radius={8} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Scroll the deep-linked section (`/failures#fm3`) into view; runs once the sections are mounted. */
function useHashScroll(ids: readonly string[]): void {
  const { hash } = useLocation();
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!hash) return;
    const id = hash.slice(1);
    if (!ids.includes(id)) return;
    document.getElementById(id)?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
  }, [hash, ids, reduced]);
}

function FailureModesContent({ modes, nTest }: { modes: FailureMode[]; nTest: number | null }) {
  const ids = useMemo(() => modes.map((m) => m.id), [modes]);
  const active = useActiveSection(ids);
  const maxShare = Math.max(0, ...modes.map((m) => m.share));
  useHashScroll(ids);

  return (
    <PageTransition>
      <div className={LAYOUT}>
        <FailureIndex modes={modes} activeId={active} variant="strip" className="mb-4 lg:hidden" />
        <aside className="hidden lg:sticky lg:top-10 lg:block lg:self-start">
          <FailureIndex modes={modes} activeId={active} variant="rail" />
        </aside>
        <div className="hairline-t flex min-w-0 flex-col divide-y divide-border">
          {modes.map((m, i) => (
            <FailureSection key={m.id} mode={m} index={i} nTest={nTest} maxShare={maxShare} />
          ))}
        </div>
      </div>
    </PageTransition>
  );
}

export default function FailureModes() {
  useDocumentTitle("Failure modes");
  const failures = useAsync(getFailures, []);
  // Optional context only: the size of the test split for "x of N test tweets". Its errors are not surfaced.
  const results = useAsync(getResults, []);
  const modes = failures.data;
  const nTest = results.data?.meta.n_test ?? null;
  const totalExamples = modes?.reduce((acc, m) => acc + m.count, 0) ?? 0;

  return (
    <>
      <PageHeader
        eyebrow={modes ? `failure modes · top ${modes.length} · ${plural(totalExamples, "example")}` : "failure modes · top five"}
        title="Where it fails"
        description="The recurring ways the agent gets it wrong on the test split: the real tweets, a hypothesis about the cause, and the fix each one points to."
      />
      {failures.loading && <FailureModesSkeleton />}
      {!failures.loading && (failures.error || !modes) && <ErrorState error={failures.error} what="the failure modes" onRetry={failures.reload} />}
      {!failures.loading && modes && modes.length === 0 && (
        <EmptyState title="No failure modes recorded" description="results/failure_modes.json is empty. Run the evaluation (make eval) to mine the test split for recurring errors." />
      )}
      {!failures.loading && modes && modes.length > 0 && <FailureModesContent modes={modes} nTest={nTest} />}
    </>
  );
}
