"use client";

import { useState, useEffect, useRef, useCallback, type ReactNode } from "react";
import { useTranslation } from "@/contexts/LanguageContext";
import { apiFetch } from "@/lib/api";

interface WatchRuleHealth {
  id: string;
  name: string;
  status?: string | null;
  healthy?: boolean | null;
  last_poll?: string | null;
  failures?: number | null;
}

interface RecentChange {
  id: string;
  source_type: string;
  significance?: string | number | null;
  diff_summary?: string | null;
  created_at?: string | null;
}

interface StatusStats {
  pending?: number;
  processing?: number;
  completed?: number;
  failed?: number;
  active?: number;
  superseded?: number;
  verified?: number;
}

interface CalibrationDistribution {
  high?: number;
  medium?: number;
  low?: number;
}

interface CalibrationStats {
  high_accuracy_rules?: number;
  medium_accuracy_rules?: number;
  low_accuracy_rules?: number;
  avg_accuracy?: number;
  total_rules?: number;
  source_trust_distribution?: CalibrationDistribution;
  total_sources?: number;
  avg_trust?: number;
}

interface MonitoringDashboard {
  watch_rules?: WatchRuleHealth[];
  watchRules?: WatchRuleHealth[];
  recent_changes?: RecentChange[];
  recentChanges?: RecentChange[];
  revision_jobs?: StatusStats;
  revisionJobs?: StatusStats;
  predictions?: StatusStats;
  calibration?: CalibrationStats;
}

interface MonitoringEvent {
  id?: string;
  event?: string;
  topic?: string;
  type?: string;
  payload?: Record<string, unknown>;
  created_at?: string;
  timestamp?: string;
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatPercent(value?: number) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function percentWidth(value: number, total: number) {
  if (total <= 0) return "0%";
  return `${Math.max(0, Math.min(100, (value / total) * 100))}%`;
}

function HealthDot({ healthy, failures = 0 }: { healthy: boolean; failures?: number | null }) {
  const tone = healthy ? "bg-[var(--accent-green)]" : failures && failures > 2 ? "bg-[var(--accent-red)]" : "bg-[var(--accent-yellow)]";
  return <span className={`inline-block h-2 w-2 rounded-full ${tone}`} />;
}

function EventLabel({ event }: { event: MonitoringEvent }) {
  return (
    <span className="badge badge-premium font-mono">
      {event.event || event.topic || event.type || "event"}
    </span>
  );
}

function BentoPanel({
  title,
  children,
  className = "",
  action,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  return (
    <section className={`card rounded-xl p-5 ${className}`}>
      <div className="mb-5 flex items-center justify-between gap-4">
        <h2 className="heading-section">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function InlineMetric({ label, value, tone = "default" }: { label: string; value: number; tone?: "default" | "green" | "yellow" | "red" }) {
  const toneClass =
    tone === "green"
      ? "text-[var(--accent-green)]"
      : tone === "yellow"
        ? "text-[var(--accent-yellow)]"
        : tone === "red"
          ? "text-[var(--accent-red)]"
          : "text-[var(--foreground)]";

  return (
    <div className="border-b border-[var(--card-border)] py-3 last:border-b-0">
      <div className="flex items-baseline justify-between gap-4">
        <span className="section-label">{label}</span>
        <span className={`font-mono text-xl ${toneClass}`}>{value}</span>
      </div>
    </div>
  );
}

function DistributionBar({ high, medium, low }: { high: number; medium: number; low: number }) {
  const total = high + medium + low;

  return (
    <div className="h-2 overflow-hidden rounded-full bg-[var(--background)]">
      <div className="flex h-full">
        <div className="bg-[var(--accent-green)] transition-[width,opacity] duration-300" style={{ width: percentWidth(high, total) }} />
        <div className="bg-[var(--accent-yellow)] transition-[width,opacity] duration-300" style={{ width: percentWidth(medium, total) }} />
        <div className="bg-[var(--accent-red)] transition-[width,opacity] duration-300" style={{ width: percentWidth(low, total) }} />
      </div>
    </div>
  );
}

function CalibrationGauge({ value, label }: { value?: number; label: string }) {
  const degrees = Math.max(0, Math.min(360, (value ?? 0) * 360));

  return (
    <div className="flex items-center gap-4">
      <div
        className="grid h-24 w-24 shrink-0 place-items-center rounded-full"
        style={{ background: `conic-gradient(var(--accent) ${degrees}deg, var(--background) ${degrees}deg)` }}
      >
        <div className="grid h-16 w-16 place-items-center rounded-full bg-[var(--card)]">
          <span className="font-mono text-lg">{formatPercent(value)}</span>
        </div>
      </div>
      <div>
        <div className="section-label">{label}</div>
        <div className="divider-subtle mt-2 w-20" />
      </div>
    </div>
  );
}

function SkeletonPanel() {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-6">
      {[0, 1, 2, 3].map((item) => (
        <div key={item} className="h-44 card rounded-xl p-5">
          <div className="h-3 w-24 rounded bg-[var(--card-border)] animate-pulse" />
          <div className="mt-8 h-12 rounded bg-[var(--card-border)]/70 animate-pulse" />
          <div className="mt-5 h-3 w-2/3 rounded bg-[var(--card-border)]/60 animate-pulse" />
        </div>
      ))}
    </div>
  );
}

export default function MonitoringPage() {
  const { t } = useTranslation();
  const [dashboard, setDashboard] = useState<MonitoringDashboard | null>(null);
  const [events, setEvents] = useState<MonitoringEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<MonitoringDashboard>("/monitoring/dashboard");
      setDashboard(data);
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();

    const es = new EventSource("/api/monitoring/events/stream");
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as MonitoringEvent;
        setEvents((prev) => [data, ...prev].slice(0, 100));
      } catch (error) {
        console.error(error);
      }
    };
    eventSourceRef.current = es;

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [loadDashboard]);

