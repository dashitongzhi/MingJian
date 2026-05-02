"use client";

import { useState, useEffect, useRef, useCallback } from "react";
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

function StatCard({ label, value, tone = "accent" }: { label: string; value: number; tone?: "accent" | "green" | "yellow" | "red" }) {
  const toneClass =
    tone === "green"
      ? "text-[var(--accent-green)]"
      : tone === "yellow"
        ? "text-[var(--accent-yellow)]"
        : tone === "red"
          ? "text-[var(--accent-red)]"
          : "text-[var(--accent)]";

  return (
    <div className="rounded-lg border border-[var(--card-border)] p-4">
      <div className="text-xs text-[var(--muted)] uppercase">{label}</div>
      <div className={`text-2xl font-semibold font-mono mt-2 ${toneClass}`}>{value}</div>
    </div>
  );
}

function EventLabel({ event }: { event: MonitoringEvent }) {
  return <span className="text-xs font-mono text-[var(--accent)]">{event.event || event.topic || event.type || "event"}</span>;
}

function formatPercent(value?: number) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function percentWidth(value: number, total: number) {
  if (total <= 0) return "0%";
  return `${Math.max(0, Math.min(100, (value / total) * 100))}%`;
}

function DistributionBar({
  high,
  medium,
  low,
}: {
  high: number;
  medium: number;
  low: number;
}) {
  const total = high + medium + low;

  return (
    <div className="h-2 rounded-full bg-[var(--bg)] overflow-hidden flex">
      <div className="bg-[var(--accent-green)]" style={{ width: percentWidth(high, total) }} />
      <div className="bg-[var(--accent-yellow)]" style={{ width: percentWidth(medium, total) }} />
      <div className="bg-[var(--accent-red)]" style={{ width: percentWidth(low, total) }} />
    </div>
  );
}

