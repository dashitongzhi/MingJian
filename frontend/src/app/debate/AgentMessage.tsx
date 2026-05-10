export function AgentMessage({ role, message }: { role: string; message: string }) {
  return (
    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-4">
      <div className="font-medium">{role}</div>
      <div className="mt-2 text-sm text-[var(--muted-foreground)]">{message}</div>
    </div>
  );
}