  const watchRules = dashboard?.watch_rules || dashboard?.watchRules || [];
  const recentChanges = dashboard?.recent_changes || dashboard?.recentChanges || [];
  const revisionJobs = dashboard?.revision_jobs || dashboard?.revisionJobs || {};
  const predictionStats = dashboard?.predictions || {};
  const calibration = dashboard?.calibration || {};
  const highAccuracyRules = calibration.high_accuracy_rules ?? 0;
  const lowAccuracyRules = calibration.low_accuracy_rules ?? 0;
  const mediumAccuracyRules =
    calibration.medium_accuracy_rules ??
    Math.max((calibration.total_rules ?? 0) - highAccuracyRules - lowAccuracyRules, 0);
  const sourceTrust = calibration.source_trust_distribution || {};
  const highTrustSources = sourceTrust.high ?? 0;
  const mediumTrustSources = sourceTrust.medium ?? 0;
  const lowTrustSources = sourceTrust.low ?? 0;
  const healthyRules = watchRules.filter((rule) => rule.healthy ?? (rule.status || "").toUpperCase() === "HEALTHY").length;

  return (
    <div className="space-y-8">
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="grid gap-6 pb-6 lg:grid-cols-[1fr_280px]">
        <div>
          <p className="section-label mb-3">{t("monitoring.eventFeed")}</p>
          <h1 className="heading-display">{t("monitoring.title")}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--muted-foreground)]">{t("monitoring.subtitle")}</p>
        </div>
        <div className="liquid-glass self-end rounded-xl p-5">
          <div className="flex items-center justify-between">
            <span className="section-label">{t("monitoring.watchRules")}</span>
            <span className="font-mono text-xs text-[var(--accent-green)]">{healthyRules}/{watchRules.length}</span>
          </div>
          <div className="mt-4 flex gap-1">
            {watchRules.slice(0, 18).map((rule) => {
              const healthy = rule.healthy ?? (rule.status || "").toUpperCase() === "HEALTHY";
              return <HealthDot key={rule.id} healthy={healthy} failures={rule.failures} />;
            })}
          </div>
        </div>
      </div>

      <div className="divider-subtle" />

      {loading && <SkeletonPanel />}

      {!loading && error && (
        <div className="rounded-xl border border-[var(--accent-red)]/30 bg-[var(--accent-red-bg)] p-5 text-sm text-[var(--accent-red)]">
          <div className="font-medium">{t("common.failed")}</div>
          <div className="mt-1 text-xs text-[var(--muted-foreground)]">{error}</div>
        </div>
      )}

      {!loading && !error && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-6">
          {/* ── Watch Rules Panel ─────────────────────────────────────────── */}
          <BentoPanel title={t("monitoring.watchRules")} className="xl:col-span-4 xl:row-span-2">
            <div className="grid grid-cols-1 gap-x-8 lg:grid-cols-2">
              {watchRules.map((rule) => {
                const healthy = rule.healthy ?? (rule.status || "").toUpperCase() === "HEALTHY";
                return (
                  <div key={rule.id} className="grid grid-cols-[14px_1fr_auto] items-start gap-3 border-b border-[var(--card-border)] py-4 last:border-b-0">
                    <div className="pt-1.5">
                      <HealthDot healthy={healthy} failures={rule.failures} />
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{rule.name}</div>
                      <div className="mt-1 text-xs text-[var(--muted)]">
                        {t("monitoring.lastPoll")}: {formatDate(rule.last_poll)}
                      </div>
                    </div>
                    <div className="text-right text-xs text-[var(--muted)]">
                      <span className={healthy ? "badge badge-success" : "badge badge-error"}>
                        {healthy ? t("monitoring.healthy") : t("monitoring.unhealthy")}
                      </span>
                      <div className="mt-1 font-mono">{t("monitoring.failures")}: {rule.failures ?? 0}</div>
                    </div>
                  </div>
                );
              })}

              {watchRules.length === 0 && (
                <div className="empty-state col-span-full py-10">
                  <div className="empty-state-title">{t("monitoring.watchRules")}</div>
                </div>
              )}
            </div>
          </BentoPanel>

          {/* ── Revision Jobs Panel ───────────────────────────────────────── */}
          <BentoPanel title={t("monitoring.revisionJobs")} className="xl:col-span-2">
            <InlineMetric label={t("common.pending")} value={revisionJobs.pending ?? 0} tone="yellow" />
            <InlineMetric label={t("common.processing")} value={revisionJobs.processing ?? 0} />
            <InlineMetric label={t("common.completed")} value={revisionJobs.completed ?? 0} tone="green" />
            <InlineMetric label={t("common.failed")} value={revisionJobs.failed ?? 0} tone="red" />
          </BentoPanel>

          {/* ── Predictions Panel ─────────────────────────────────────────── */}
          <BentoPanel title={t("monitoring.predictions")} className="xl:col-span-2">
            <div className="grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--card-border)]">
              <div className="bg-[var(--background)] p-4">
                <div className="section-label">{t("monitoring.active")}</div>
                <div className="mt-2 font-mono text-xl text-[var(--accent-green)]">{predictionStats.active ?? 0}</div>
              </div>
              <div className="bg-[var(--background)] p-4">
                <div className="section-label">{t("monitoring.superseded")}</div>
                <div className="mt-2 font-mono text-xl text-[var(--accent-yellow)]">{predictionStats.superseded ?? 0}</div>
              </div>
              <div className="bg-[var(--background)] p-4">
                <div className="section-label">{t("monitoring.verified")}</div>
                <div className="mt-2 font-mono text-xl text-[var(--accent)]">{predictionStats.verified ?? 0}</div>
              </div>
            </div>
          </BentoPanel>

          {/* ── Calibration Panel ─────────────────────────────────────────── */}
          <BentoPanel title={t("monitoring.calibration")} className="xl:col-span-3">
            <div className="grid gap-6 lg:grid-cols-[160px_1fr]">
              <CalibrationGauge value={calibration.avg_accuracy} label={t("monitoring.avgCalibrationScore")} />
              <div className="space-y-6">
                <div>
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <div className="text-sm font-medium">{t("monitoring.ruleAccuracyDistribution")}</div>
                    <div className="font-mono text-xs text-[var(--muted)]">{calibration.total_rules ?? highAccuracyRules + mediumAccuracyRules + lowAccuracyRules}</div>
                  </div>
                  <DistributionBar high={highAccuracyRules} medium={mediumAccuracyRules} low={lowAccuracyRules} />
                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                    <div className="text-[var(--accent-green)]">{t("monitoring.high")}: <span className="font-mono">{highAccuracyRules}</span></div>
                    <div className="text-[var(--accent-yellow)]">{t("monitoring.medium")}: <span className="font-mono">{mediumAccuracyRules}</span></div>
                    <div className="text-[var(--accent-red)]">{t("monitoring.low")}: <span className="font-mono">{lowAccuracyRules}</span></div>
                  </div>
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <div className="text-sm font-medium">{t("monitoring.sourceTrustDistribution")}</div>
                    <div className="font-mono text-xs text-[var(--muted)]">{calibration.total_sources ?? highTrustSources + mediumTrustSources + lowTrustSources}</div>
                  </div>
                  <DistributionBar high={highTrustSources} medium={mediumTrustSources} low={lowTrustSources} />
                  <div className="mt-3 flex items-center justify-between gap-3 text-xs text-[var(--muted)]">
                    <span>{t("monitoring.avgTrust")}: <span className="font-mono">{formatPercent(calibration.avg_trust)}</span></span>
                    <span className="font-mono">{highTrustSources}/{mediumTrustSources}/{lowTrustSources}</span>
                  </div>
                </div>
              </div>
            </div>
          </BentoPanel>

          {/* ── Recent Changes Panel ──────────────────────────────────────── */}
          <BentoPanel title={t("monitoring.recentChanges")} className="xl:col-span-3">
            <div className="max-h-[320px] overflow-y-auto border-y border-[var(--card-border)]">
              {recentChanges.map((change) => (
                <div key={change.id} className="grid grid-cols-[92px_1fr_auto] gap-4 border-b border-[var(--card-border)] py-4 last:border-b-0">
                  <div className="section-label truncate">{change.source_type}</div>
                  <div className="min-w-0">
                    <p className="line-clamp-2 text-sm leading-5">{change.diff_summary || "-"}</p>
                    <div className="mt-1 text-xs text-[var(--muted)]">{formatDate(change.created_at)}</div>
                  </div>
                  <span className="badge badge-premium font-mono">{change.significance ?? "-"}</span>
                </div>
              ))}

              {recentChanges.length === 0 && (
                <div className="empty-state py-10">
                  <div className="empty-state-title">{t("monitoring.recentChanges")}</div>
                </div>
              )}
            </div>
          </BentoPanel>

          {/* ── Event Feed Panel ──────────────────────────────────────────── */}
          <aside className="xl:col-span-6 card rounded-xl p-5">
            <div className="mb-5 flex items-center justify-between gap-4">
              <h2 className="heading-section flex items-center gap-2">
                <span className="status-dot online" />
                {t("monitoring.eventFeed")}
              </h2>
              <span className="font-mono text-xs text-[var(--muted)]">{events.length}</span>
            </div>
            <div className="max-h-[360px] overflow-y-auto border-y border-[var(--card-border)]">
              {events.map((event, index) => (
                <div
                  key={event.id || `${event.event || event.topic || "event"}-${index}`}
                  className="animate-slideIn border-b border-[var(--card-border)] py-4 last:border-b-0"
                >
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <EventLabel event={event} />
                    <span className="text-xs text-[var(--muted)]">{formatDate(event.created_at || event.timestamp)}</span>
                  </div>
                  {event.payload && (
                    <pre className="max-h-32 overflow-auto rounded-lg bg-[var(--background)] p-3 text-xs text-[var(--muted-foreground)] whitespace-pre-wrap break-words">
                      {JSON.stringify(event.payload, null, 2)}
                    </pre>
                  )}
                </div>
              ))}

              {events.length === 0 && (
                <div className="empty-state py-10">
                  <div className="empty-state-title">{t("monitoring.noEvents")}</div>
                </div>
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
