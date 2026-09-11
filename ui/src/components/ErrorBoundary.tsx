import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorState } from "@/components/ErrorState";

export interface ErrorBoundaryProps {
  children: ReactNode;
  /** What the failing subtree was showing, for the message ("the overview"). */
  what?: string;
  /** Changing this key resets the boundary (e.g. the route path). */
  resetKey?: string;
}

interface State {
  error: unknown;
}

/** Catches a render error in a page so the shell and navigation survive; the ErrorState offers a retry. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error };
  }

  override componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error("Page render failed", error, info.componentStack);
  }

  override componentDidUpdate(prev: ErrorBoundaryProps): void {
    if (prev.resetKey !== this.props.resetKey && this.state.error !== null) this.setState({ error: null });
  }

  override render(): ReactNode {
    if (this.state.error !== null) {
      return <ErrorState error={this.state.error} what={this.props.what ?? "this page"} onRetry={() => this.setState({ error: null })} />;
    }
    return this.props.children;
  }
}
