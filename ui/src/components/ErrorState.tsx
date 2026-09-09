import { RotateCcw, WifiOff } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { describeError } from "@/lib/api";

export interface ErrorStateProps {
  error: unknown;
  /** What failed to load, e.g. "the evaluation results". */
  what: string;
  onRetry?: () => void;
  compact?: boolean;
  className?: string;
}

/** Rose EmptyState with the typed error's message and a retry button. */
export function ErrorState({ error, what, onRetry, compact, className }: ErrorStateProps) {
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
