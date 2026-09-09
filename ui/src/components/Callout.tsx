import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

export type CalloutTone = "amber" | "sky" | "rose" | "green" | "neutral";

export interface CalloutProps {
  /** Italic serif title, e.g. "What is misleading about these numbers". */
  title: ReactNode;
  children: ReactNode;
  tone?: CalloutTone;
  /** Mono eyebrow above the title. */
  eyebrow?: string;
  className?: string;
}

const TONE_BORDER: Record<CalloutTone, string> = {
  amber: "border-amber/40",
  sky: "border-sky/40",
  rose: "border-rose/40",
  green: "border-green/40",
  neutral: "border-border-strong",
};

const TONE_RULE: Record<CalloutTone, string> = {
  amber: "bg-amber",
  sky: "bg-sky",
  rose: "bg-rose",
  green: "bg-green",
  neutral: "bg-faint",
};

/** Hairline-bordered box for editorial asides. Amber by default: the honest-caveats box. */
export function Callout({ title, children, tone = "amber", eyebrow, className }: CalloutProps) {
  return (
    <aside className={cx("relative rounded-lg border bg-surface px-6 py-5 sm:px-7", TONE_BORDER[tone], className)}>
      <span aria-hidden="true" className={cx("absolute top-5 bottom-5 left-0 w-px", TONE_RULE[tone])} />
      {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
      <h3 className="t-display-28 t-italic text-text">{title}</h3>
      <div className="mt-3 text-[14px] leading-relaxed text-muted [&_li]:relative [&_li]:pl-5 [&_li::before]:absolute [&_li::before]:top-[0.7em] [&_li::before]:left-1 [&_li::before]:size-1 [&_li::before]:rounded-full [&_li::before]:bg-faint [&_li::before]:content-[''] [&_strong]:font-medium [&_strong]:text-text [&_ul]:flex [&_ul]:flex-col [&_ul]:gap-2">
        {children}
      </div>
    </aside>
  );
}
