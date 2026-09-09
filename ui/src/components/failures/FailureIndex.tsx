import { cx } from "@/lib/cx";
import type { FailureMode } from "@/lib/types";

export interface FailureIndexProps {
  modes: readonly FailureMode[];
  /** Id of the section currently being read (see `useActiveSection`). */
  activeId: string | null;
  /** `rail`: the sticky list beside the sections on wide screens. `strip`: a horizontal jump row. */
  variant: "rail" | "strip";
  className?: string;
}

function ordinal(i: number): string {
  return String(i + 1).padStart(2, "0");
}

/** In-page index of the failure modes. Plain hash links, so the browser scrolls and the URL deep-links. */
export function FailureIndex({ modes, activeId, variant, className }: FailureIndexProps) {
  if (variant === "strip") {
    return (
      <nav aria-label="Failure modes" className={cx("-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:-mx-6 sm:px-6", className)}>
        {modes.map((m, i) => {
          const active = m.id === activeId;
          return (
            <a
              key={m.id}
              href={`#${m.id}`}
              aria-current={active ? "true" : undefined}
              className={cx(
                "inline-flex h-8 shrink-0 items-center gap-2 rounded-full border px-3 text-[13px] whitespace-nowrap transition-colors duration-[120ms]",
                active ? "border-border-strong bg-surface-2 text-text" : "border-border text-muted hover:border-border-strong hover:text-text",
              )}
            >
              <span className="t-mono text-[12px] text-faint">{ordinal(i)}</span>
              {m.title}
            </a>
          );
        })}
      </nav>
    );
  }

  return (
    <nav aria-label="Failure modes" className={cx("flex flex-col gap-0.5", className)}>
      <p className="eyebrow mb-3 px-3">on this page</p>
      {modes.map((m, i) => {
        const active = m.id === activeId;
        return (
          <a
            key={m.id}
            href={`#${m.id}`}
            aria-current={active ? "true" : undefined}
            className={cx(
              "relative flex items-start gap-3 rounded-md px-3 py-2 text-[13px] leading-snug transition-colors duration-[120ms]",
              active ? "bg-surface-2 text-text" : "text-muted hover:bg-surface-2 hover:text-text",
            )}
          >
            {active && <span aria-hidden="true" className="absolute top-2 bottom-2 left-0 w-0.5 rounded-full bg-rose" />}
            <span className="t-mono mt-px shrink-0 text-[12px] text-faint">{ordinal(i)}</span>
            <span className="truncate-2 min-w-0 flex-1">{m.title}</span>
            <span className="t-mono mt-px shrink-0 text-[12px] text-faint" aria-label={`${m.count} examples`}>
              {m.count}
            </span>
          </a>
        );
      })}
    </nav>
  );
}