export default function MonitoringPage() {
  const { t } = useTranslation();
  const [dashboard, setDashboard] = useState<MonitoringDashboard | null>(null);
  const [events, setEvents] = useState<MonitoringEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const eventSourceRef = useRef<EventSource | null>(null);

  const loadDashboard = useCallback(async () => {
    try {
      const data = await apiFetch<MonitoringDashboard>("/monitoring/dashboard");
      setDashboard(data);
    } catch (e) {
      console.error(e);
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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t("monitoring.title")}</h1>
        <p className="text-[var(--muted)] mt-1">{t("monitoring.subtitle")}</p>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-8 text-sm text-[var(--muted)]">
          <div className="spinner mr-2" />
          {t("common.loading")}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6">
        <div className="space-y-6">
          <section className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
            <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
              </svg>
              {t("monitoring.watchRules")}
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {watchRules.map((rule) => {
                const healthy = rule.healthy ?? (rule.status || "").toUpperCase() === "HEALTHY";
                return (
                  <div key={rule.id} className="rounded-lg border border-[var(--card-border)] p-4 hover:border-[var(--muted)] transition-colors">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium truncate">{rule.name}</div>
                        <div className="text-xs text-[var(--muted)] mt-2">
                          {t("monitoring.lastPoll")}: {formatDate(rule.last_poll)}
                        </div>
                      </div>
                      <span className={`badge ${healthy ? "badge-success" : "badge-error"}`}>
                        {healthy ? t("monitoring.healthy") : t("monitoring.unhealthy")}
                      </span>
                    </div>
                    <div className="text-xs text-[var(--muted)] mt-3">
                      {t("monitoring.failures")}: <span className="font-mono">{rule.failures ?? 0}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
            <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
              </svg>
              {t("monitoring.recentChanges")}
            </h2>
            <div className="space-y-2 max-h-[360px] overflow-y-auto">
              {recentChanges.map((change) => (
                <div key={change.id} className="rounded-lg border border-[var(--card-border)] p-4 hover:border-[var(--muted)] transition-colors">
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <span className="text-xs uppercase text-[var(--muted)]">{change.source_type}</span>
                    <span className="badge badge-info">{change.significance ?? "-"}</span>
                  </div>
                  <p className="text-sm">{change.diff_summary || "-"}</p>
                  <div className="text-xs text-[var(--muted)] mt-2">{formatDate(change.created_at)}</div>
                </div>
              ))}
            </div>
          </section>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <section className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
              <h2 className="text-sm font-semibold mb-4">{t("monitoring.revisionJobs")}</h2>
              <div className="grid grid-cols-2 gap-3">
                <StatCard label={t("common.pending")} value={revisionJobs.pending ?? 0} tone="yellow" />
                <StatCard label={t("common.processing")} value={revisionJobs.processing ?? 0} />
                <StatCard label={t("common.completed")} value={revisionJobs.completed ?? 0} tone="green" />
                <StatCard label={t("common.failed")} value={revisionJobs.failed ?? 0} tone="red" />
              </div>
            </section>

            <section className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
              <h2 className="text-sm font-semibold mb-4">{t("monitoring.predictions")}</h2>
              <div className="grid grid-cols-3 gap-3">
                <StatCard label={t("monitoring.active")} value={predictionStats.active ?? 0} tone="green" />
                <StatCard label={t("monitoring.superseded")} value={predictionStats.superseded ?? 0} tone="yellow" />
                <StatCard label={t("monitoring.verified")} value={predictionStats.verified ?? 0} />
              </div>
            </section>
          </div>

          <section className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
            <div className="flex items-start justify-between gap-4 mb-5">
              <h2 className="text-sm font-semibold">{t("monitoring.calibration")}</h2>
              <div className="text-right">
                <div className="text-xs text-[var(--muted)] uppercase">{t("monitoring.avgCalibrationScore")}</div>
                <div className="text-2xl font-semibold font-mono text-[var(--accent)] mt-1">
                  {formatPercent(calibration.avg_accuracy)}
                </div>
              </div>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium">{t("monitoring.ruleAccuracyDistribution")}</div>
                  <div className="text-xs text-[var(--muted)] font-mono">{calibration.total_rules ?? highAccuracyRules + mediumAccuracyRules + lowAccuracyRules}</div>
                </div>
                <DistributionBar high={highAccuracyRules} medium={mediumAccuracyRules} low={lowAccuracyRules} />
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="text-[var(--accent-green)]">
                    {t("monitoring.high")}: <span className="font-mono">{highAccuracyRules}</span>
                  </div>
                  <div className="text-[var(--accent-yellow)]">
                    {t("monitoring.medium")}: <span className="font-mono">{mediumAccuracyRules}</span>
                  </div>
                  <div className="text-[var(--accent-red)]">
                    {t("monitoring.low")}: <span className="font-mono">{lowAccuracyRules}</span>
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium">{t("monitoring.sourceTrustDistribution")}</div>
                  <div className="text-xs text-[var(--muted)] font-mono">{calibration.total_sources ?? highTrustSources + mediumTrustSources + lowTrustSources}</div>
                </div>
                <DistributionBar high={highTrustSources} medium={mediumTrustSources} low={lowTrustSources} />
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="text-[var(--accent-green)]">
                    {t("monitoring.high")}: <span className="font-mono">{highTrustSources}</span>
                  </div>
                  <div className="text-[var(--accent-yellow)]">
                    {t("monitoring.medium")}: <span className="font-mono">{mediumTrustSources}</span>
                  </div>
                  <div className="text-[var(--accent-red)]">
                    {t("monitoring.low")}: <span className="font-mono">{lowTrustSources}</span>
                  </div>
                </div>
                <div className="text-xs text-[var(--muted)]">
                  {t("monitoring.avgTrust")}: <span className="font-mono">{formatPercent(calibration.avg_trust)}</span>
                </div>
              </div>
            </div>
          </section>
        </div>

        <aside className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
            <span className="status-dot online" />
            {t("monitoring.eventFeed")}
          </h2>
          <div className="space-y-2 max-h-[calc(100vh-220px)] overflow-y-auto">
            {events.map((event, index) => (
              <div key={event.id || `${event.event || event.topic || "event"}-${index}`} className="rounded-lg border border-[var(--card-border)] p-3">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <EventLabel event={event} />
                  <span className="text-xs text-[var(--muted)]">{formatDate(event.created_at || event.timestamp)}</span>
                </div>
                {event.payload && <pre className="text-xs text-[var(--muted)] whitespace-pre-wrap break-words">{JSON.stringify(event.payload, null, 2)}</pre>}
              </div>
            ))}

            {events.length === 0 && (
              <div className="empty-state py-10">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                  <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                </svg>
                <div className="empty-state-title">{t("monitoring.noEvents")}</div>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
