"use client";

import { PriorityBadge } from "./PriorityBadge";

function toText(value: unknown) {
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function RecommendationCard({
  rec,
  index,
  actionItemsLabel = "Action Items",
}: {
  rec: { title: string; priority?: string | null; rationale?: string | null; action_items?: string[] };
  index: number;
  actionItemsLabel?: string;
}) {
  const priority = rec.priority || "";
  const actionItems = rec.action_items || [];

  return (
    <div
      className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5 motion-safe:animate-[fadeIn_0.3s_ease-out]"
      style={{ animationDelay: `${index * 80}ms` }}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-3">
          <span className="font-mono text-lg text-[var(--accent)]">{String(index + 1).padStart(2, "0")}</span>
          <h4 className="text-sm font-semibold">{rec.title}</h4>
        </div>
        {priority && <PriorityBadge priority={priority} />}
      </div>
      {rec.rationale && (
        <p className="text-xs leading-6 text-[var(--muted-foreground)] mb-3 pl-8">{rec.rationale}</p>
      )}
      {actionItems.length > 0 && (
        <div className="divider-subtle pt-3 pl-8 mt-3">
          <div className="text-xs font-medium text-[var(--muted)] mb-2">{actionItemsLabel}</div>
          <div className="space-y-1.5">
            {actionItems.map((item, i) => (
              <div key={i} className="grid grid-cols-[18px_1fr] text-xs leading-5">
                <span className="text-[var(--accent)]">→</span>
                <span className="text-[var(--muted-foreground)]">{toText(item)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
