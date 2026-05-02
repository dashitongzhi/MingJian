"use client";

import type { ReactNode } from "react";
import useSWR from "swr";
import { fetchSessions, fetchScoreboard, fetchQueueHealth, fetchWatchRules } from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";

function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`motion-safe:animate-pulse rounded bg-[var(--card-border)]/50 ${className}`} />;
}

function DashboardSkeleton() {
  return (
    <div className="space-y-8">
      <div className="flex items-end justify-between gap-6">
        <div className="space-y-3">
          <SkeletonLine className="h-5 w-28" />
          <SkeletonLine className="h-9 w-72 max-w-full" />
          <SkeletonLine className="h-4 w-96 max-w-full" />
        </div>
        <SkeletonLine className="hidden h-16 w-16 rounded md:block" />
      </div>
      <div className="grid grid-cols-1 gap-px overflow-hidden rounded-lg bg-[var(--card-border)] lg:grid-cols-12">
        <div className="bg-[var(--card)] p-6 lg:col-span-7 lg:row-span-2">
          <SkeletonLine className="h-4 w-36" />
          <SkeletonLine className="mt-6 h-16 w-40" />
          <div className="mt-8 grid grid-cols-4 gap-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <SkeletonLine key={i} className="h-20" />
            ))}
          </div>
        </div>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-[var(--card)] p-6 lg:col-span-5">
            <SkeletonLine className="h-4 w-28" />
            <SkeletonLine className="mt-5 h-10 w-24" />
            <SkeletonLine className="mt-4 h-2 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--muted)]">{children}</div>;
}

function ErrorNotice({ children }: { children: ReactNode }) {
  return (
    <div className="border-l border-[var(--accent-red)] bg-[var(--accent-red-bg)] px-4 py-3 text-sm text-[var(--accent-red)]">
      {children}
    </div>
  );
}

function MetricPanel({
  label,
  value,
  sub,
  large = false,
  children,
}: {
  label: string;
  value: string | number;
  sub?: string;
  large?: boolean;
  children?: ReactNode;
}) {
  return (
    <section className={`bg-[var(--card)] p-6 ${large ? "lg:col-span-7 lg:row-span-2" : "lg:col-span-5"}`}>
      <SectionLabel>{label}</SectionLabel>
      <div className={large ? "mt-6 flex items-end gap-5" : "mt-5 flex items-end gap-3"}>
        <div className={`${large ? "text-6xl" : "text-4xl"} font-semibold leading-none tracking-tight text-balance`}>
          {value}
        </div>
        {sub && <div className="pb-1 text-sm text-[var(--muted-foreground)]">{sub}</div>}
      </div>
      {children}
    </section>
  );
}

