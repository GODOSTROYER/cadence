import { FailureExampleCard } from "@/components/failures/FailureExampleCard";
import { Reveal } from "@/components/PageTransition";
import { int, pct, plural } from "@/lib/format";
import type { FailureMode } from "@/lib/types";

export interface FailureSectionProps {
  mode: FailureMode;
  /** 0-based position in the list; rendered as the large "01" numeral. */
  index: number;
  /** Size of the test split, for "x of N test tweets"; null when the summary is unavailable. */
  nTest: number | null;
  /** Largest share among all modes, so the bars compare modes against each other. */
  maxShare: number;
}

function ShareLine({ mode, nTest, maxShare }: Pick<FailureSectionProps, "mode" | "nTest" | "maxShare">) {
  const share = pct(mode.share, 1);
  const width = maxShare > 0 ? Math.min(100, (mode.share / maxShare) * 100) : 0;
  return (
    <div className="flex flex-col gap-2">
      <p className="t-mono text-[13px] text-muted">
        <span className="text-rose">{plural(mode.count, "example")}</span> · <span className="text-text">{share}</span> of{" "}
        {nTest ? `${int(nTest)} test tweets` : "the test split"}
      </p>
      <div
        role="img"
        aria-label={`${share} of the test split, ${Math.round(width)}% of the largest failure mode`}
        title="Bar length is relative to the largest failure mode"
        className="h-1 w-full max-w-[320px] overflow-hidden rounded-full bg-surface-2"
      >
        <span className="block h-full rounded-full bg-rose" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

/** One numbered editorial section: numeral, title, count and share, hypothesis, examples, proposed fix. */
export function FailureSection({ mode, index, nTest, maxShare }: FailureSectionProps) {
  const titleId = `${mode.id}-title`;
  return (
    <Reveal>
      <section id={mode.id} aria-labelledby={titleId} className="grid scroll-mt-6 gap-5 py-10 md:grid-cols-[96px_minmax(0,1fr)] md:gap-8 md:py-12">
        <a
          href={`#${mode.id}`}
          aria-label={`Failure mode ${index + 1}`}
          className="numeral self-start text-[56px] leading-none text-faint transition-colors duration-[120ms] hover:text-rose md:text-[72px]"
        >
          {String(index + 1).padStart(2, "0")}
        </a>
        <div className="flex min-w-0 flex-col gap-6">
          <header className="flex flex-col gap-3">
            <h2 id={titleId} className="t-display-28 text-text md:text-[32px]">
              {mode.title}
            </h2>
            <ShareLine mode={mode} nTest={nTest} maxShare={maxShare} />
          </header>
          <p className="measure-wide text-[15px] leading-relaxed text-text">
            <span className="t-mono mr-2 text-[12px] text-faint">hypothesis</span>
            {mode.hypothesis}
          </p>
          {mode.examples.length > 0 ? (
            <ol className="flex flex-col gap-4" aria-label={`Examples of ${mode.title}`}>
              {mode.examples.map((ex, i) => (
                <FailureExampleCard key={`${ex.golden_id}-${i}`} example={ex} index={i} />
              ))}
            </ol>
          ) : (
            <p className="region-plain px-4 py-5 text-center text-[13px] text-faint italic">No examples were recorded for this failure mode.</p>
          )}
          <aside className="region-plain relative bg-surface px-5 py-4" aria-label="Proposed fix">
            <span aria-hidden="true" className="absolute top-4 bottom-4 left-0 w-px bg-green" />
            <p className="eyebrow mb-2">proposed fix</p>
            <p className="measure-wide text-[14px] leading-relaxed text-text">{mode.proposed_fix}</p>
          </aside>
        </div>
      </section>
    </Reveal>
  );
}
