import { useEffect } from "react";

/** Set `document.title` to "<title> — Cadence" for the lifetime of the page. */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    const previous = document.title;
    document.title = title ? `${title} — Cadence` : "Cadence";
    return () => {
      document.title = previous;
    };
  }, [title]);
}
