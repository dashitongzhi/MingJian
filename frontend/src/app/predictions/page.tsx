"use client";

import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "@/contexts/LanguageContext";
import { apiFetch } from "@/lib/api";

interface PredictionSeries {
  id: string;
  subject?: string | null;
  subject_name?: string | null;
  subject_type?: string | null;
  subject_id?: string | null;
  domain?: string | null;
  domain_id?: string | null;
  status: string;
  current_version?: number | string | null;
  current_version_id?: string | null;
  created_at: string;
  updated_at?: string | null;
}

interface PredictionTimelineItem {
  id: string;
  version_number: number;
  probability?: number | null;
  confidence?: number | null;
  trigger_type?: string | null;
  trigger_evidence?: string | null;
  evidence_title?: string | null;
  summary_delta?: string | null;
  prediction_text?: string | null;
  status?: string | null;
  created_at: string;
}

type PredictionTimelineResponse =
  | PredictionTimelineItem[]
  | {
      timeline?: PredictionTimelineItem[];
      versions?: PredictionTimelineItem[];
    };

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

function formatPercent(value?: number | null) {
  return value == null ? "-" : `${(value * 100).toFixed(0)}%`;
}

function clampPercent(value?: number | null) {
  if (value == null) return 0;
  return Math.max(0, Math.min(100, value * 100));
}

