import { useEffect, useRef, useState } from "react";

import { useReducedMotion } from "./useReducedMotion";

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/**
 * Animate a number from 0 to `target` over `duration` ms (ease-out) on first appearance.
 * Returns the target immediately when reduced motion is preferred or `enabled` is false.
 */
export function useCountUp(target: number, duration = 600, enabled = true): number {
  const reduced = useReducedMotion();
  const animate = enabled && !reduced;
  const [value, setValue] = useState<number>(animate ? 0 : target);
  const done = useRef(false);

  useEffect(() => {
    if (!animate || done.current) {
      setValue(target);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      setValue(target * easeOutCubic(t));
      if (t < 1) frame = requestAnimationFrame(step);
      else done.current = true;
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, duration, animate]);

  return value;
}
