"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Clock3,
  FileSearch,
  Layers3,
  PauseCircle,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import {
  createUserDecision,
  fetchSessions,
  fetchWorkbenchData,
  type StrategicSession,
  type UserDecisionValue,
  type WorkbenchAlternativeScenario,
  type WorkbenchPredictionVersion,
  type WorkbenchRecommendation,
} from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";
import { toast } from "@/lib/toast";

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

function percentValue(value?: number | null) {
  if (value == null || Number.isNaN(value)) return null;
  return Math.max(0, Math.min(100, value > 1 ? value : value * 100));
}

function formatPercent(value?: number | null) {
  const pct = percentValue(value);
  return pct == null ? "-" : `${pct.toFixed(0)}%`;
}

function confidenceTone(value?: number | null) {
  const pct = percentValue(value) ?? 0;
  if (pct >= 70) return "badge-success";
  if (pct >= 40) return "badge-warning";
  return "badge-error";
}

function SkeletonBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5 animate-pulse">
          <div className="h-3 w-28 rounded bg-[var(--card-border)]/70" />
          <div className="mt-4 h-3 w-full rounded bg-[var(--card-border)]/60" />
          <div className="mt-3 h-3 w-2/3 rounded bg-[var(--card-border)]/50" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex min-h-[360px] items-center justify-center rounded-lg border border-dashed border-[var(--card-border)] text-center">
      <div className="max-w-sm px-6">
        <div className="mx-auto mb-4 h-px w-16 bg-[var(--accent)]" />
        <div className="heading-section">{title}</div>
        <div className="mt-2 text-sm leading-6 text-[var(--muted)]">{description}</div>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  helper,
}: {
  label: string;
  value: string;
  helper?: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
      <div className="section-label !text-[var(--muted)]">{label}</div>
      <div className="mt-3 font-mono text-3xl text-[var(--foreground)]">{value}</div>
      {helper && <div className="mt-2 truncate text-xs text-[var(--muted)]">{helper}</div>}
    </div>
  );
}

