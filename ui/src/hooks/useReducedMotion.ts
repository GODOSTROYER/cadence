import { useEffect, useState } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function current(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(QUERY).matches;
}

/** True when the viewer asked for reduced motion; updates live if the OS setting changes. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(current);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(QUERY);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
