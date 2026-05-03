"use client";

import type { ReactNode } from "react";
import { useMemo } from "react";
import Image from "next/image";
import useSWR from "swr";
import {
  TrendingUp,
  Target,
  Activity,
  Brain,
  Shield,
  Zap,
  Search,
  Play,
  MessageSquare,
} from "lucide-react";
import { fetchSessions, fetchScoreboard, fetchQueueHealth, fetchWatchRules, type StrategicSession } from "@/lib/api";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/ui/data-table";
import { useTranslation } from "@/contexts/LanguageContext";
import { TextReveal, StaggerContainer, StaggerItem, AnimatedGradientText } from "@/components/ui/aceternity";

function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
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
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="min-h-[270px] rounded-2xl bg-[var(--card)] p-7">
          <SkeletonLine className="h-4 w-36" />
          <SkeletonLine className="mt-5 h-12 w-32" />
          <div className="mt-8 grid grid-cols-6 gap-1">
            {Array.from({ length: 12 }).map((_, i) => (
              <SkeletonLine key={i} className="aspect-[1.7]" />
            ))}
          </div>
        </div>
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="min-h-[270px] rounded-2xl bg-[var(--card)] p-7">
            <SkeletonLine className="h-4 w-28" />
            <SkeletonLine className="mt-5 h-10 w-24" />
            <SkeletonLine className="mt-8 h-2 w-full" />
            <SkeletonLine className="mt-4 h-2 w-3/4" />
          </div>
        ))}
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="section-label">{children}</div>;
}

function ErrorNotice({ children }: { children: ReactNode }) {
  return (
    <div className="border-l-2 border-[var(--accent-red)] bg-[var(--accent-red-bg)] px-4 py-3 text-sm text-[var(--accent-red)] rounded-r-lg">
      {children}
    </div>
  );
}

function MetricPanel({
  label,
  value,
  sub,
  icon,
  large = false,
  children,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon?: ReactNode;
  large?: boolean;
  children?: ReactNode;
}) {
  return (
    <section
      className={`group relative overflow-hidden liquid-glass iridescent
        h-full min-h-[270px] rounded-2xl p-7 hover:-translate-y-0.5`}
    >
      {/* Top edge light refraction */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
      {/* Bottom edge shadow */}
      <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-black/5 to-transparent" />
      {/* Accent glow on hover */}
      <div className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-500 group-hover:opacity-100"
        style={{
          background: "radial-gradient(ellipse at 30% 20%, rgba(127,159,144,0.06) 0%, transparent 60%)",
        }}
      />
      <div className="relative z-10 flex h-full flex-col">
        <div className="flex items-center gap-2.5">
          {icon && (
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--accent)]/10 text-[var(--accent)]">
              {icon}
            </span>
          )}
          <SectionLabel>{label}</SectionLabel>
        </div>
        <div className="mt-5 flex min-h-14 items-end gap-3">
          <div className={`${large ? "text-5xl" : "text-4xl"} font-semibold leading-none tracking-normal text-balance`}>
            {value}
          </div>
          {sub && <div className="pb-1 text-sm text-[var(--muted-foreground)]">{sub}</div>}
        </div>
        {children}
      </div>
    </section>
  );
}

