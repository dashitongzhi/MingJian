"use client";

import type { ReactNode } from "react";

/* ── Skeleton Card ────────────────────────────────────────────────────────── */

export function SkeletonCard({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div className={`rounded-xl border border-[var(--card-border)] bg-[var(--card)] p-5 ${className}`}>
      <div className="flex items-center gap-3">
        <div className="h-9 w-9 rounded-lg bg-[var(--card-border)] animate-pulse" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-1/2 rounded bg-[var(--card-border)] animate-pulse" />
          <div className="h-3 w-3/4 rounded bg-[var(--card-border)]/70 animate-pulse" />
        </div>
      </div>
      {lines > 0 && (
        <div className="mt-4 space-y-2">
          {Array.from({ length: lines }).map((_, i) => (
            <div key={i} className="h-3 rounded bg-[var(--card-border)]/50 animate-pulse" style={{ width: `${85 - i * 15}%` }} />
          ))}
        </div>
      )}
    </div>
  );
}

export function SkeletonGrid({ count = 6, lines = 3 }: { count?: number; lines?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} lines={lines} />
      ))}
    </div>
  );
}

/* ── Error State ──────────────────────────────────────────────────────────── */

export function ErrorState({
  title = "加载失败",
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-[var(--accent-red)]/20 bg-[var(--card)] py-16 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-full bg-[var(--accent-red-bg)]">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent-red)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
      </div>
      <div>
        <h3 className="text-sm font-semibold text-[var(--foreground)]">{title}</h3>
        {message && <p className="mt-1 max-w-sm text-xs text-[var(--muted)]">{message}</p>}
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-lg border border-[var(--card-border)] bg-[var(--background)] px-4 py-2 text-xs font-medium text-[var(--foreground)] transition-colors hover:border-[var(--accent)]"
        >
          重试
        </button>
      )}
    </div>
  );
}

/* ── Empty State ──────────────────────────────────────────────────────────── */

export function EmptyState({
  icon,
  title = "暂无数据",
  description,
  action,
}: {
  icon?: ReactNode;
  title?: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-[var(--card-border)] border-dashed bg-transparent py-16 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-full bg-[var(--card)] text-[var(--muted)]">
        {icon || (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 9V3H15" /><path d="M3 15V21H9" />
            <path d="M21 3L14 10" /><path d="M3 21L10 14" />
          </svg>
        )}
      </div>
      <div>
        <h3 className="text-sm font-medium text-[var(--foreground)]">{title}</h3>
        {description && <p className="mt-1 max-w-sm text-xs text-[var(--muted)]">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/* ── Status Badge ─────────────────────────────────────────────────────────── */

export function StatusDot({ status }: { status: "online" | "offline" | "warning" }) {
  const colors = {
    online: "bg-[var(--accent-green)]",
    offline: "bg-[var(--muted)]",
    warning: "bg-[var(--accent-yellow)]",
  };
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${colors[status]}`} />;
}

/* ── Count Badge ──────────────────────────────────────────────────────────── */

export function CountBadge({ count, total, label }: { count: number; total: number; label: string }) {
  return (
    <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card)] p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--muted)]">{label}</span>
        <span className="font-mono text-xs text-[var(--accent)]">{count}/{total}</span>
      </div>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[var(--background)]">
        <div
          className="h-full rounded-full bg-[var(--accent)] transition-[width,opacity] duration-300"
          style={{ width: total ? `${(count / total) * 100}%` : "0%" }}
        />
      </div>
    </div>
  );
}
