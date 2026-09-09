import { AnimatePresence, motion } from "framer-motion";
import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { ScrollToTop } from "@/components/ScrollToTop";
import { Sidebar } from "@/components/Sidebar";
import { useAsync } from "@/hooks/useAsync";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { getHealth, uiMode } from "@/lib/api";
import { cx } from "@/lib/cx";

/**
 * Sidebar (240px) → icon rail (64px) under 1100px → slide-in drawer under 768px.
 * The health call happens once here and feeds the status chips.
 */
export function AppShell() {
  const rail = useMediaQuery("(max-width: 1099px)");
  const phone = useMediaQuery("(max-width: 767px)");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { pathname } = useLocation();
  const health = useAsync(getHealth, []);
  const mode = uiMode(health.data);

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  const sidebarProps = { health: health.data, healthLoading: health.loading, mode };

  return (
    <div className="flex min-h-screen bg-bg text-text">
      <ScrollToTop />
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[1200] focus:rounded-md focus:bg-green focus:px-3 focus:py-2 focus:text-[13px] focus:font-medium focus:text-bg"
      >
        Skip to content
      </a>

      {!phone && (
        <aside
          className={cx("sticky top-0 h-screen shrink-0 border-r border-border bg-surface", rail ? "w-16" : "w-60")}
          aria-label="Sidebar"
        >
          <Sidebar collapsed={rail} {...sidebarProps} />
        </aside>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {phone && (
          <header className="sticky top-0 z-[50] flex h-14 items-center justify-between border-b border-border bg-bg/90 px-4 backdrop-blur">
            <span className="t-display t-italic text-[24px] leading-none">Cadence</span>
            <button type="button" className="btn btn-ghost -mr-2 size-9 justify-center px-0" aria-label="Open navigation" aria-expanded={drawerOpen} onClick={() => setDrawerOpen(true)}>
              <Menu className="size-5" />
            </button>
          </header>
        )}

        <main id="content" tabIndex={-1} className="flex-1 outline-none">
          <div className="mx-auto w-full max-w-[1280px] px-4 py-6 sm:px-6 md:px-8 md:py-8 lg:py-10">
            <Outlet />
          </div>
        </main>
      </div>

      <AnimatePresence>
        {phone && drawerOpen && (
          <div className="fixed inset-0 z-[950]">
            <motion.button
              type="button"
              aria-label="Close navigation"
              onClick={() => setDrawerOpen(false)}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="absolute inset-0 cursor-default bg-bg/70"
            />
            <motion.aside
              role="dialog"
              aria-modal="true"
              aria-label="Navigation"
              initial={{ x: -24, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: -24, opacity: 0 }}
              transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
              className="absolute inset-y-0 left-0 w-[280px] max-w-[85vw] border-r border-border bg-surface"
            >
              <button type="button" aria-label="Close navigation" onClick={() => setDrawerOpen(false)} className="btn btn-ghost absolute top-3.5 right-2 size-9 justify-center px-0">
                <X className="size-4" />
              </button>
              <Sidebar {...sidebarProps} onNavigate={() => setDrawerOpen(false)} />
            </motion.aside>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
