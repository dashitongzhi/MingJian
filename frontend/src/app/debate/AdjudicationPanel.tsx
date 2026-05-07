"use client";

import type { DebateVerdict } from "@/lib/api";

export function LiveVerdictCard({ verdict }: { verdict: DebateVerdict }) {
  return (
    <section className="rounded-lg border border-[var(--accent)]/40 bg-[var(--card)] p-5 animate-scaleIn">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="section-label !text-[var(--accent)]">实时裁决</div>
          <h3 className="mt-2 text-lg font-semibold uppercase">{verdict.verdict}</h3>
        </div>
        <span className="badge badge-success">{(Math.max(0, Math.min(1, verdict.confidence)) * 100).toFixed(0)}%</span>
      </div>
      <div className="space-y-2">
        {verdict.winning_arguments.map((argument, index) => (
          <div key={`${argument}-${index}`} className="grid grid-cols-[28px_1fr] text-sm leading-6 text-[var(--muted-foreground)]">
            <span className="font-mono text-xs text-[var(--accent)]">{String(index + 1).padStart(2, "0")}</span>
            <span>{argument}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
