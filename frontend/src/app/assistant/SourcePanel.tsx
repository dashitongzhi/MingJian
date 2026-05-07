"use client";

import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "@/contexts/LanguageContext";
import { toText } from "@/lib/utils";
import type { AssistantResult, StrategicSessionDetail, WorkbenchAlternativeScenario } from "@/lib/api";
import { RecommendationCard } from "@/components/RecommendationCard";
import { SectionLabel } from "@/components/ui/status";
import { EmptyState, RichText, StreamingSkeleton } from "./ProcessPanel";

function SourceCard({ source, index }: { source: { title: string; url: string }; index: number }) {
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="grid grid-cols-[48px_minmax(0,1fr)_18px] gap-4 divider-subtle py-4 outline-none motion-safe:animate-[fadeIn_0.25s_ease-out] motion-safe:transition-opacity hover:opacity-85 focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]"
      style={{ animationDelay: `${index * 45}ms` }}
    >
      <div className="font-mono text-xs text-[var(--muted)]">{String(index + 1).padStart(2, "0")}</div>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{source.title}</div>
        <div className="mt-1 truncate font-mono text-xs text-[var(--muted)]">{source.url}</div>
      </div>
      <div className="text-[var(--accent)]">↗</div>
    </a>
  );
}

export function SourcePanel({ sources, streaming }: { sources: { title: string; url: string }[]; streaming: boolean }) {
  const { t } = useTranslation();

  if (sources.length > 0) {
    return (
      <div>
        {sources.map((source, index) => (
          <SourceCard key={index} source={source} index={index} />
        ))}
        {streaming && <StreamingSkeleton label={t("assistant.sources")} />}
      </div>
    );
  }

  if (streaming) return <StreamingSkeleton label={t("assistant.sources")} />;
  return <EmptyState title={t("assistant.noSources")} description={t("assistant.noSourcesDescription")} />;
}

