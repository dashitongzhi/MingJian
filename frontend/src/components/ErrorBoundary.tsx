"use client";

import { Component, type ReactNode, type ErrorInfo } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info);
    this.props.onError?.(error, info);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex min-h-[300px] flex-col items-center justify-center gap-4 rounded-xl border border-[var(--accent-red)]/20 bg-[var(--card)] p-8 text-center">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-[var(--accent-red-bg)]">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent-red)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[var(--foreground)]">页面渲染出错</h3>
            <p className="mt-1 max-w-md text-xs text-[var(--muted)]">
              {this.state.error?.message || "发生了未知错误"}
            </p>
          </div>
          <button
            onClick={this.handleRetry}
            className="rounded-lg bg-[var(--accent)] px-4 py-2 text-xs font-medium text-black transition-opacity hover:opacity-90"
          >
            重试
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
