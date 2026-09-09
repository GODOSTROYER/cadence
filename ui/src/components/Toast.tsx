import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Info, TriangleAlert, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

import { cx } from "@/lib/cx";

export type ToastTone = "neutral" | "success" | "warning" | "error";

export interface ToastOptions {
  title: string;
  description?: string;
  tone?: ToastTone;
  /** Auto-dismiss after this many ms (default 4200; 0 keeps it until closed). */
  duration?: number;
}

interface ToastItem extends Required<Pick<ToastOptions, "title" | "tone" | "duration">> {
  id: number;
  description: string | undefined;
}

interface ToastApi {
  toast: (opts: ToastOptions) => void;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const ICON: Record<ToastTone, ReactNode> = {
  neutral: <Info />,
  success: <CheckCircle2 />,
  warning: <TriangleAlert />,
  error: <XCircle />,
};

const ICON_TONE: Record<ToastTone, string> = {
  neutral: "text-sky",
  success: "text-green",
  warning: "text-amber",
  error: "text-rose",
};

/** Provides `useToast()`; renders the stack bottom-right (bottom-centre on phones). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => setItems((list) => list.filter((t) => t.id !== id)), []);

  const toast = useCallback(
    (opts: ToastOptions) => {
      const id = ++seq.current;
      const item: ToastItem = {
        id,
        title: opts.title,
        description: opts.description,
        tone: opts.tone ?? "neutral",
        duration: opts.duration ?? 4200,
      };
      setItems((list) => [...list.slice(-3), item]);
      if (item.duration > 0) window.setTimeout(() => dismiss(id), item.duration);
    },
    [dismiss],
  );

  const api = useMemo(() => ({ toast, dismiss }), [toast, dismiss]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-4 bottom-4 z-[1100] flex flex-col items-center gap-2 sm:inset-x-auto sm:right-6 sm:bottom-6 sm:items-end"
      >
        <AnimatePresence initial={false}>
          {items.map((t) => (
            <motion.div
              key={t.id}
              role="status"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="pointer-events-auto flex w-full max-w-[380px] items-start gap-3 rounded-lg border border-border-strong bg-surface-2 px-4 py-3"
            >
              <span aria-hidden="true" className={cx("mt-0.5 shrink-0 [&>svg]:size-4", ICON_TONE[t.tone])}>
                {ICON[t.tone]}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-text">{t.title}</p>
                {t.description && <p className="mt-0.5 text-[12px] leading-snug text-muted">{t.description}</p>}
              </div>
              <button
                type="button"
                aria-label="Dismiss notification"
                onClick={() => dismiss(t.id)}
                className="btn btn-ghost btn-sm -mr-2 size-7 shrink-0 justify-center px-0"
              >
                <X className="size-3.5" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

/** Access the toast API; must be used under <ToastProvider>. */
export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast() requires <ToastProvider> above it in the tree.");
  return api;
}
