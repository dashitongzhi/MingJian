export function DisputeFocus({ disputes }: { disputes: any[] }) {
  if (!disputes || disputes.length === 0) return null;

  return (
    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-4">
      <div className="section-label">争议焦点</div>
      <div className="mt-4 space-y-2">
        {disputes.map((dispute, i) => (
          <div key={i} className="text-sm text-[var(--muted-foreground)]">{dispute}</div>
        ))}
      </div>
    </div>
  );
}
