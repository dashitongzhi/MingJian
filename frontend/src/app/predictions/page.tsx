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

function StatusBadge({ status }: { status?: string | null }) {
  const normalized = (status || "UNKNOWN").toUpperCase();
  const className =
    normalized === "ACTIVE" || normalized === "CURRENT"
      ? "badge-success"
      : normalized === "SUPERSEDED"
        ? "badge-warning"
        : normalized === "VERIFIED"
          ? "badge-info"
          : "badge-error";
  return <span className={`badge ${className}`}>{normalized}</span>;
}

function ProbabilityDelta({ current, previous }: { current?: number | null; previous?: number | null }) {
  const delta = current != null && previous != null ? current - previous : null;
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-sm">{formatPercent(current)}</span>
      {delta != null && (
        <span className={`text-xs font-mono ${delta >= 0 ? "text-[var(--accent-green)]" : "text-[var(--accent-red)]"}`}>
          {delta >= 0 ? "+" : ""}
          {(delta * 100).toFixed(0)}pt
        </span>
      )}
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
  const [selectedSeries, setSelectedSeries] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<PredictionTimelineItem[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);

  const loadPredictions = useCallback(async () => {
    try {
      const data = await apiFetch<PredictionSeries[]>("/predictions");
      setPredictions(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTimeline = useCallback(async (seriesId: string) => {
    setTimelineLoading(true);
    try {
      const data = await apiFetch<PredictionTimelineResponse>(`/predictions/${seriesId}/timeline`);
      setTimeline(normalizeTimeline(data));
      setSelectedSeries(seriesId);
    } catch (e) {
      console.error(e);
      setTimeline([]);
      setSelectedSeries(seriesId);
    } finally {
      setTimelineLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPredictions();
  }, [loadPredictions]);

  const selectedPrediction = predictions.find((item) => item.id === selectedSeries);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t("predictions.title")}</h1>
        <p className="text-[var(--muted)] mt-1">{t("predictions.subtitle")}</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[420px_1fr] gap-6">
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 3v18h18" />
              <path d="m19 9-5 5-4-4-3 3" />
            </svg>
            {t("predictions.series")} ({predictions.length})
          </h2>

          <div className="space-y-2 max-h-[calc(100vh-260px)] overflow-y-auto">
            {predictions.map((prediction) => {
              const subject =
                prediction.subject ||
                prediction.subject_name ||
                prediction.subject_id ||
                prediction.subject_type ||
                prediction.id.slice(0, 8);
              const domain = prediction.domain || prediction.domain_id || "-";
              const currentVersion = prediction.current_version || prediction.current_version_id?.slice(0, 8) || "-";

              return (
                <button
                  key={prediction.id}
                  onClick={() => loadTimeline(prediction.id)}
                  className={`w-full text-left p-4 rounded-lg border transition-all ${
                    selectedSeries === prediction.id
                      ? "border-[var(--accent)] bg-[var(--accent)]/10"
                      : "border-[var(--card-border)] hover:border-[var(--muted)] hover:bg-[var(--card-hover)]"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">{subject}</div>
                      <div className="text-xs text-[var(--muted)] mt-1">{domain}</div>
                    </div>
                    <StatusBadge status={prediction.status} />
                  </div>
                  <div className="flex items-center justify-between text-xs text-[var(--muted)]">
                    <span className="font-mono">v{currentVersion}</span>
                    <span>{formatDate(prediction.created_at)}</span>
                  </div>
                </button>
              );
            })}

            {loading && (
              <div className="flex items-center justify-center py-10 text-sm text-[var(--muted)]">
                <div className="spinner mr-2" />
                {t("common.loading")}
              </div>
            )}

            {!loading && predictions.length === 0 && (
              <div className="empty-state py-10">
                <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                  <path d="M3 3v18h18" />
                  <path d="m19 9-5 5-4-4-3 3" />
                </svg>
                <div className="empty-state-title">{t("predictions.noPredictions")}</div>
              </div>
            )}
          </div>
        </div>

        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
          <div className="flex items-start justify-between gap-4 mb-5">
            <div>
              <h2 className="text-sm font-semibold flex items-center gap-2">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 8v4l3 3" />
                  <circle cx="12" cy="12" r="10" />
                </svg>
                {t("predictions.versionHistory")}
              </h2>
              {selectedPrediction && (
                <p className="text-xs text-[var(--muted)] mt-1">
                  {selectedPrediction.domain || selectedPrediction.domain_id || "-"} / {selectedPrediction.status}
                </p>
              )}
            </div>
            {timeline.length > 0 && <span className="badge badge-info">{timeline.length} {t("predictions.versions")}</span>}
          </div>

          {timelineLoading && (
            <div className="flex items-center justify-center py-16 text-sm text-[var(--muted)]">
              <div className="spinner mr-2" />
              {t("common.loading")}
            </div>
          )}

          {!timelineLoading && selectedSeries && timeline.length > 0 && (
            <div className="relative">
              <div className="absolute left-[11px] top-2 bottom-2 w-px bg-[var(--card-border)]" />
              <div className="space-y-4">
                {timeline.map((version, index) => {
                  const previous = timeline[index - 1];
                  const evidence = version.trigger_evidence || version.evidence_title || version.summary_delta;

                  return (
                    <div key={version.id} className="relative pl-9">
                      <div className="absolute left-0 top-1 w-6 h-6 rounded-full bg-[var(--accent)] text-white text-xs font-mono flex items-center justify-center">
                        {version.version_number}
                      </div>
                      <div className="rounded-lg border border-[var(--card-border)] p-4 hover:border-[var(--muted)] transition-colors">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-sm font-semibold">v{version.version_number}</span>
                              <StatusBadge status={version.status} />
                            </div>
                            <div className="text-xs text-[var(--muted)]">{formatDate(version.created_at)}</div>
                          </div>
                          <div className="text-right">
                            <div className="text-xs text-[var(--muted)] mb-1">{t("predictions.probability")}</div>
                            <ProbabilityDelta current={version.probability} previous={previous?.probability} />
                          </div>
                        </div>

                        {version.prediction_text && <p className="text-sm mt-3 text-[var(--foreground)]">{version.prediction_text}</p>}

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
                          <div>
                            <div className="text-xs text-[var(--muted)]">{t("predictions.confidence")}</div>
                            <div className="text-sm font-mono mt-1">{formatPercent(version.confidence)}</div>
                          </div>
                          <div>
                            <div className="text-xs text-[var(--muted)]">{t("predictions.triggerType")}</div>
                            <div className="text-sm mt-1">{version.trigger_type || "-"}</div>
                          </div>
                          <div>
                            <div className="text-xs text-[var(--muted)]">{t("predictions.status")}</div>
                            <div className="text-sm mt-1">{version.status || "-"}</div>
                          </div>
                        </div>

                        {evidence && (
                          <div className="mt-4 p-3 rounded-lg bg-[var(--background)] border border-[var(--card-border)]">
                            <div className="text-xs text-[var(--muted)] mb-1">{t("predictions.timeline")}</div>
                            <div className="text-sm">{evidence}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {!timelineLoading && !selectedSeries && (
            <div className="empty-state py-16">
              <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                <path d="M12 8v4l3 3" />
                <circle cx="12" cy="12" r="10" />
              </svg>
              <div className="empty-state-title">{t("predictions.timeline")}</div>
              <div className="empty-state-description">{t("predictions.subtitle")}</div>
            </div>
          )}

          {!timelineLoading && selectedSeries && timeline.length === 0 && (
            <div className="empty-state py-16">
              <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                <path d="M12 8v4l3 3" />
                <circle cx="12" cy="12" r="10" />
              </svg>
              <div className="empty-state-title">{t("predictions.noPredictions")}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