function AccuracyMatrix({ accuracy, pending }: { accuracy: number | null; pending: number }) {
  const filled = accuracy == null ? 0 : Math.max(0, Math.min(12, Math.round(accuracy * 12)));

  return (
    <div className="mt-8">
      <div className="grid grid-cols-6 gap-px bg-[var(--card-border)]/50">
        {Array.from({ length: 12 }).map((_, i) => (
          <div
            key={i}
            className={`aspect-[1.7] transition-all duration-500 ${
              i < filled ? "bg-[var(--accent)]/70" : "bg-[var(--code-bg)]"
            }`}
            style={{ opacity: i < filled ? 0.5 + i * 0.035 : 1, transitionDelay: `${i * 40}ms` }}
          />
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between border-t border-[var(--foreground)]/5 pt-4 text-xs text-[var(--muted)]">
        <span>{pending} pending</span>
        <span>{filled}/12 signal cells</span>
      </div>
    </div>
  );
}

function QueueBars({ queues }: { queues: Array<{ queue: string; pending: number; processing: number; completed: number; failed: number }> }) {
  const max = Math.max(1, ...queues.map((q) => q.pending + q.processing + q.completed + q.failed));

  if (queues.length === 0) {
    return <div className="mt-5 pt-4 text-sm text-[var(--muted)]">—</div>;
  }

  return (
    <div className="mt-6 space-y-3.5">
      {queues.slice(0, 4).map((q) => {
        const total = q.pending + q.processing + q.completed + q.failed;
        return (
          <div key={q.queue} className="grid grid-cols-[minmax(0,1fr)_90px] items-center gap-4">
            <div className="min-w-0">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="truncate font-mono text-[var(--muted-foreground)]">{q.queue}</span>
                <span className="text-[var(--muted)]">{total}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden bg-[var(--code-bg)] rounded-full">
                <div
                  className="h-full origin-left bg-[var(--accent)]/70 transition-transform duration-700 ease-out rounded-full"
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
      className="group grid grid-cols-[32px_minmax(0,1fr)_18px] gap-4 py-5 outline-none transition-all duration-200 hover:bg-[var(--card)]/50 hover:pl-2 focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]"
    >
      <div className="flex h-8 w-8 items-center justify-center text-[var(--accent)] transition-transform duration-300 group-hover:scale-110">
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-sm font-medium text-[var(--foreground)]">{label}</div>
        <div className="mt-1 text-[13px] text-[var(--muted)] leading-relaxed">{description}</div>
      </div>
      <div className="pt-1 text-[var(--muted)] transition-transform duration-300 group-hover:translate-x-1 group-hover:text-[var(--accent)]">→</div>
    </a>
  );
}

function EmptySessions({ title, description }: { title: string; description: string }) {
  return (
    <div className="py-14">
      <div className="max-w-sm">
        <div className="text-sm font-medium text-[var(--foreground)]">{title}</div>
        <div className="mt-2 text-[13px] leading-relaxed text-[var(--muted)]">{description}</div>
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

  const sessionColumns = useMemo<ColumnDef<StrategicSession>[]>(
    () => [
      {
        accessorKey: "name",
        header: t("dashboard.sessionName"),
        cell: ({ row }) => row.original.name || row.original.topic,
      },
      {
        accessorKey: "auto_refresh_enabled",
        header: t("common.status"),
        cell: ({ row }) => (
          <span className="border border-[var(--card-border)] px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
            {row.original.auto_refresh_enabled ? t("common.auto") : t("common.manual")}
          </span>
        ),
      },
      {
        accessorKey: "created_at",
        header: t("dashboard.createdAt"),
        cell: ({ row }) => new Date(row.original.created_at).toLocaleDateString(),
      },
    ],
    [t],
  );

  if (isLoading) return <DashboardSkeleton />;

  return (
    <div className="space-y-8">
      {/* ── Hero Header ──────────────────────────────────────────────────────── */}
      <header className="relative pb-4">
        <div className="absolute right-0 top-0 h-24 w-64 bg-[var(--accent)]/4 blur-3xl rounded-full" />
        <TextReveal>
          <div className="relative">
            <div className="flex items-center gap-3 mb-4">
              <Image src="/mingjian-icon.jpg" alt="明鉴" width={40} height={40} className="rounded-lg object-cover" />
              <SectionLabel>{t("dashboard.welcome")}</SectionLabel>
            </div>
            <AnimatedGradientText className="block max-w-2xl text-4xl font-bold leading-tight tracking-tight text-balance">
              {t("dashboard.tagline")}
            </AnimatedGradientText>
            <p className="mt-4 max-w-xl text-base text-[var(--muted)] leading-relaxed">
              {t("dashboard.taglineSubtitle")}
            </p>
          </div>
        </TextReveal>
      </header>

      {hasError && (
        <ErrorNotice>
          {sessionsError?.message || scoreboardError?.message || healthError?.message || rulesError?.message}
        </ErrorNotice>
      )}

      {/* ── Overview Metrics ─────────────────────────────────────────────────── */}
      <StaggerContainer className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4" staggerDelay={0.06}>
        <StaggerItem className="min-w-0">
          <MetricPanel
            large
            label={t("dashboard.predictionAccuracy")}
            value={accuracy == null ? "—" : `${(accuracy * 100).toFixed(0)}%`}
            sub={sb?.brier_score != null ? `${t("dashboard.brier")}: ${sb.brier_score.toFixed(3)}` : t("dashboard.predictionScoreboard")}
            icon={<Target size={16} />}
          >
            <AccuracyMatrix accuracy={accuracy} pending={sb?.pending ?? 0} />
          </MetricPanel>
        </StaggerItem>

        <StaggerItem className="min-w-0">
          <MetricPanel
            label={t("dashboard.activeSessions")}
            value={sessions ? activeSessions : "—"}
            sub={t("dashboard.strategicAnalyses")}
            icon={<Brain size={16} />}
          >
            <div className="mt-6 h-px bg-[var(--foreground)]/5" />
            <div className="mt-4 grid grid-cols-2 gap-4 text-xs text-[var(--muted)]">
              <span>{t("dashboard.activeMonitors")}</span>
              <span className="text-right font-mono text-[var(--muted-foreground)]">{activeRules}</span>
            </div>
          </MetricPanel>
        </StaggerItem>

        <StaggerItem className="min-w-0">
          <MetricPanel
            label={t("dashboard.queueHealth")}
            value={health ? pendingItems : "—"}
            sub={t("dashboard.pendingItems")}
            icon={<Activity size={16} />}
          >
            <QueueBars queues={health?.queues ?? []} />
          </MetricPanel>
        </StaggerItem>

        <StaggerItem className="min-w-0">
          <MetricPanel
            label={t("dashboard.watchRules")}
            value={rules ? activeRules : "—"}
            sub={t("dashboard.activeMonitors")}
            icon={<Shield size={16} />}
          >
            <div className="mt-6 grid grid-cols-8 gap-px bg-[var(--card-border)]/50">
              {Array.from({ length: Math.max(8, rules?.length || 8) }).slice(0, 24).map((_, i) => (
                <div
                  key={i}
                  className={`aspect-square transition-all duration-300 ${
                    rules && i < rules.length && rules[i].enabled ? "bg-[var(--accent)]/60" : "bg-[var(--code-bg)]"
                  }`}
                  style={{ transitionDelay: `${i * 30}ms` }}
                />
              ))}
            </div>
          </MetricPanel>
        </StaggerItem>
      </StaggerContainer>

      {/* ── Quick Actions & Sessions ─────────────────────────────────────────── */}
      <StaggerContainer className="grid grid-cols-1 gap-6 lg:grid-cols-2 xl:grid-cols-[minmax(280px,0.85fr)_minmax(280px,0.85fr)_minmax(520px,1.3fr)]" staggerDelay={0.06}>
        <StaggerItem className="min-w-0">
          <section className="h-full min-h-[270px] rounded-2xl liquid-glass p-7">
            <h2 className="mb-1 text-lg font-semibold text-balance">{t("dashboard.quickActions")}</h2>
            <div className="mt-4 space-y-0 divide-y divide-[var(--foreground)]/5">
              <QuickAction
                label={t("dashboard.newAnalysis")}
                description={t("dashboard.newAnalysisDescription")}
                href="/assistant"
                icon={<Search size={18} />}
              />
              <QuickAction
                label={t("dashboard.runSimulation")}
                description={t("dashboard.runSimulationDescription")}
                href="/simulation"
                icon={<Play size={18} />}
              />
              <QuickAction
                label={t("dashboard.startDebate")}
                description={t("dashboard.startDebateDescription")}
                href="/debate"
                icon={<MessageSquare size={18} />}
              />
            </div>
          </section>
        </StaggerItem>

        <StaggerItem className="min-w-0">
          <MetricPanel
            label={t("dashboard.vsHuman")}
            value={lift}
            sub={t("dashboard.totalHypotheses")}
            icon={<TrendingUp size={16} />}
          >
            <div className="mt-5 flex items-end gap-2">
              {[sb?.confirmed ?? 0, sb?.refuted ?? 0, sb?.pending ?? 0].map((value, i) => {
                const max = Math.max(1, sb?.confirmed ?? 0, sb?.refuted ?? 0, sb?.pending ?? 0);
                return (
                  <div key={i} className="flex flex-1 flex-col items-center gap-2">
                    <div className="flex h-20 w-full items-end bg-[var(--code-bg)] rounded-sm overflow-hidden">
                      <div
                        className="w-full origin-bottom transition-transform duration-700 ease-out"
                        style={{
                          height: "100%",
                          transform: `scaleY(${value / max})`,
                          background: `linear-gradient(to top, var(--accent), rgba(127, 159, 144, ${0.3 + i * 0.2}))`,
                        }}
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
        </StaggerItem>

        <StaggerItem className="min-w-0 lg:col-span-2 xl:col-span-1">
          <section className="h-full min-h-[270px] rounded-2xl liquid-glass p-7">
            <div className="mb-4 flex items-center justify-between gap-4">
              <h2 className="text-lg font-semibold text-balance">{t("dashboard.recentSessions")}</h2>
              <Zap size={16} className="text-[var(--accent)]/60" />
            </div>

            {sessions && sessions.length > 0 ? (
              <DataTable
                columns={sessionColumns}
                data={sessions.slice(0, 10)}
                searchColumn="name"
                searchPlaceholder={t("dashboard.sessionName") + "..."}
                pageSize={5}
                onRowClick={(s) => window.location.assign(`/assistant?session=${s.id}`)}
              />
            ) : (
              <EmptySessions title={t("dashboard.noSessions")} description={t("dashboard.noSessionsDescription")} />
            )}
          </section>
        </StaggerItem>
      </StaggerContainer>
    </div>
  );
}
