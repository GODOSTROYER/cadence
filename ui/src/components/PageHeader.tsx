import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

export interface PageHeaderProps {
  /** Mono, muted label above the title (e.g. "evaluation · 150 test examples"). */
  eyebrow: ReactNode;
  /** Serif title. */
  title: ReactNode;
  /** One sentence: what the reader can do or learn here. */
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

/** Top of every page: eyebrow / serif title / one-sentence description. */
export function PageHeader({ eyebrow, title, description, actions, className }: PageHeaderProps) {
  return (
    <header className={cx("mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        <p className="eyebrow mb-3">{eyebrow}</p>
        <h1 className="t-display t-display-40 text-text">{title}</h1>
        {description && <p className="measure-wide mt-3 text-[15px] leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}
