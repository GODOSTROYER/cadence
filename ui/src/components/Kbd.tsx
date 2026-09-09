import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

export interface KbdProps {
  children: ReactNode;
  className?: string;
}

/** Keyboard key hint, e.g. <Kbd>⌘K</Kbd>. */
export function Kbd({ children, className }: KbdProps) {
  return (
    <kbd
      className={cx(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-[4px] border border-border-strong bg-surface-2 px-1.5 font-mono text-[11px] leading-none text-muted",
        className,
      )}
    >
      {children}
    </kbd>
  );
}
