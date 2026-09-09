import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/** Scroll to the top on every route change (instant, so it never fights reduced-motion settings). */
export function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" as ScrollBehavior });
  }, [pathname]);
  return null;
}
