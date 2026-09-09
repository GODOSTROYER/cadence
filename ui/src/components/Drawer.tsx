import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { cx } from "@/lib/cx";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  /** Serif title; `eyebrow` is a mono label above it (e.g. the record id). */
  title: ReactNode;
  eyebrow?: ReactNode;
  /** Actions rendered in the header, right of the title. */
  actions?: ReactNode;
  children: ReactNode;
  /** Panel width in px on wide screens (default 560). Full width under 640px. */
  width?: number;
  className?: string;
}

/** Right-side detail panel. Escape and the backdrop close it; focus moves into the panel on open. */
export function Drawer({ open, onClose, title, eyebrow, actions, children, width = 560, className }: DrawerProps) {
  const panel = useRef<HTMLDivElement | null>(null);
  const restore = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restore.current = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const t = window.setTimeout(() => panel.current?.focus(), 30);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      window.clearTimeout(t);
      restore.current?.focus?.();
    };
  }, [open, onClose]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[900]">
          <motion.button
            type="button"
            aria-label="Close panel"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 cursor-default bg-bg/70"
          />
          <motion.div
            ref={panel}
            role="dialog"
            aria-modal="true"
            tabIndex={-1}
            initial={{ x: 24, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 24, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
            className={cx(
              "absolute inset-y-0 right-0 flex w-full flex-col border-l border-border bg-surface outline-none",
              className,
            )}
            style={{ maxWidth: width }}
          >
            <header className="hairline-b flex items-start gap-4 px-6 py-5">
              <div className="min-w-0 flex-1">
                {eyebrow && <p className="eyebrow mb-1.5">{eyebrow}</p>}
                <h2 className="t-display-28 truncate text-text">{title}</h2>
              </div>
              {actions}
              <button type="button" aria-label="Close" onClick={onClose} className="btn btn-ghost -mr-2 size-9 justify-center px-0">
                <X className="size-4" />
              </button>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
