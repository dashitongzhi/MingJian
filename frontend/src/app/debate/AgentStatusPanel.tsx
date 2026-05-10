export function AgentStatusPanel({ agents }: { agents: any[] }) {
  return (
    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-4">
      <div className="section-label">智能体状态</div>
      <div className="mt-4 space-y-2">
        {agents.map((agent, i) => (
          <div key={i} className="text-sm">{agent.name || agent.role}</div>
        ))}
      </div>
    </div>
  );
}
