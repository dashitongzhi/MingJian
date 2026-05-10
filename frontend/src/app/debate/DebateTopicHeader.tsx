export function DebateTopicHeader({ topic, status }: { topic: string; status: string }) {
  return (
    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-6">
      <h1 className="heading-section">{topic}</h1>
      <div className="mt-2 text-sm text-[var(--muted)]">状态: {status}</div>
    </div>
  );
}
