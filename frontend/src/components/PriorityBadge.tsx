"use client";

export function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    high: "badge badge-error",
    medium: "badge badge-warning",
    low: "badge badge-success",
  };
  return (
    <span className={colors[priority] || "badge badge-warning"}>
      {priority}
    </span>
  );
}
