import { motion } from "framer-motion";
import { useRef, type KeyboardEvent } from "react";

import { cx } from "@/lib/cx";

export interface TabItem<T extends string> {
  id: T;
  label: string;
  /** Optional count shown in mono after the label. */
  count?: number;
}

export interface TabsProps<T extends string> {
  tabs: readonly TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  /** Accessible name for the tab list. */
  label: string;
  className?: string;
}

/** Underlined tab strip with roving keyboard focus (←/→, Home/End). */
export function Tabs<T extends string>({ tabs, value, onChange, label, className }: TabsProps<T>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = tabs.findIndex((t) => t.id === value);
    let next = i;
    if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    else return;
    e.preventDefault();
    const tab = tabs[next];
    if (!tab) return;
    onChange(tab.id);
    refs.current[next]?.focus();
  };

  // The hairline is drawn on the outer wrapper (not on the scrolling strip), so the active underline can
  // sit exactly on it without a negative margin, which would otherwise create 1px of vertical overflow.
  return (
    <div className={cx("relative after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-border after:content-['']", className)}>
      <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="flex gap-1 overflow-x-auto">
        {tabs.map((t, i) => {
          const active = t.id === value;
          return (
            <button
              key={t.id}
              ref={(el) => {
                refs.current[i] = el;
              }}
              role="tab"
              type="button"
              aria-selected={active}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(t.id)}
              className={cx(
                "relative flex h-10 shrink-0 items-center gap-2 px-3 text-[13px] font-medium transition-colors duration-[120ms] focus-visible:outline-offset-[-2px]",
                active ? "text-text" : "text-muted hover:text-text",
              )}
            >
              {t.label}
              {typeof t.count === "number" && <span className="t-mono text-[12px] text-faint">{t.count}</span>}
              {active && (
                <motion.span
                  layoutId={`tabs-${label}`}
                  aria-hidden="true"
                  className="absolute inset-x-2 bottom-0 z-[1] h-px bg-green"
                  transition={{ type: "spring", stiffness: 500, damping: 40 }}
                />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
