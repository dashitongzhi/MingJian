"use client";
import useSWR from "swr";
import { fetchSessions, fetchScoreboard, fetchQueueHealth, fetchWatchRules } from "@/lib/api";

function Card({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4">
      <div className="text-xs text-[var(--muted)] uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
      {sub && <div className="text-xs text-[var(--muted)] mt-1">{sub}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const { data: sessions } = useSWR("sessions", fetchSessions, { refreshInterval: 30000 });
  const { data: sb } = useSWR("scoreboard", fetchScoreboard, { refreshInterval: 60000 });
  const { data: health } = useSWR("health", fetchQueueHealth, { refreshInterval: 15000 });
  const { data: rules } = useSWR("watch-rules", fetchWatchRules, { refreshInterval: 30000 });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Command Center</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card label="Active Sessions" value={sessions?.length ?? "—"} />
        <Card label="Prediction Accuracy" value={sb ? `${(sb.accuracy * 100).toFixed(0)}%` : "—"} sub={sb?.brier_score != null ? `Brier: ${sb.brier_score.toFixed(3)}` : undefined} />
        <Card label="Queue Health" value={health ? health.queues.reduce((s, q) => s + q.pending, 0) : "—"} sub="pending" />
        <Card label="Watch Rules" value={rules?.filter((r) => r.enabled).length ?? "—"} sub="active" />
      </div>

      {sb && (
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4">
          <h2 className="text-sm font-semibold mb-3">Prediction Scoreboard</h2>
          <div className="grid grid-cols-5 gap-4 text-center">
            {[["Total", sb.total_hypotheses], ["Confirmed", sb.confirmed], ["Refuted", sb.refuted], ["Pending", sb.pending], ["vs Human", sb.human_baseline_accuracy != null ? `${((sb.lift_over_human_baseline ?? 0) * 100).toFixed(1)}%` : "—"]].map(([l, v]) => (
              <div key={l as string}><div className="text-lg font-bold">{v as string | number}</div><div className="text-xs text-[var(--muted)]">{l}</div></div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4">
        <h2 className="text-sm font-semibold mb-3">Strategic Sessions</h2>
        {sessions && sessions.length > 0 ? (
          <div className="space-y-2">
            {sessions.map((s) => (
              <a key={s.id} href={`/assistant?session=${s.id}`} className="block p-3 rounded border border-[var(--card-border)] hover:border-[var(--accent)] transition-colors">
                <div className="flex justify-between"><div className="font-medium text-sm">{s.name || s.topic}</div><div className="text-xs text-[var(--muted)]">{s.auto_refresh_enabled ? "Auto" : "Manual"}</div></div>
                <div className="text-xs text-[var(--muted)] mt-1">{s.domain_id} &middot; {s.subject_name || "auto"}</div>
              </a>
            ))}
          </div>
        ) : <div className="text-sm text-[var(--muted)]">No sessions yet.</div>}
      </div>
    </div>
  );
}
