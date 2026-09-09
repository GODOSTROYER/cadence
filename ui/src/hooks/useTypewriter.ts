import { useCallback, useEffect, useRef, useState } from "react";

import { useReducedMotion } from "./useReducedMotion";

export interface Typewriter {
  /** The characters revealed so far. */
  shown: string;
  /** True while characters are still being revealed. */
  typing: boolean;
  /** Reveal everything immediately ("click to skip"). */
  skip: () => void;
}

/**
 * Reveal `text` at `msPerChar` (≈8ms per DESIGN.md). Reduced motion or `active=false` shows the
 * full text at once. Restarts whenever `text` changes.
 */
export function useTypewriter(text: string, active: boolean, msPerChar = 8): Typewriter {
  const reduced = useReducedMotion();
  const instant = reduced || !active;
  const [count, setCount] = useState<number>(instant ? text.length : 0);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (timer.current) window.clearInterval(timer.current);
    if (instant) {
      setCount(text.length);
      return;
    }
    setCount(0);
    const started = performance.now();
    timer.current = window.setInterval(() => {
      const n = Math.min(text.length, Math.floor((performance.now() - started) / msPerChar));
      setCount(n);
      if (n >= text.length && timer.current) {
        window.clearInterval(timer.current);
        timer.current = null;
      }
    }, 16);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [text, instant, msPerChar]);

  const skip = useCallback(() => {
    if (timer.current) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
    setCount(text.length);
  }, [text.length]);

  return { shown: text.slice(0, count), typing: count < text.length, skip };
}
