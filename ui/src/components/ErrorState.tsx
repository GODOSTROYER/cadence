import { RotateCcw, WifiOff } from "lucide-react";
import { lazy, Suspense } from "react";

import { EmptyState } from "@/components/EmptyState";
import { AdminSkeleton } from "@/components/RequireAdmin";
import { describeError, isApiError } from "@/lib/api";

const SignIn = lazy(() => import("@/pages/SignIn"));

export interface ErrorStateProps {
  error: unknown;
  /** What failed to load, e.g. "the evaluation results". */
  what: string;
  onRetry?: () => void;
  compact?: boolean;
  className?: string;
}

/**
 * Rose EmptyState with the typed error's message and a retry button. A 401 (the admin session expired
 * or was never set) renders the sign-in page in place instead, so every admin page locks the same way.
 */
export function ErrorState({ error, what, onRetry, compact, className }: ErrorStateProps) {
  if (isApiError(error) && error.status === 401) {
    return (
      <Suspense fallback={<AdminSkeleton />}>
        <SignIn inline />
      </Suspense>
    );
  }
  return (
    <EmptyState
      tone="rose"
      icon={<WifiOff />}
      title={`Couldn't load ${what}`}
      description={describeError(error)}
      compact={compact}
      className={className}
      action={
        onRetry && (
          <button type="button" className="btn" onClick={onRetry}>
            <RotateCcw className="size-3.5" aria-hidden="true" />
            Try again
          </button>
        )
      }
    />
  );
}
