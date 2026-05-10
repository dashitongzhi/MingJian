export function VerdictResult({ verdict }: { verdict: any }) {
  return (
    <div className="rounded-lg border border-[var(--accent)]/40 bg-[var(--card)] p-6">
      <div className="section-label !text-[var(--accent)]">最终裁决</div>
      <div className="mt-4 text-lg font-semibold">{verdict?.verdict || "待定"}</div>
      {verdict?.winning_arguments && (
        <ul className="mt-4 space-y-2">
          {verdict.winning_arguments.map((arg: string, i: number) => (
            <li key={i} className="text-sm text-[var(--muted-foreground)]">{arg}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
