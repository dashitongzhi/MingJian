import type { DebateDetail } from "@/lib/api";

export function DebateTopicHeader({
  debate,
  topic,
  status,
  roundCount,
}: {
  debate?: DebateDetail;
  topic?: string;
  status?: string;
  roundCount?: number;
  liveStatus?: string;
  onNextRound?: () => void;
  onEndDebate?: () => void;
}) {
  const title = debate?.topic || topic || "辩论";
  const currentStatus = debate?.status || status || "UNKNOWN";
  return (
    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-6">
      <h1 className="heading-section">{title}</h1>
      <div className="mt-2 text-sm text-[var(--muted)]">
        状态: {currentStatus}
        {typeof roundCount === "number" ? ` · ${roundCount} 轮发言` : ""}
      </div>
    </div>
  );
}
