import { AnimatePresence, motion } from "framer-motion";
import { cloneElement, isValidElement, useCallback, useId, useRef, useState, type ReactElement, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { cx } from "@/lib/cx";

export interface TooltipProps {
  /** Tooltip body. When null/empty the child renders alone. */
  content: ReactNode;
  children: ReactElement;
  side?: "top" | "bottom";
  /** Max width in px (default 280). */
  maxWidth?: number;
  className?: string;
}

interface Position {
  x: number;
  y: number;
  side: "top" | "bottom";
}

/**
 * Hover / focus tooltip rendered in a portal with fixed positioning, so it is never clipped by
 * overflow containers (tables, drawers). The child receives `aria-describedby`.
 */
export function Tooltip({ content, children, side = "top", maxWidth = 280, className }: TooltipProps) {
  const id = useId();
  const anchor = useRef<HTMLElement | null>(null);
  const [pos, setPos] = useState<Position | null>(null);

  const show = useCallback(() => {
    const el = anchor.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const roomAbove = r.top > 72;
    const resolved: "top" | "bottom" = side === "top" && roomAbove ? "top" : "bottom";
    setPos({ x: r.left + r.width / 2, y: resolved === "top" ? r.top - 8 : r.bottom + 8, side: resolved });
  }, [side]);

  const hide = useCallback(() => setPos(null), []);

  if (!content || !isValidElement(children)) return children;

  const childProps = children.props as Record<string, unknown>;
  const trigger = cloneElement(children, {
    ref: (node: HTMLElement | null) => {
      anchor.current = node;
      const childRef = (children as ReactElement & { ref?: unknown }).ref;
      if (typeof childRef === "function") childRef(node);
      else if (childRef && typeof childRef === "object") (childRef as { current: HTMLElement | null }).current = node;
    },
    onMouseEnter: (e: unknown) => {
      show();
      (childProps.onMouseEnter as ((e: unknown) => void) | undefined)?.(e);
    },
    onMouseLeave: (e: unknown) => {
      hide();
      (childProps.onMouseLeave as ((e: unknown) => void) | undefined)?.(e);
    },
    onFocus: (e: unknown) => {
      show();
      (childProps.onFocus as ((e: unknown) => void) | undefined)?.(e);
    },
    onBlur: (e: unknown) => {
      hide();
      (childProps.onBlur as ((e: unknown) => void) | undefined)?.(e);
    },
    "aria-describedby": pos ? id : undefined,
  } as Record<string, unknown>);

  return (
    <>
      {trigger}
      {createPortal(
        <AnimatePresence>
          {pos && (
            <motion.div
              role="tooltip"
              id={id}
              initial={{ opacity: 0, y: pos.side === "top" ? 4 : -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.12 }}
              className={cx(
                "pointer-events-none fixed z-[1000] rounded-md border border-border-strong bg-surface-2 px-2.5 py-1.5 text-[12px] leading-snug text-text shadow-none",
                className,
              )}
              style={{
                left: pos.x,
                top: pos.y,
                maxWidth,
                transform: `translate(-50%, ${pos.side === "top" ? "-100%" : "0"})`,
              }}
            >
              {content}
            </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </>
  );
}
