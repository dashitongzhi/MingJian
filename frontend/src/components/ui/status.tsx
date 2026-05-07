import type { ReactNode } from "react";

export function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="section-label">{children}</div>;
}

export function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`motion-safe:animate-pulse rounded bg-[var(--card-border)]/55 ${className}`} />;
}
