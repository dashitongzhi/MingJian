"use client";
import useSWR from "swr";
import { fetchSessions, fetchScoreboard, fetchQueueHealth, fetchWatchRules } from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";

function StatCard({ label, value, sub, trend, icon }: { label: string; value: string | number; sub?: string; trend?: "up" | "down" | "neutral"; icon: React.ReactNode }) {
  return (
    <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5 card-hover">
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs text-[var(--muted)] uppercase tracking-wider font-medium">{label}</div>
        <div className="w-8 h-8 rounded-lg bg-[var(--background)] flex items-center justify-center text-[var(--muted)]">
          {icon}
        </div>
      </div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="flex items-center gap-2 mt-2">
        {trend && (
          <span className={`text-xs flex items-center gap-1 ${trend === "up" ? "text-[var(--accent-green)]" : trend === "down" ? "text-[var(--accent-red)]" : "text-[var(--muted)]"}`}>
            {trend === "up" ? "↑" : trend === "down" ? "↓" : "→"} 12%
          </span>
        )}
        {sub && <span className="text-xs text-[var(--muted)]">{sub}</span>}
      </div>
    </div>
  );
}

function QuickAction({ label, description, icon, href }: { label: string; description: string; icon: React.ReactNode; href: string }) {
  return (
    <a href={href} className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-4 card-hover flex items-start gap-4">
      <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center text-blue-400 flex-shrink-0">
        {icon}
      </div>
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-[var(--muted)] mt-1">{description}</div>
      </div>
    </a>
  );
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const { data: sessions } = useSWR("sessions", fetchSessions, { refreshInterval: 30000 });
  const { data: sb } = useSWR("scoreboard", fetchScoreboard, { refreshInterval: 60000 });
  const { data: health } = useSWR("health", fetchQueueHealth, { refreshInterval: 15000 });
  const { data: rules } = useSWR("watch-rules", fetchWatchRules, { refreshInterval: 30000 });

  const pendingItems = health ? health.queues.reduce((s, q) => s + q.pending, 0) : 0;

  return (
    <div className="space-y-8">
      {/* Welcome section */}
      <div className="flex items-center gap-4">
        <img src="/mingjian-icon.jpg" alt="明鉴" className="w-14 h-14 rounded-xl object-cover shadow-lg" />
        <div>
          <h1 className="text-2xl font-bold">{t("dashboard.welcome")}</h1>
          <p className="text-[var(--muted)] mt-1">{t("dashboard.tagline")}</p>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label={t("dashboard.activeSessions")}
          value={sessions?.length ?? "—"}
          sub={t("dashboard.strategicAnalyses")}
          trend="up"
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          }
        />
        <StatCard
          label={t("dashboard.predictionAccuracy")}
          value={sb ? `${(sb.accuracy * 100).toFixed(0)}%` : "—"}
          sub={sb?.brier_score != null ? `${t("dashboard.brier")}: ${sb.brier_score.toFixed(3)}` : undefined}
          trend="up"
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
            </svg>
          }
        />
        <StatCard
          label={t("dashboard.queueHealth")}
          value={pendingItems}
          sub={t("dashboard.pendingItems")}
          trend={pendingItems > 10 ? "down" : "neutral"}
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M3 9h18" />
              <path d="M9 21V9" />
            </svg>
          }
        />
        <StatCard
          label={t("dashboard.watchRules")}
          value={rules?.filter((r) => r.enabled).length ?? "—"}
          sub={t("dashboard.activeMonitors")}
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          }
        />
      </div>

      {/* Quick Actions */}
      <div>
        <h2 className="text-lg font-semibold mb-4">{t("dashboard.quickActions")}</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <QuickAction
            label={t("dashboard.newAnalysis")}
            description={t("dashboard.newAnalysisDescription")}
            icon={
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35" />
              </svg>
            }
            href="/assistant"
          />
          <QuickAction
            label={t("dashboard.runSimulation")}
            description={t("dashboard.runSimulationDescription")}
            icon={
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 6v6l4 2" />
              </svg>
            }
            href="/simulation"
          />
          <QuickAction
            label={t("dashboard.startDebate")}
            description={t("dashboard.startDebateDescription")}
            icon={
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            }
            href="/debate"
          />
        </div>
      </div>

      {/* Scoreboard */}
      {sb && (
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4">{t("dashboard.predictionScoreboard")}</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
            {[
              { label: t("dashboard.totalHypotheses"), value: sb.total_hypotheses, color: "text-[var(--foreground)]" },
              { label: t("dashboard.confirmed"), value: sb.confirmed, color: "text-[var(--accent-green)]" },
              { label: t("dashboard.refuted"), value: sb.refuted, color: "text-[var(--accent-red)]" },
              { label: t("dashboard.pending"), value: sb.pending, color: "text-[var(--accent-yellow)]" },
              { label: t("dashboard.vsHuman"), value: sb.human_baseline_accuracy != null ? `${((sb.lift_over_human_baseline ?? 0) * 100).toFixed(1)}%` : "—", color: "text-[var(--accent)]" },
            ].map((item) => (
              <div key={item.label} className="text-center">
                <div className={`text-2xl font-bold ${item.color}`}>{item.value}</div>
                <div className="text-xs text-[var(--muted)] mt-1">{item.label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Sessions */}
      <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">{t("dashboard.recentSessions")}</h2>
          <a href="/assistant" className="text-sm text-[var(--accent)] hover:underline">{t("dashboard.viewAll")} →</a>
        </div>
        {sessions && sessions.length > 0 ? (
          <div className="space-y-3">
            {sessions.slice(0, 5).map((s) => (
              <a
                key={s.id}
                href={`/assistant?session=${s.id}`}
                className="flex items-center justify-between p-4 rounded-lg border border-[var(--card-border)] hover:border-[var(--accent)] hover:bg-[var(--card-hover)] transition-all"
              >
                <div className="flex items-center gap-4">
                  <div className={`w-2 h-2 rounded-full ${s.auto_refresh_enabled ? "bg-[var(--accent-green)]" : "bg-[var(--muted)]"}`} />
                  <div>
                    <div className="text-sm font-medium">{s.name || s.topic}</div>
                    <div className="text-xs text-[var(--muted)] mt-1">
                      {s.domain_id} &middot; {s.subject_name || t("common.auto").toLowerCase()}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`badge ${s.auto_refresh_enabled ? "badge-success" : "badge-warning"}`}>
                    {s.auto_refresh_enabled ? t("common.auto") : t("common.manual")}
                  </span>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--muted)]">
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </div>
              </a>
            ))}
          </div>
        ) : (
          <div className="empty-state py-8">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
            <div className="empty-state-title">{t("dashboard.noSessions")}</div>
            <div className="empty-state-description">{t("dashboard.noSessionsDescription")}</div>
          </div>
        )}
      </div>
    </div>
  );
}