export function SessionDetailPanel({ detail, onBack }: { detail: StrategicSessionDetail; onBack: () => void }) {
  const { t } = useTranslation();
  const { session, daily_briefs, recent_runs } = detail;

  return (
    <div className="motion-safe:animate-[fadeIn_0.25s_ease-out]">
      <div className="flex items-center justify-between divider-subtle px-5 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <button
            onClick={onBack}
            className="flex h-7 w-7 shrink-0 items-center justify-center border border-[var(--card-border)] font-mono text-xs text-[var(--muted)] outline-none motion-safe:transition-colors hover:text-[var(--foreground)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          >
            ←
          </button>
          <div className="min-w-0">
            <SectionLabel>{t("assistant.sessionDetail")}</SectionLabel>
            <div className="mt-1 truncate text-sm font-medium">{session.name || session.topic.slice(0, 60)}</div>
          </div>
        </div>
        <span className="badge shrink-0">{session.domain_id}</span>
      </div>

      <div className="px-5 py-5">
        {/* Session Info */}
        <div className="grid grid-cols-[48px_minmax(0,1fr)] gap-4 divider-subtle pb-5">
          <div className="font-mono text-xs text-[var(--muted)]">01</div>
          <div className="space-y-3">
            <div>
              <div className="section-label">{t("assistant.topic")}</div>
              <div className="mt-1 text-sm text-[var(--foreground)]">{session.topic}</div>
            </div>
            {session.subject_name && (
              <div>
                <div className="section-label">{t("assistant.subjectName")}</div>
                <div className="mt-1 text-sm text-[var(--foreground)]">{session.subject_name}</div>
              </div>
            )}
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              <div>
                <div className="section-label">{t("assistant.autoRefresh")}</div>
                <div className="mt-1">
                  <span className={`badge ${session.auto_refresh_enabled ? "badge-success" : "badge-error"}`}>
                    {session.auto_refresh_enabled ? t("assistant.enabled") : t("assistant.disabled")}
                  </span>
                </div>
              </div>
              <div>
                <div className="section-label">{t("assistant.createdAt")}</div>
                <div className="mt-1 font-mono text-xs text-[var(--muted-foreground)]">
                  {new Date(session.created_at).toLocaleString()}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Daily Briefs */}
        <div className="mt-6">
          <div className="mb-3 flex items-center justify-between">
            <SectionLabel>{t("assistant.dailyBriefs")}</SectionLabel>
            <span className="font-mono text-[11px] text-[var(--muted)]">{daily_briefs.length}</span>
          </div>
          {daily_briefs.length > 0 ? (
            <div className="space-y-0">
              {daily_briefs.map((brief, i) => (
                <div
                  key={brief.id}
                  className="grid grid-cols-[48px_minmax(0,1fr)] divider-subtle py-4 motion-safe:animate-[fadeIn_0.25s_ease-out]"
                  style={{ animationDelay: `${i * 45}ms` }}
                >
                  <div className="font-mono text-xs text-[var(--muted)]">{String(i + 1).padStart(2, "0")}</div>
                  <div className="min-w-0">
                    <div className="mb-1 section-label">
                      {t("assistant.briefSummary")} · {new Date(brief.generated_at).toLocaleDateString()}
                    </div>
                    <RichText text={brief.summary} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="divider-subtle py-6 text-sm text-[var(--muted)]">
              {t("assistant.noDailyBriefs")}
            </div>
          )}
        </div>

        {/* Recent Runs */}
        <div className="mt-6">
          <div className="mb-3 flex items-center justify-between">
            <SectionLabel>{t("assistant.recentRuns")}</SectionLabel>
            <span className="font-mono text-[11px] text-[var(--muted)]">{recent_runs.length}</span>
          </div>
          {recent_runs.length > 0 ? (
            <div className="space-y-0">
              {recent_runs.map((run, i) => {
                const verdict = run.result?.debate?.verdict;
                const recs = verdict?.recommendations || [];
                const risks = verdict?.risk_factors || [];
                const conclusion = verdict?.conclusion_summary;
                const debateId = run.debate_id || run.result?.debate?.id;

                const content = (
                  <div
                    className="divider-subtle py-5 motion-safe:animate-[fadeIn_0.25s_ease-out]"
                    style={{ animationDelay: `${i * 45}ms` }}
                  >
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span className="section-label">
                          {t("assistant.runResult")}
                        </span>
                        <span className="font-mono text-[10px] text-[var(--muted)]">{run.id.slice(0, 8)}</span>
                      </div>
                      <span className="font-mono text-[10px] text-[var(--muted)]">
                        {new Date(run.generated_at).toLocaleString()}
                      </span>
                    </div>

                    {/* Conclusion Summary (truncated) */}
                    {conclusion && (
                      <div className="mb-3 border-l-2 border-[var(--accent)] pl-3">
                        <p className="text-xs leading-5 text-[var(--muted-foreground)] line-clamp-2">
                          {conclusion.slice(0, 150)}{conclusion.length > 150 ? "…" : ""}
                        </p>
                      </div>
                    )}

                    {/* Analysis Summary */}
                    {run.result?.analysis?.summary && (
                      <div className="mb-3">
                        <RichText text={run.result.analysis.summary} />
                      </div>
                    )}

                    {/* Recommendations tags */}
                    {recs.length > 0 && (
                      <div className="mb-2 flex flex-wrap items-center gap-1.5">
                        <span className="text-[10px] text-[var(--muted)]">{t("assistant.recommendations")}:</span>
                        {recs.slice(0, 3).map((rec, ri) => (
                          <span key={ri} className="badge text-[10px] truncate max-w-[200px]">
                            {rec.title || (typeof rec === "string" ? rec : "")}
                          </span>
                        ))}
                        {recs.length > 3 && (
                          <span className="text-[10px] text-[var(--muted)]">+{recs.length - 3}</span>
                        )}
                      </div>
                    )}

                    {/* Risk Factors tags */}
                    {risks.length > 0 && (
                      <div className="mb-2 flex flex-wrap items-center gap-1.5">
                        <span className="text-[10px] text-[var(--accent-red)]">{t("assistant.riskFactors")}:</span>
                        {risks.slice(0, 3).map((risk, ri) => (
                          <span key={ri} className="badge badge-error text-[10px] truncate max-w-[200px]">
                            {typeof risk === "string" ? risk.slice(0, 40) : ""}
                          </span>
                        ))}
                        {risks.length > 3 && (
                          <span className="text-[10px] text-[var(--muted)]">+{risks.length - 3}</span>
                        )}
                      </div>
                    )}

                    {/* Key Findings */}
                    {run.result?.analysis?.findings && run.result.analysis.findings.length > 0 && (
                      <div className="mb-3 border-l border-[var(--card-border)] pl-4">
                        <div className="mb-2 section-label">
                          {t("assistant.keyFindings")}
                        </div>
                        <div className="space-y-1">
                          {run.result.analysis.findings.slice(0, 5).map((f, fi) => (
                            <div key={fi} className="flex gap-2 text-xs text-[var(--muted-foreground)]">
                              <span className="font-mono text-[var(--accent)]">{String(fi + 1).padStart(2, "0")}</span>
                              <span className="leading-5">{f}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Debate Verdict */}
                    {verdict && (
                      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 divider-subtle pt-3 text-xs">
                        <div className="flex items-center gap-2">
                          <span className="text-[var(--muted)]">{t("assistant.debateVerdict")}:</span>
                          <span className="badge badge-success uppercase">{verdict.verdict}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[var(--muted)]">{t("common.confidence")}:</span>
                          <span className="badge">{((verdict.confidence ?? 0) * 100).toFixed(0)}%</span>
                        </div>
                        {verdict.minority_opinion && (
                          <div className="flex items-center gap-2">
                            <span className="text-[var(--muted)]">{t("debate.minorityOpinion")}:</span>
                            <span className="text-[var(--muted-foreground)]">{verdict.minority_opinion.slice(0, 80)}</span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Simulation status */}
                    {run.result?.simulation_run && (
                      <div className="mt-2 flex items-center gap-2 text-xs text-[var(--muted)]">
                        <span>{t("assistant.simulation")}:</span>
                        <span className="font-mono">{run.result.simulation_run.id.slice(0, 8)}</span>
                        <span className="badge badge-warning uppercase">{run.result.simulation_run.status}</span>
                      </div>
                    )}

                    {/* Link to debate */}
                    {debateId && (
                      <div className="mt-2">
                        <Link href={`/debate?id=${debateId}`} className="text-xs text-[var(--accent)] hover:underline">
                          {t("assistant.viewFullDebate")} →
                        </Link>
                      </div>
                    )}
                  </div>
                );

                return debateId ? (
                  <Link key={run.id} href={`/debate?id=${debateId}`} className="block outline-none motion-safe:transition-opacity hover:opacity-85 focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]">
                    {content}
                  </Link>
                ) : (
                  <div key={run.id}>{content}</div>
                );
              })}
            </div>
          ) : (
            <div className="divider-subtle py-6 text-sm text-[var(--muted)]">
              {t("assistant.noRecentRuns")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultVerdictBadge({ verdict }: { verdict: string }) {
  const colors: Record<string, string> = {
    ACCEPTED: "badge-success",
    REJECTED: "badge-error",
    CONDITIONAL: "badge-warning",
  };
  return <span className={`badge uppercase text-sm ${colors[verdict] || "badge"}`}>{verdict}</span>;
}

export function ResultSection({
  result,
  onExport,
  onReanalyze,
  streaming,
}: {
  result: AssistantResult;
  onExport: () => void;
  onReanalyze: () => void;
  streaming: boolean;
}) {
  const { t } = useTranslation();
  const verdict = result.debate?.verdict;
  const recs = verdict?.recommendations || [];
  const simpleRecs = result.analysis.recommendations || [];
  const risks = verdict?.risk_factors || [];
  const scenarios = verdict?.alternative_scenarios || [];
  const conclusion = verdict?.conclusion_summary;

  return (
    <section className="mt-6 space-y-6 motion-safe:animate-[fadeIn_0.25s_ease-out]">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h3 className="heading-section">{t("assistant.analysisComplete")}</h3>
        <div className="flex flex-wrap items-center gap-2">
          {result.debate?.id && (
            <Link href={`/debate?id=${result.debate.id}`} className="btn btn-ghost text-xs">
              {t("assistant.viewFullDebate")}
            </Link>
          )}
          <button onClick={onReanalyze} disabled={streaming} className="btn btn-primary">
            <RefreshCw size={16} />
            {t("assistant.reanalyze")}
          </button>
          <button onClick={onExport} className="btn btn-ghost">{t("common.exportMd")}</button>
        </div>
      </div>

      {/* 1. Conclusion Summary */}
      {conclusion && verdict && (
        <div className="rounded-lg border-l-4 border-[var(--accent)] bg-[var(--card)] p-5">
          <div className="flex items-center gap-3 mb-3">
            <ResultVerdictBadge verdict={verdict.verdict} />
            <span className="text-sm text-[var(--muted)]">
              {t("assistant.confidence")}: <span className="font-mono text-[var(--foreground)]">{((verdict.confidence ?? 0) * 100).toFixed(0)}%</span>
            </span>
          </div>
          <p className="text-sm leading-7 text-[var(--muted-foreground)]">{conclusion}</p>
        </div>
      )}

      {/* 2. Structured Recommendations */}
      {recs.length > 0 && (
        <div>
          <SectionLabel>{t("assistant.actionRecommendations")}</SectionLabel>
          <div className="mt-3 space-y-3">
            {recs.map((rec, i) => (
              <RecommendationCard
                key={i}
                rec={rec}
                index={i}
                actionItemsLabel={t("assistant.actionItems")}
              />
            ))}
          </div>
        </div>
      )}

      {/* 2b. Simple recommendations fallback */}
      {recs.length === 0 && simpleRecs.length > 0 && (
        <div>
          <SectionLabel>{t("assistant.recommendations")}</SectionLabel>
          <div className="mt-3 space-y-3">
            {simpleRecs.map((rec, i) => (
              <div key={i} className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-4 flex items-start gap-3">
                <span className="font-mono text-xs text-[var(--accent)] shrink-0">{String(i + 1).padStart(2, "0")}</span>
                <RichText text={rec} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3. Risk Factors */}
      {risks.length > 0 && (
        <div>
          <SectionLabel>{t("assistant.riskFactors")}</SectionLabel>
          <div className="mt-3 overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--card)] divide-y divide-[var(--card-border)]">
            {risks.map((risk: string, i: number) => (
              <div key={i} className="flex items-start gap-3 p-4">
                <span className="font-mono text-xs text-[var(--accent-red)] shrink-0">{String(i + 1).padStart(2, "0")}</span>
                <span className="text-sm leading-6 text-[var(--muted-foreground)]">{typeof risk === "string" ? risk : toText(risk)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 4. Alternative Scenarios */}
      {scenarios.length > 0 && (
        <div>
          <SectionLabel>{t("assistant.alternativeScenarios")}</SectionLabel>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            {scenarios.map((sc: WorkbenchAlternativeScenario, i: number) => (
              <div key={i} className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-4">
                <h4 className="text-sm font-semibold mb-2">{sc.name || `Scenario ${String.fromCharCode(65 + i)}`}</h4>
                {sc.description && <p className="text-xs leading-6 text-[var(--muted-foreground)] mb-2">{sc.description}</p>}
                {sc.expected_outcome && (
                  <p className="text-xs text-[var(--muted)]">
                    {t("assistant.expectedOutcome")}: <span className="text-[var(--muted-foreground)]">{sc.expected_outcome}</span>
                  </p>
                )}
                {sc.probability != null && (
                  <span className="badge mt-2">{((sc.probability ?? 0) * 100).toFixed(0)}%</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. Debate Details (collapsible) */}
      {verdict && (
        <details className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
          <summary className="cursor-pointer font-medium text-sm">{t("assistant.debateDetails")}</summary>
          <div className="mt-4 space-y-4">
            {verdict.winning_arguments.length > 0 && (
              <div>
                <div className="text-xs font-medium text-[var(--muted)] mb-2">{t("assistant.winningArguments")}</div>
                <ul className="space-y-1">
                  {verdict.winning_arguments.map((arg, i) => (
                    <li key={i} className="text-sm text-[var(--muted-foreground)] flex items-start gap-2">
                      <span className="text-[var(--accent)] shrink-0">+</span>
                      {arg}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {verdict.decisive_evidence.length > 0 && (
              <div>
                <div className="text-xs font-medium text-[var(--muted)] mb-2">{t("assistant.decisiveEvidence")}</div>
                <ul className="space-y-1">
                  {verdict.decisive_evidence.map((ev, i) => (
                    <li key={i} className="text-sm text-[var(--muted-foreground)] flex items-start gap-2">
                      <span className="text-[var(--accent)] shrink-0">*</span>
                      {ev}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {verdict.minority_opinion && (
              <div className="border-l-2 border-[var(--accent-red)] pl-3">
                <div className="text-xs font-medium text-[var(--accent-red)] mb-1">{t("assistant.minorityOpinion")}</div>
                <p className="text-sm text-[var(--muted-foreground)]">{verdict.minority_opinion}</p>
              </div>
            )}

            {verdict.conditions && verdict.conditions.length > 0 && (
              <div>
                <div className="text-xs font-medium text-[var(--muted)] mb-2">{t("assistant.conditions")}</div>
                <ul className="space-y-1">
                  {verdict.conditions.map((cond, i) => (
                    <li key={i} className="text-sm text-[var(--muted-foreground)] flex items-start gap-2">
                      <span className="text-[var(--accent)] shrink-0">*</span>
                      {cond}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </details>
      )}

      {/* 6. Latest Report */}
      {result.latest_report && (
        <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-4">
          <SectionLabel>{t("assistant.latestReport")}</SectionLabel>
          <p className="mt-2 text-sm font-medium">{result.latest_report.title}</p>
          <p className="text-xs text-[var(--muted-foreground)] mt-1">{result.latest_report.summary}</p>
        </div>
      )}

      {/* 7. Analysis Summary */}
      <RichText text={result.analysis.summary} />

      {/* 8. Key Findings */}
      {result.analysis.findings.length > 0 && (
        <div>
          <SectionLabel>{t("assistant.keyFindings")}</SectionLabel>
          <div className="mt-3 divider-subtle">
            {result.analysis.findings.map((f, i) => (
              <div key={i} className="grid grid-cols-[34px_minmax(0,1fr)] gap-3 py-3 divider-subtle">
                <span className="font-mono text-xs text-[var(--accent)]">{String(i + 1).padStart(2, "0")}</span>
                <RichText text={f} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 9. Panel Discussion key points */}
      {result.panel_discussion.length > 0 && (
        <div>
          <SectionLabel>{t("assistant.panelDiscussion")}</SectionLabel>
          <div className="mt-3 space-y-3">
            {result.panel_discussion.map((msg, i) => (
              <div key={i} className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="font-medium text-sm">{msg.label}</span>
                  <span className={`badge text-xs ${msg.stance === "support" ? "badge-success" : msg.stance === "challenge" ? "badge-error" : "badge-warning"}`}>{msg.stance}</span>
                  <span className="text-xs text-[var(--muted)]">{(msg.confidence * 100).toFixed(0)}%</span>
                </div>
                <RichText text={msg.summary} />
                {msg.key_points.length > 0 && (
                  <div className="mt-2">
                    <div className="text-xs font-medium text-[var(--muted)] mb-1">{t("assistant.keyPoints")}</div>
                    <ul className="space-y-0.5">
                      {msg.key_points.map((kp, j) => (
                        <li key={j} className="text-xs text-[var(--muted-foreground)]">• {kp}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {msg.recommendation && (
                  <div className="mt-3 border-l-2 border-[var(--accent)] pl-3">
                    <div className="text-xs font-medium text-[var(--muted)] mb-1">{t("assistant.recommendation")}</div>
                    <RichText text={msg.recommendation} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 10. Simulation metadata */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-xs text-[var(--muted)]">
        {result.simulation_run && (
          <div className="flex items-center gap-2">
            <span>{t("assistant.simulation")}:</span>
            <span className="font-mono text-[var(--muted-foreground)]">{result.simulation_run.id.slice(0, 8)}</span>
            <span className="badge badge-warning uppercase">{result.simulation_run.status}</span>
          </div>
        )}
      </div>
    </section>
  );
}