function AccuracyMatrix({ accuracy, pending }: { accuracy: number | null; pending: number }) {
  const filled = accuracy == null ? 0 : Math.max(0, Math.min(12, Math.round(accuracy * 12)));

  return (
    <div className="mt-10">
      <div className="grid grid-cols-6 gap-px bg-[var(--card-border)]/70">
        {Array.from({ length: 12 }).map((_, i) => (
          <div
            key={i}
            className={`aspect-[1.7] motion-safe:transition-opacity ${
              i < filled ? "bg-[var(--accent)]/80" : "bg-[#0f0e0c]"
            }`}
            style={{ opacity: i < filled ? 0.45 + i * 0.035 : 1 }}
          />
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between border-t border-[var(--card-border)] pt-4 text-xs text-[var(--muted)]">
        <span>{pending} {pending === 1 ? "pending" : "pending"}</span>
        <span>{filled}/12 signal cells</span>
      </div>
    </div>
  );
}

function QueueBars({ queues }: { queues: Array<{ queue: string; pending: number; processing: number; completed: number; failed: number }> }) {
  const max = Math.max(1, ...queues.map((q) => q.pending + q.processing + q.completed + q.failed));

  if (queues.length === 0) {
    return <div className="mt-5 border-t border-[var(--card-border)] pt-4 text-sm text-[var(--muted)]">—</div>;
  }

  return (
    <div className="mt-6 space-y-4">
      {queues.slice(0, 4).map((q) => {
        const total = q.pending + q.processing + q.completed + q.failed;
        return (
          <div key={q.queue} className="grid grid-cols-[minmax(0,1fr)_90px] items-center gap-4">
            <div className="min-w-0">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="truncate font-mono text-[var(--muted-foreground)]">{q.queue}</span>
                <span className="text-[var(--muted)]">{total}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden bg-[#0f0e0c]">
                <div
                  className="h-full origin-left bg-[var(--accent)]/75 motion-safe:transition-transform"
                  style={{ transform: `scaleX(${total / max})` }}
                />
              </div>
            </div>
            <div className="text-right text-xs text-[var(--muted)]">
              {q.processing} / {q.pending}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function QuickAction({ label, description, icon, href }: { label: string; description: string; icon: ReactNode; href: string }) {
  return (
    <a
      href={href}
      className="group grid grid-cols-[32px_minmax(0,1fr)_18px] gap-4 border-t border-[var(--card-border)] py-5 outline-none motion-safe:transition-opacity hover:opacity-85 focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]"
    >
      <div className="flex h-8 w-8 items-center justify-center text-[var(--accent)]">{icon}</div>
      <div className="min-w-0">
        <div className="text-sm font-medium text-[var(--foreground)]">{label}</div>
        <div className="mt-1 text-sm text-[var(--muted)]">{description}</div>
      </div>
      <div className="pt-1 text-[var(--muted)] motion-safe:transition-transform group-hover:translate-x-1">→</div>
    </a>
  );
}

function EmptySessions({ title, description }: { title: string; description: string }) {
  return (
    <div className="border-t border-[var(--card-border)] py-12">
      <div className="max-w-sm">
        <div className="text-sm font-medium text-[var(--foreground)]">{title}</div>
        <div className="mt-2 text-sm leading-6 text-[var(--muted)]">{description}</div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const { data: sessions, error: sessionsError } = useSWR("sessions", fetchSessions, { refreshInterval: 30000 });
  const { data: sb, error: scoreboardError } = useSWR("scoreboard", fetchScoreboard, { refreshInterval: 60000 });
  const { data: health, error: healthError } = useSWR("health", fetchQueueHealth, { refreshInterval: 15000 });
  const { data: rules, error: rulesError } = useSWR("watch-rules", fetchWatchRules, { refreshInterval: 30000 });

  const activeSessions = sessions?.length ?? 0;
  const pendingItems = health ? health.queues.reduce((s, q) => s + q.pending, 0) : 0;
  const processingItems = health ? health.queues.reduce((s, q) => s + q.processing, 0) : 0;
  const activeRules = rules?.filter((r) => r.enabled).length ?? 0;
  const hasError = sessionsError || scoreboardError || healthError || rulesError;
  const hasData = sessions || sb || health || rules;
  const isLoading = !hasData && !hasError;
  const accuracy = sb?.accuracy ?? null;
  const lift = sb?.human_baseline_accuracy != null ? `${((sb.lift_over_human_baseline ?? 0) * 100).toFixed(1)}%` : "—";

  if (isLoading) return <DashboardSkeleton />;

  return (
    <div className="space-y-10">
      <header className="relative overflow-hidden border-b border-[var(--card-border)] pb-8">
        <div className="absolute right-0 top-0 h-24 w-64 bg-[var(--accent)]/10 blur-3xl" />
        <div className="relative flex items-end justify-between gap-6">
          <div className="max-w-3xl">
            <div className="flex items-center gap-3">
              <img src="/mingjian-icon.jpg" alt="明鉴" className="h-10 w-10 rounded object-cover" />
              <SectionLabel>{t("dashboard.welcome")}</SectionLabel>
            </div>
            <h1 className="mt-5 max-w-2xl text-4xl font-semibold leading-tight tracking-tight text-balance">
              {t("dashboard.tagline")}
            </h1>
          </div>
          <div className="hidden min-w-44 border-l border-[var(--card-border)] pl-6 md:block">
            <div className="text-xs text-[var(--muted)]">{t("dashboard.queueHealth")}</div>
            <div className="mt-2 font-mono text-2xl text-[var(--accent)]">{pendingItems + processingItems}</div>
          </div>
        </div>
      </header>

      {hasError && (
        <ErrorNotice>
          {sessionsError?.message || scoreboardError?.message || healthError?.message || rulesError?.message}
        </ErrorNotice>
      )}

      <div className="grid grid-cols-1 gap-px overflow-hidden rounded-lg bg-[var(--card-border)] lg:grid-cols-12">
        <MetricPanel
          large
          label={t("dashboard.predictionAccuracy")}
          value={accuracy == null ? "—" : `${(accuracy * 100).toFixed(0)}%`}
          sub={sb?.brier_score != null ? `${t("dashboard.brier")}: ${sb.brier_score.toFixed(3)}` : t("dashboard.predictionScoreboard")}
        >
          <AccuracyMatrix accuracy={accuracy} pending={sb?.pending ?? 0} />
        </MetricPanel>

        <MetricPanel label={t("dashboard.activeSessions")} value={sessions ? activeSessions : "—"} sub={t("dashboard.strategicAnalyses")}>
          <div className="mt-6 h-px bg-[var(--card-border)]" />
          <div className="mt-4 grid grid-cols-2 gap-4 text-xs text-[var(--muted)]">
            <span>{t("dashboard.activeMonitors")}</span>
            <span className="text-right font-mono text-[var(--muted-foreground)]">{activeRules}</span>
          </div>
        </MetricPanel>

        <MetricPanel label={t("dashboard.queueHealth")} value={health ? pendingItems : "—"} sub={t("dashboard.pendingItems")}>
          <QueueBars queues={health?.queues ?? []} />
        </MetricPanel>

        <MetricPanel label={t("dashboard.watchRules")} value={rules ? activeRules : "—"} sub={t("dashboard.activeMonitors")}>
          <div className="mt-6 grid grid-cols-8 gap-px bg-[var(--card-border)]/70">
            {Array.from({ length: Math.max(8, rules?.length || 8) }).slice(0, 24).map((_, i) => (
              <div
                key={i}
                className={`aspect-square ${rules && i < rules.length && rules[i].enabled ? "bg-[var(--accent)]/70" : "bg-[#0f0e0c]"}`}
              />
            ))}
          </div>
        </MetricPanel>

        <MetricPanel label={t("dashboard.vsHuman")} value={lift} sub={t("dashboard.totalHypotheses")}>
          <div className="mt-5 flex items-end gap-2">
            {[sb?.confirmed ?? 0, sb?.refuted ?? 0, sb?.pending ?? 0].map((value, i) => {
              const max = Math.max(1, sb?.confirmed ?? 0, sb?.refuted ?? 0, sb?.pending ?? 0);
              return (
                <div key={i} className="flex flex-1 flex-col items-center gap-2">
                  <div className="flex h-20 w-full items-end bg-[#0f0e0c]">
                    <div
                      className="w-full origin-bottom bg-[var(--accent)]/70 motion-safe:transition-transform"
                      style={{ height: "100%", transform: `scaleY(${value / max})`, opacity: 0.45 + i * 0.18 }}
                    />
                  </div>
                  <span className="text-[10px] uppercase tracking-wide text-[var(--muted)]">
                    {[t("dashboard.confirmed"), t("dashboard.refuted"), t("dashboard.pending")][i]}
                  </span>
                </div>
              );
            })}
          </div>
        </MetricPanel>
      </div>

      <div className="grid grid-cols-1 gap-10 xl:grid-cols-[minmax(0,0.8fr)_minmax(460px,1.2fr)]">
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-balance">{t("dashboard.quickActions")}</h2>
          </div>
          <QuickAction
            label={t("dashboard.newAnalysis")}
            description={t("dashboard.newAnalysisDescription")}
            href="/assistant"
            icon={
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35" />
              </svg>
            }
          />
          <QuickAction
            label={t("dashboard.runSimulation")}
            description={t("dashboard.runSimulationDescription")}
            href="/simulation"
            icon={
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 6v6l4 2" />
              </svg>
            }
          />
          <QuickAction
            label={t("dashboard.startDebate")}
            description={t("dashboard.startDebateDescription")}
            href="/debate"
            icon={
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            }
          />
        </section>

        <section className="min-w-0">
          <div className="mb-4 flex items-center justify-between gap-4">
            <h2 className="text-lg font-semibold text-balance">{t("dashboard.recentSessions")}</h2>
            <a
              href="/assistant"
              className="text-sm text-[var(--accent)] outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]"
            >
              {t("dashboard.viewAll")} →
            </a>
          </div>

          {sessions && sessions.length > 0 ? (
            <div className="divide-y divide-[var(--card-border)] border-y border-[var(--card-border)]">
              {sessions.slice(0, 5).map((s, i) => (
                <a
                  key={s.id}
                  href={`/assistant?session=${s.id}`}
                  className="grid grid-cols-[42px_minmax(0,1fr)_auto] items-center gap-4 py-4 outline-none motion-safe:transition-colors hover:bg-[var(--card)]/70 focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]"
                >
                  <div className="font-mono text-xs text-[var(--muted)]">{String(i + 1).padStart(2, "0")}</div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{s.name || s.topic}</div>
                    <div className="mt-1 truncate text-xs text-[var(--muted)]">
                      {s.domain_id} · {s.subject_name || t("common.auto").toLowerCase()}
                    </div>
                  </div>
                  <span className="border-l border-[var(--card-border)] pl-4 text-xs text-[var(--muted-foreground)]">
                    {s.auto_refresh_enabled ? t("common.auto") : t("common.manual")}
                  </span>
                </a>
              ))}
            </div>
          ) : (
            <EmptySessions title={t("dashboard.noSessions")} description={t("dashboard.noSessionsDescription")} />
          )}
        </section>
      </div>
    </div>
  );
}
