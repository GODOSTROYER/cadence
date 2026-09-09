import { useEffect, useState } from "react";

/** Fraction of the viewport height a section's top must cross before it counts as "being read". */
const READING_LINE = 0.3;

/**
 * Track which of the given section ids the reader is on: the last section whose top edge has passed
 * a line 30% down the viewport, or the final section once the page is scrolled to the bottom (so a
 * short last section can still become active). Measures on scroll and resize, one frame at a time.
 * Pass a memoised `ids` array; the listener re-subscribes when it changes.
 */
export function useActiveSection(ids: readonly string[], enabled = true): string | null {
  const [active, setActive] = useState<string | null>(ids[0] ?? null);

  useEffect(() => {
    if (!enabled || ids.length === 0) return;
    let frame = 0;

    const measure = () => {
      frame = 0;
      const line = window.innerHeight * READING_LINE;
      let current = ids[0] ?? null;
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top <= line) current = id;
      }
      const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      if (atBottom) current = ids[ids.length - 1] ?? current;
      setActive(current);
    };

    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };

    measure();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [ids, enabled]);

  return active;
}