function ConfidenceBar({ value }: { value?: number | null }) {
  const pct = percentValue(value) ?? 0;
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-4">
        <span className="section-label !text-[var(--muted)]">CONF</span>
        <span className="font-mono text-xs text-[var(--muted)]">{formatPercent(value)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[var(--card-border)]">
        <div className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function NumberedList({
  title,
  items,
  empty,
  tone = "text-[var(--accent)]",
}: {
  title: string;
  items: string[];
  empty: string;
  tone?: string;
}) {
  return (
    <section className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 className="heading-section">{title}</h2>
        <span className="badge">{items.length}</span>
      </div>
      {items.length > 0 ? (
        <div className="divide-y divide-[var(--card-border)]/70">
          {items.map((item, index) => (
            <div key={`${item}-${index}`} className="grid grid-cols-[32px_1fr] gap-3 py-3 text-sm leading-6">
              <span className={`font-mono text-xs ${tone}`}>{String(index + 1).padStart(2, "0")}</span>
              <span className="text-[var(--muted-foreground)]">{item}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="py-6 text-sm text-[var(--muted)]">{empty}</div>
      )}
    </section>
  );
}

function RecommendationList({
  title,
  items,
  empty,
}: {
  title: string;
  items: WorkbenchRecommendation[];
  empty: string;
}) {
  return (
    <section className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 className="heading-section">{title}</h2>
        <span className="badge">{items.length}</span>
      </div>
      {items.length > 0 ? (
        <div className="space-y-4">
          {items.map((item, index) => (
            <article key={`${item.title}-${index}`} className="border-l border-[var(--card-border)] pl-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-[var(--accent)]">{String(index + 1).padStart(2, "0")}</span>
                <h3 className="text-sm font-medium">{item.title}</h3>
                {item.priority && <span className="badge badge-warning">{item.priority}</span>}
              </div>
              {item.rationale && <p className="mt-2 text-xs leading-6 text-[var(--muted-foreground)]">{item.rationale}</p>}
              {item.action_items && item.action_items.length > 0 && (
                <div className="mt-3 space-y-1.5">
                  {item.action_items.map((action, actionIndex) => (
                    <div key={actionIndex} className="grid grid-cols-[18px_1fr] text-xs leading-5 text-[var(--muted-foreground)]">
                      <span className="text-[var(--accent)]">+</span>
                      <span>{action}</span>
                    </div>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      ) : (
        <div className="py-6 text-sm text-[var(--muted)]">{empty}</div>
      )}
    </section>
  );
}

function PredictionTimeline({
  versions,
  empty,
}: {
  versions: WorkbenchPredictionVersion[];
  empty: string;
}) {
  if (versions.length === 0) {
    return <div className="empty-state py-12"><div className="empty-state-title">{empty}</div></div>;
  }

  return (
    <div className="space-y-6">
      {versions.map((version, index) => {
        const previous = versions[index - 1];
        const currentPct = percentValue(version.probability);
        const previousPct = percentValue(previous?.probability);
        const delta = currentPct != null && previousPct != null ? currentPct - previousPct : null;

        return (
          <article key={`${version.id}-${index}`} className="grid grid-cols-[72px_1fr] gap-5">
            <div className="pt-1 text-right">
              <div className="font-mono text-xs text-[var(--accent)]">v{version.version_number}</div>
              <div className="mt-2 text-[11px] leading-4 text-[var(--muted)]">{formatDate(version.created_at)}</div>
            </div>
            <div className="relative border-l border-[var(--card-border)] pl-5">
              <span className="absolute -left-[5px] top-2 h-2.5 w-2.5 rounded-full border border-[var(--accent)] bg-[var(--card)]" />
              <div className="rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      {version.status && <span className="badge">{version.status}</span>}
                      <span className="text-xs text-[var(--muted)]">{version.trigger_type || "-"}</span>
                    </div>
                    {version.prediction_text && (
                      <p className="mt-3 text-sm leading-6 text-[var(--muted-foreground)]">{version.prediction_text}</p>
                    )}
                    {version.summary_delta && (
                      <p className="mt-3 border-l border-[var(--card-border)] pl-3 text-xs leading-5 text-[var(--muted)]">{version.summary_delta}</p>
                    )}
                  </div>
                  <div className="min-w-[150px]">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <span className="font-mono text-lg">{formatPercent(version.probability)}</span>
                      {delta != null && (
                        <span className={`font-mono text-xs ${delta >= 0 ? "text-[var(--accent-green)]" : "text-[var(--accent-red)]"}`}>
                          {delta >= 0 ? "+" : ""}{delta.toFixed(0)}pt
                        </span>
                      )}
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[var(--card-border)]">
                      <div className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-500" style={{ width: `${currentPct ?? 0}%` }} />
                    </div>
                    <div className="mt-2 text-right font-mono text-[11px] text-[var(--muted)]">{formatPercent(version.confidence)}</div>
                  </div>
                </div>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function ScenarioGrid({
  scenarios,
  empty,
}: {
  scenarios: WorkbenchAlternativeScenario[];
  empty: string;
}) {
  if (scenarios.length === 0) {
    return <div className="empty-state py-10"><div className="empty-state-title">{empty}</div></div>;
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {scenarios.map((scenario, index) => (
        <article key={`${scenario.name}-${index}`} className="rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
          <div className="flex items-start justify-between gap-4">
            <h3 className="text-sm font-medium leading-6">{scenario.name}</h3>
            {scenario.probability != null && <span className="badge">{formatPercent(scenario.probability)}</span>}
          </div>
          {scenario.description && <p className="mt-3 text-xs leading-6 text-[var(--muted-foreground)]">{scenario.description}</p>}
          {scenario.expected_outcome && (
            <div className="mt-4 border-l border-[var(--card-border)] pl-3">
              <div className="section-label !text-[var(--muted)]">OUTCOME</div>
              <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">{scenario.expected_outcome}</p>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}

export default function WorkbenchPage() {
  const { t } = useTranslation();
  const { data: sessions, error: sessionsError, isLoading: sessionsLoading } = useSWR("workbench-sessions", fetchSessions);
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");
  const [decision, setDecision] = useState<UserDecisionValue | null>(null);
  const [savingDecision, setSavingDecision] = useState(false);

  useEffect(() => {
    if (!selectedSessionId && sessions && sessions.length > 0) {
      setSelectedSessionId(sessions[0].id);
    }
  }, [selectedSessionId, sessions]);

  const { data: workbench, error: workbenchError, isLoading: workbenchLoading } = useSWR(
    selectedSessionId ? `decision-workbench-${selectedSessionId}` : null,
    () => fetchWorkbenchData(selectedSessionId),
  );

  const selectedSession = useMemo<StrategicSession | undefined>(
    () => sessions?.find((session) => session.id === selectedSessionId),
    [selectedSessionId, sessions],
  );

  const decisionLabelKey = (value: UserDecisionValue) => {
    if (value === "need_more_info") return "workbench.needMoreInfoDecision";
    return `workbench.${value}`;
  };

  const handleDecision = async (next: UserDecisionValue, message: string) => {
    if (!selectedSessionId || savingDecision) return;
    setSavingDecision(true);
    try {
      await createUserDecision({ session_id: selectedSessionId, decision: next });
      setDecision(next);
      toast.success(message);
    } catch (error) {
      toast.error(`${t("workbench.decisionSaveFailed")}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSavingDecision(false);
    }
  };

  const loading = sessionsLoading || (selectedSessionId && workbenchLoading);

  return (
    <div className="mx-auto max-w-[1500px] space-y-8">
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div>
          <div className="section-label">{t("workbench.title")}</div>
          <h1 className="heading-display mt-3">{t("workbench.subtitle")}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--muted-foreground)]">{t("workbench.description")}</p>
        </div>
        <section className="self-end rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
          <label className="section-label mb-3 block">{t("workbench.selectSession")}</label>
          <select
            value={selectedSessionId}
            onChange={(event) => {
              setSelectedSessionId(event.target.value);
              setDecision(null);
            }}
            className="w-full rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          >
            <option value="">{t("workbench.selectSessionPlaceholder")}</option>
            {(sessions || []).map((session) => (
              <option key={session.id} value={session.id}>
                {session.name || session.subject_name || session.topic}
              </option>
            ))}
          </select>
          {selectedSession && (
            <div className="mt-3 truncate text-xs text-[var(--muted)]">
              {selectedSession.domain_id} / {formatDate(selectedSession.created_at)}
            </div>
          )}
        </section>
      </div>

      <div className="divider-line" />

      {sessionsError && (
        <div className="rounded-lg border border-[var(--accent-red)]/30 bg-[var(--accent-red-bg)] p-4 text-sm text-[var(--accent-red)]">
          {t("workbench.loadFailed")}
        </div>
      )}

      {!sessionsLoading && !sessionsError && (!sessions || sessions.length === 0) && (
        <EmptyState title={t("workbench.noSessions")} description={t("workbench.noSessionsDescription")} />
      )}

      {loading && <SkeletonBlock rows={5} />}

      {!loading && workbenchError && (
        <div className="rounded-lg border border-[var(--accent-red)]/30 bg-[var(--accent-red-bg)] p-5 text-sm text-[var(--accent-red)]">
          <div className="font-medium">{t("workbench.loadFailed")}</div>
          <div className="mt-1 text-xs text-[var(--muted-foreground)]">{String(workbenchError)}</div>
        </div>
      )}

      {!loading && !workbenchError && workbench && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <aside className="space-y-6">
            <section className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <div className="section-label !text-[var(--muted)]">{t("workbench.currentRecommendation")}</div>
                  <h2 className="mt-3 text-xl font-semibold leading-8">{workbench.current_recommendation.verdict}</h2>
                </div>
                <span className={`badge ${confidenceTone(workbench.current_recommendation.confidence)}`}>
                  {formatPercent(workbench.current_recommendation.confidence)}
                </span>
              </div>
              <ConfidenceBar value={workbench.current_recommendation.confidence} />
              {workbench.current_recommendation.summary && (
                <p className="mt-5 text-sm leading-7 text-[var(--muted-foreground)]">{workbench.current_recommendation.summary}</p>
              )}
              <div className="mt-5 flex items-center gap-2 text-xs text-[var(--muted)]">
                <Clock3 size={14} />
                <span>{formatDate(workbench.generated_at)}</span>
              </div>
            </section>

            <NumberedList title={t("workbench.keyFindings")} items={workbench.findings} empty={t("workbench.noFindings")} />
            <NumberedList title={t("workbench.riskFactors")} items={workbench.risk_factors} empty={t("workbench.noRisks")} tone="text-[var(--accent-red)]" />
            <RecommendationList title={t("workbench.recommendations")} items={workbench.recommendations} empty={t("workbench.noRecommendations")} />
          </aside>

          <main className="space-y-6">
            <section className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
              <div className="mb-5 flex items-center justify-between gap-4">
                <h2 className="heading-section">{t("workbench.evidenceStrength")}</h2>
                <ShieldCheck size={18} className="text-[var(--accent)]" />
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <MetricCard label={t("workbench.evidenceCount")} value={String(workbench.evidence.evidence_count)} helper={t("workbench.evidenceItems")} />
                <MetricCard label={t("workbench.claimsCount")} value={String(workbench.evidence.claims_count)} helper={t("workbench.claimItems")} />
                <MetricCard label={t("workbench.confidence")} value={formatPercent(workbench.evidence.confidence)} helper={t("workbench.integratedConfidence")} />
              </div>
              {workbench.evidence.decisive_evidence.length > 0 && (
                <div className="mt-5 border-l border-[var(--card-border)] pl-4">
                  <div className="mb-2 flex items-center gap-2 section-label !text-[var(--muted)]">
                    <FileSearch size={14} />
                    {t("workbench.decisiveEvidence")}
                  </div>
                  <div className="space-y-1.5">
                    {workbench.evidence.decisive_evidence.slice(0, 4).map((item, index) => (
                      <div key={`${item}-${index}`} className="text-xs leading-5 text-[var(--muted-foreground)]">{item}</div>
                    ))}
                  </div>
                </div>
              )}
            </section>

            <section className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
              <div className="mb-6 flex items-center justify-between gap-4">
                <div>
                  <h2 className="heading-section">{t("workbench.predictionTimeline")}</h2>
                  <div className="mt-1 text-xs text-[var(--muted)]">{workbench.prediction_versions.length} {t("workbench.versions")}</div>
                </div>
                <TrendingUp size={18} className="text-[var(--accent)]" />
              </div>
              <PredictionTimeline versions={workbench.prediction_versions} empty={t("workbench.noPredictions")} />
            </section>

            <section className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
              <div className="mb-5 flex items-center justify-between gap-4">
                <h2 className="heading-section">{t("workbench.alternativeScenarios")}</h2>
                <Layers3 size={18} className="text-[var(--accent)]" />
              </div>
              <ScenarioGrid scenarios={workbench.alternative_scenarios} empty={t("workbench.noScenarios")} />
            </section>

            <section className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
              <div className="mb-4 flex items-center justify-between gap-4">
                <h2 className="heading-section">{t("workbench.decisionActions")}</h2>
                {savingDecision ? (
                  <span className="badge">{t("workbench.savingDecision")}</span>
                ) : (
                  decision && <span className="badge badge-success">{t(decisionLabelKey(decision))}</span>
                )}
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <button
                  type="button"
                  onClick={() => handleDecision("adopt", t("workbench.adoptedToast"))}
                  disabled={!selectedSessionId || savingDecision}
                  className="btn btn-primary justify-center"
                >
                  <CheckCircle2 size={16} />
                  {t("workbench.adoptRecommendation")}
                </button>
                <button
                  type="button"
                  onClick={() => handleDecision("defer", t("workbench.deferredToast"))}
                  disabled={!selectedSessionId || savingDecision}
                  className="btn btn-ghost justify-center"
                >
                  <PauseCircle size={16} />
                  {t("workbench.deferAction")}
                </button>
                <button
                  type="button"
                  onClick={() => handleDecision("need_more_info", t("workbench.moreInfoToast"))}
                  disabled={!selectedSessionId || savingDecision}
                  className="btn btn-ghost justify-center"
                >
                  <CircleHelp size={16} />
                  {t("workbench.needMoreInfo")}
                </button>
              </div>
              <div className="mt-4 flex items-start gap-2 text-xs leading-5 text-[var(--muted)]">
                <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[var(--accent-amber)]" />
                <span>{t("workbench.decisionNote")}</span>
              </div>
            </section>
          </main>
        </div>
      )}
    </div>
  );
}
