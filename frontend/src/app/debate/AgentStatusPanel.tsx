import type { DebateRound } from "@/lib/api";
import { roleLabel } from "./utils";

const EXPECTED_ROLES = [
  "advocate",
  "intel_analyst",
  "geo_expert",
  "econ_analyst",
  "military_strategist",
  "tech_foresight",
  "social_impact",
  "challenger",
  "arbitrator",
];

export function AgentStatusPanel({
  agents,
  rounds,
}: {
  agents?: any[];
  rounds?: DebateRound[];
}) {
  const participated = new Set((rounds || []).map((round) => round.role));
  const items = rounds?.length
    ? EXPECTED_ROLES.map((role) => ({ role, name: roleLabel(role), active: participated.has(role) }))
    : (agents || []).map((agent) => ({ role: agent.role, name: agent.name || agent.role, active: true }));
  return (
    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-4">
      <div className="section-label">智能体状态</div>
      <div className="mt-4 space-y-2">
        {items.map((agent, i) => (
          <div key={i} className="flex items-center justify-between gap-3 text-sm">
            <span>{agent.name}</span>
            <span className={agent.active ? "text-[var(--accent-green)]" : "text-[var(--muted)]"}>
              {agent.active ? "已参与" : "等待"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
