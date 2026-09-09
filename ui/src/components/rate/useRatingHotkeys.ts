import { useEffect, useRef } from "react";

import type { Verdict } from "@/lib/types";

export interface RatingHotkeyHandlers {
  /** A digit 1–5 was pressed outside an editable field; `target` is the focused element. */
  onDigit: (value: number, target: HTMLElement | null) => void;
  /** S / E / R was pressed outside an editable field. */
  onVerdict: (verdict: Verdict) => void;
  /** Cmd/Ctrl + Enter, from anywhere on the page (the rationale textarea included). */
  onSubmit: () => void;
}

const VERDICT_KEYS: Record<string, Verdict> = { s: "ship", e: "edit", r: "reject" };

function isEditable(el: HTMLElement | null): boolean {
  if (!el) return false;
  return el.tagName === "TEXTAREA" || el.tagName === "INPUT" || el.tagName === "SELECT" || el.isContentEditable;
}

/** Whether the viewer is on an Apple keyboard, for the ⌘ / Ctrl hint. */
export function isApplePlatform(): boolean {
  return typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent);
}

/**
 * Document-level keyboard shortcuts for the rating flow. Handlers are read through a ref, so the
 * listener is attached once per `enabled` change and always sees the latest closure.
 */
export function useRatingHotkeys(enabled: boolean, handlers: RatingHotkeyHandlers): void {
  const latest = useRef(handlers);
  latest.current = handlers;

  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        latest.current.onSubmit();
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target instanceof HTMLElement ? e.target : null;
      if (isEditable(target)) return;

      const digit = Number(e.key);
      if (Number.isInteger(digit) && digit >= 1 && digit <= 5) {
        e.preventDefault();
        latest.current.onDigit(digit, target);
        return;
      }
      const verdict = VERDICT_KEYS[e.key.toLowerCase()];
      if (verdict) {
        e.preventDefault();
        latest.current.onVerdict(verdict);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [enabled]);
}