function StatusBadge({ status }: { status?: string | null }) {
  const normalized = (status || "UNKNOWN").toUpperCase();
  const className =
    normalized === "ACTIVE" || normalized === "CURRENT"
      ? "border-[var(--accent-green)]/30 bg-[var(--accent-green-bg)] text-[var(--accent-green)]"
      : normalized === "SUPERSEDED"
        ? "border-[var(--accent-yellow)]/30 bg-[var(--accent-yellow-bg)] text-[var(--accent-yellow)]"
        : normalized === "VERIFIED"
          ? "border-[var(--accent)]/30 bg-[var(--accent)]/10 text-[var(--accent)]"
          : "border-[var(--accent-red)]/30 bg-[var(--accent-red-bg)] text-[var(--accent-red)]";

  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] leading-4 ${className}`}>
      {normalized}
    </span>
  );
}

function ProbabilityDelta({ current, previous }: { current?: number | null; previous?: number | null }) {
  const delta = current != null && previous != null ? current - previous : null;
  const width = clampPercent(current);

  return (
    <div className="min-w-[150px]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="font-mono text-lg text-[var(--foreground)]">{formatPercent(current)}</span>
        {delta != null && (
          <span className={`font-mono text-xs ${delta >= 0 ? "text-[var(--accent-green)]" : "text-[var(--accent-red)]"}`}>
            {delta >= 0 ? "+" : ""}
            {(delta * 100).toFixed(0)}pt
          </span>
        )}
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[var(--background)]">
        <div
          className="h-full rounded-full bg-[var(--accent)] transition-[width,opacity] duration-300"
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function ProbabilitySparkline({ values }: { values: Array<number | null | undefined> }) {
  const normalized = values.map((value) => clampPercent(value));
  if (normalized.length === 0) {
    return <div className="h-8 rounded border border-dashed border-[var(--card-border)]" />;
  }

  return (
    <div className="flex h-8 items-end gap-1">
      {normalized.map((value, index) => (
        <span
          key={`${value}-${index}`}
          className="w-1.5 rounded-t-sm bg-[var(--accent)]/75 transition-[height,opacity] duration-300"
          style={{ height: `${Math.max(10, value)}%`, opacity: 0.35 + (index + 1) / (normalized.length * 1.8) }}
        />
      ))}
    </div>
  );
}

function DiffBlock({
  before,
  after,
  evidence,
}: {
  before?: string | null;
  after?: string | null;
  evidence?: string | null;
}) {
  if (!before && !after && !evidence) return null;

  return (
    <div className="mt-5 overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--background)] font-mono text-xs">
      {before && (
        <div className="flex gap-3 border-b border-[var(--card-border)] px-3 py-2 text-[var(--accent-red)]/90">
          <span className="select-none text-[var(--muted)]">-</span>
          <span className="line-clamp-3">{before}</span>
        </div>
      )}
      {after && (
        <div className="flex gap-3 border-b border-[var(--card-border)] px-3 py-2 text-[var(--accent-green)]/90 last:border-b-0">
          <span className="select-none text-[var(--muted)]">+</span>
          <span className="line-clamp-4">{after}</span>
        </div>
      )}
      {evidence && (
        <div className="flex gap-3 px-3 py-2 text-[var(--muted-foreground)]">
          <span className="select-none text-[var(--muted)]">@</span>
          <span className="line-clamp-4">{evidence}</span>
        </div>
      )}
    </div>
  );
}

function TimelineSkeleton() {
  return (
    <div className="space-y-5">
      {[0, 1, 2].map((item) => (
        <div key={item} className="grid grid-cols-[72px_1fr] gap-5">
          <div className="h-4 rounded bg-[var(--card-border)]/60 animate-pulse" />
          <div className="space-y-3 border-l border-[var(--card-border)] pl-6">
            <div className="h-4 w-1/3 rounded bg-[var(--card-border)]/70 animate-pulse" />
            <div className="h-20 rounded-lg bg-[var(--card)] animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

function normalizeTimeline(data: PredictionTimelineResponse): PredictionTimelineItem[] {
  if (Array.isArray(data)) return data;
  return data.timeline || data.versions || [];
}

export default function PredictionsPage() {
  const { t } = useTranslation();
  const [predictions, setPredictions] = useState<PredictionSeries[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSeries, setSelectedSeries] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<PredictionTimelineItem[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const loadPredictions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<PredictionSeries[]>("/predictions");
      setPredictions(data);
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTimeline = useCallback(async (seriesId: string) => {
    setTimelineLoading(true);
    setTimelineError(null);
    try {
      const data = await apiFetch<PredictionTimelineResponse>(`/predictions/${seriesId}/timeline`);
      setTimeline(normalizeTimeline(data));
      setSelectedSeries(seriesId);
    } catch (e) {
      console.error(e);
      setTimeline([]);
      setSelectedSeries(seriesId);
      setTimelineError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setTimelineLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPredictions();
  }, [loadPredictions]);

  const selectedPrediction = predictions.find((item) => item.id === selectedSeries);

  return (
    <div className="space-y-8">
      <div className="grid gap-6 border-b border-[var(--card-border)] pb-6 lg:grid-cols-[1fr_320px]">
        <div>
          <p className="mb-3 text-xs uppercase tracking-[0.18em] text-[var(--accent)]">{t("predictions.series")}</p>
          <h1 className="text-3xl font-semibold tracking-normal">{t("predictions.title")}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--muted-foreground)]">{t("predictions.subtitle")}</p>
        </div>
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--card-border)]">
          <div className="bg-[var(--card)] p-4">
            <div className="text-xs text-[var(--muted)]">{t("predictions.series")}</div>
            <div className="mt-2 font-mono text-2xl">{predictions.length}</div>
          </div>
          <div className="bg-[var(--card)] p-4">
            <div className="text-xs text-[var(--muted)]">{t("predictions.versions")}</div>
            <div className="mt-2 font-mono text-2xl">{timeline.length}</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-[390px_1fr]">
        <aside className="min-w-0">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-medium">{t("predictions.series")}</h2>
            <span className="font-mono text-xs text-[var(--muted)]">{predictions.length}</span>
          </div>

          <div className="max-h-[calc(100vh-250px)] overflow-y-auto border-y border-[var(--card-border)]">
            {predictions.map((prediction) => {
              const subject =
                prediction.subject ||
                prediction.subject_name ||
                prediction.subject_id ||
                prediction.subject_type ||
                prediction.id.slice(0, 8);
              const domain = prediction.domain || prediction.domain_id || "-";
              const currentVersion = prediction.current_version || prediction.current_version_id?.slice(0, 8) || "-";
              const selected = selectedSeries === prediction.id;

              return (
                <button
                  key={prediction.id}
                  onClick={() => loadTimeline(prediction.id)}
                  className={`group grid w-full grid-cols-[56px_1fr] gap-4 border-b border-[var(--card-border)] px-0 py-4 text-left transition-[background-color,opacity] duration-200 last:border-b-0 ${
                    selected ? "bg-[var(--accent)]/8" : "hover:bg-[var(--card)]"
                  }`}
                >
                  <div className="pl-3 font-mono text-xs text-[var(--muted)]">
                    <div className={selected ? "text-[var(--accent)]" : ""}>v{currentVersion}</div>
                    <div className="mt-2 h-px w-8 bg-[var(--card-border)] group-hover:bg-[var(--accent)]/50" />
                  </div>
                  <div className="min-w-0 pr-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">{subject}</div>
                        <div className="mt-1 truncate text-xs text-[var(--muted)]">{domain}</div>
                      </div>
                      <StatusBadge status={prediction.status} />
                    </div>
                    <div className="mt-4 flex items-center justify-between text-xs text-[var(--muted)]">
                      <span>{formatDate(prediction.created_at)}</span>
                      <span>{formatDate(prediction.updated_at)}</span>
                    </div>
                  </div>
                </button>
              );
            })}

            {loading && (
              <div className="space-y-4 py-4">
                {[0, 1, 2, 3].map((item) => (
                  <div key={item} className="grid grid-cols-[56px_1fr] gap-4 px-3">
                    <div className="h-3 rounded bg-[var(--card-border)] animate-pulse" />
                    <div className="space-y-3">
                      <div className="h-4 w-3/4 rounded bg-[var(--card-border)] animate-pulse" />
                      <div className="h-3 w-1/2 rounded bg-[var(--card-border)]/70 animate-pulse" />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!loading && error && (
              <div className="px-4 py-10 text-sm text-[var(--accent-red)]">
                <div className="font-medium">{t("common.failed")}</div>
                <div className="mt-1 text-xs text-[var(--muted)]">{error}</div>
              </div>
            )}

            {!loading && !error && predictions.length === 0 && (
              <div className="empty-state py-12">
                <div className="empty-state-title">{t("predictions.noPredictions")}</div>
              </div>
            )}
          </div>
        </aside>

        <main className="min-w-0 rounded-xl border border-[var(--card-border)] bg-[var(--card)]/55 p-5 md:p-6">
          <div className="mb-8 flex flex-col justify-between gap-4 border-b border-[var(--card-border)] pb-5 md:flex-row md:items-start">
            <div>
              <h2 className="text-sm font-medium">{t("predictions.versionHistory")}</h2>
              {selectedPrediction && (
                <p className="mt-2 text-xs text-[var(--muted)]">
                  {selectedPrediction.domain || selectedPrediction.domain_id || "-"} / {selectedPrediction.status}
                </p>
              )}
            </div>
            {timeline.length > 0 && (
              <div className="flex min-w-[180px] items-end justify-between gap-4">
                <ProbabilitySparkline values={timeline.map((item) => item.probability)} />
                <span className="font-mono text-xs text-[var(--muted)]">
                  {timeline.length} {t("predictions.versions")}
                </span>
              </div>
            )}
          </div>

          {timelineLoading && <TimelineSkeleton />}

          {!timelineLoading && timelineError && (
            <div className="rounded-lg border border-[var(--accent-red)]/30 bg-[var(--accent-red-bg)] p-4 text-sm text-[var(--accent-red)]">
              <div className="font-medium">{t("common.failed")}</div>
              <div className="mt-1 text-xs text-[var(--muted-foreground)]">{timelineError}</div>
            </div>
          )}

          {!timelineLoading && !timelineError && selectedSeries && timeline.length > 0 && (
            <div className="space-y-8">
              {timeline.map((version, index) => {
                const previous = timeline[index - 1];
                const evidence = version.trigger_evidence || version.evidence_title || version.summary_delta;

                return (
                  <article key={version.id} className="grid grid-cols-[72px_1fr] gap-5 md:grid-cols-[92px_1fr]">
                    <div className="pt-1 text-right">
                      <div className="font-mono text-xs text-[var(--accent)]">v{version.version_number}</div>
                      <div className="mt-2 text-[11px] leading-4 text-[var(--muted)]">{formatDate(version.created_at)}</div>
                    </div>
                    <div className="relative border-l border-[var(--card-border)] pl-6">
                      <span className="absolute -left-[5px] top-2 h-2.5 w-2.5 rounded-full border border-[var(--accent)] bg-[var(--card)]" />
                      <div className="rounded-lg bg-[var(--background)]/70 p-4 ring-1 ring-[var(--card-border)] transition-[transform,opacity,background-color] duration-200 hover:-translate-y-0.5 hover:bg-[var(--background)]">
                        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusBadge status={version.status} />
                              <span className="text-xs text-[var(--muted)]">{version.trigger_type || "-"}</span>
                            </div>
                            {version.prediction_text && (
                              <p className="mt-4 max-w-3xl text-sm leading-6 text-[var(--foreground)]">{version.prediction_text}</p>
                            )}
                          </div>
                          <ProbabilityDelta current={version.probability} previous={previous?.probability} />
                        </div>

                        <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--card-border)] md:grid-cols-3">
                          <div className="bg-[var(--card)] p-3">
                            <div className="text-[11px] text-[var(--muted)]">{t("predictions.confidence")}</div>
                            <div className="mt-1 font-mono text-sm">{formatPercent(version.confidence)}</div>
                          </div>
                          <div className="bg-[var(--card)] p-3">
                            <div className="text-[11px] text-[var(--muted)]">{t("predictions.triggerType")}</div>
                            <div className="mt-1 truncate text-sm">{version.trigger_type || "-"}</div>
                          </div>
                          <div className="bg-[var(--card)] p-3">
                            <div className="text-[11px] text-[var(--muted)]">{t("predictions.status")}</div>
                            <div className="mt-1 truncate text-sm">{version.status || "-"}</div>
                          </div>
                        </div>

                        <DiffBlock before={previous?.prediction_text} after={version.prediction_text} evidence={evidence} />
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {!timelineLoading && !timelineError && !selectedSeries && (
            <div className="empty-state py-16">
              <div className="empty-state-title">{t("predictions.timeline")}</div>
              <div className="empty-state-description">{t("predictions.subtitle")}</div>
            </div>
          )}

          {!timelineLoading && !timelineError && selectedSeries && timeline.length === 0 && (
            <div className="empty-state py-16">
              <div className="empty-state-title">{t("predictions.noPredictions")}</div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
