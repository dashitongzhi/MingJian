"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import useSWR, { mutate as globalMutate } from "swr";
import { RefreshCw } from "lucide-react";
import { fetchSessions, fetchSessionDetail, streamAssistant, type AssistantResult, type AnalysisStep, type PanelMessage, type DebateRound, type DebateVerdict, type StrategicSessionDetail, type WorkbenchAlternativeScenario } from "@/lib/api";
import { RecommendationCard } from "@/components/RecommendationCard";
import type { ProcessStep, DebateMessage } from "@/components/ProcessVisualizer";
import { useTranslation } from "@/contexts/LanguageContext";
import { toast } from "@/lib/toast";
import { TextReveal, StaggerContainer, StaggerItem } from "@/components/ui/aceternity";

function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="section-label">{children}</div>;
}

function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`motion-safe:animate-pulse rounded bg-[var(--card-border)]/55 ${className}`} />;
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex min-h-[320px] items-center divider-subtle">
      <div className="max-w-md py-12">
        <div className="heading-section text-[var(--foreground)]">{title}</div>
        <div className="mt-2 text-sm leading-6 text-[var(--muted)]">{description}</div>
      </div>
    </div>
  );
}

function StreamingSkeleton({ label }: { label: string }) {
  return (
    <div className="divider-subtle py-5 motion-safe:animate-[fadeIn_0.25s_ease-out]">
      <div className="mb-4 flex items-center gap-3 text-xs text-[var(--accent)]">
        <span className="h-2 w-2 rounded-full bg-[var(--accent)] motion-safe:animate-pulse" />
        <span>{label}</span>
      </div>
      <div className="space-y-3">
        <SkeletonLine className="h-3 w-11/12" />
        <SkeletonLine className="h-3 w-8/12" />
        <SkeletonLine className="h-3 w-10/12" />
      </div>
    </div>
  );
}

function RichText({ text }: { text: string }) {
  const segments: Array<{ type: "text" | "code"; content: string }> = [];
  const regex = /```[\w-]*\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) segments.push({ type: "text", content: text.slice(lastIndex, match.index) });
    segments.push({ type: "code", content: match[1].trim() });
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) segments.push({ type: "text", content: text.slice(lastIndex) });

  return (
    <div className="space-y-3 text-sm leading-7 text-[var(--muted-foreground)]">
      {segments.map((segment, index) => {
        if (segment.type === "code") {
          return (
            <pre key={index} className="overflow-x-auto border-l border-[var(--accent)] bg-[var(--code-bg)] px-4 py-3 font-mono text-xs leading-6 text-[var(--foreground)]">
              <code>{segment.content}</code>
            </pre>
          );
        }

        return segment.content
          .split(/\n{2,}/)
          .filter(Boolean)
          .map((block, blockIndex) => {
            const trimmed = block.trim();
            if (trimmed.startsWith(">")) {
              return (
                <blockquote key={`${index}-${blockIndex}`} className="border-l border-[var(--accent)] pl-4 text-[var(--foreground)]">
                  {trimmed.replace(/^>\s?/gm, "")}
                </blockquote>
              );
            }
            return <p key={`${index}-${blockIndex}`}>{trimmed}</p>;
          });
      })}
    </div>
  );
}

function StepIndicator({ step, index }: { step: AnalysisStep; index: number }) {
  const { t } = useTranslation();
  const tone: Record<string, string> = {
    ingest: "opacity-55",
    extract: "opacity-65",
    analyze: "opacity-80",
    simulate: "opacity-90",
    debate: "opacity-100",
    default: "opacity-70",
  };

  return (
    <div className="grid grid-cols-[48px_minmax(0,1fr)] divider-subtle py-5 motion-safe:animate-[slideIn_0.25s_ease-out]">
      <div className="font-mono text-xs text-[var(--muted)]">{String(index + 1).padStart(2, "0")}</div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`section-label ${tone[step.stage] || tone.default}`}>
            {step.stage}
          </span>
          <span className="text-xs text-[var(--muted)]">{t("assistant.step")} {index + 1}</span>
        </div>
        <div className="mt-2">
          <RichText text={step.message} />
        </div>
        {step.detail && (
          <div className="mt-3 border-l border-[var(--card-border)] pl-4 font-mono text-xs leading-6 text-[var(--muted)]">
            {step.detail}
          </div>
        )}
      </div>
    </div>
  );
}

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

type SourceSearchState = {
  provider: string;
  label: string;
  status: "searching" | "completed" | "failed";
  count?: number;
  error?: string;
  icon?: string;
  itemsPreview?: string[];
};

function SourceSearchProgress({ sources }: { sources: SourceSearchState[] }) {
  if (sources.length === 0) return null;

  const active = sources.filter((source) => source.status === "searching").length;
  const finished = sources.filter((source) => source.status !== "searching").length;
  const collected = sources.reduce((sum, source) => sum + (source.count || 0), 0);
  const statusClass: Record<SourceSearchState["status"], string> = {
    searching: "bg-[var(--accent)] motion-safe:animate-pulse",
    completed: "bg-[var(--accent-green)]",
    failed: "bg-[var(--accent-red)]",
  };
  const statusText: Record<SourceSearchState["status"], string> = {
    searching: "搜索中",
    completed: "完成",
    failed: "失败",
  };

  return (
    <div className="divider-subtle py-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="section-label">并行搜索</div>
          <div className="mt-1 text-sm text-[var(--muted-foreground)]">
            {active > 0
              ? `正在搜索 ${sources.find((source) => source.status === "searching")?.label || "公共来源"}... (${finished}/${sources.length})`
              : `搜索完成 (${finished}/${sources.length})`}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs text-[var(--muted)]">
          <span>active={active}</span>
          <span>items={collected}</span>
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {sources.map((source) => (
          <div key={source.provider} className="border border-[var(--card-border)] px-3 py-2">
            <div className="flex min-w-0 items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <span className={`h-2 w-2 shrink-0 rounded-full ${statusClass[source.status]}`} />
                {source.icon && <span className="text-sm shrink-0">{source.icon}</span>}
                <span className="truncate text-xs font-medium">{source.label}</span>
              </div>
              <span className="shrink-0 font-mono text-[11px] text-[var(--muted)]">
                {source.status === "completed" ? `${source.count || 0}` : statusText[source.status]}
              </span>
            </div>
            {source.status === "completed" && source.itemsPreview && source.itemsPreview.length > 0 && (
              <div className="mt-1.5 space-y-0.5 pl-4">
                {source.itemsPreview.slice(0, 3).map((item, j) => (
                  <div key={j} className="truncate text-[11px] text-[var(--muted-foreground)]">• {item}</div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function PanelMessageCard({ msg }: { msg: PanelMessage }) {
  const { t } = useTranslation();
  const stance = msg.stance === "support" ? "S" : msg.stance === "challenge" ? "C" : "M";
  const stanceBadge = msg.stance === "support" ? "badge-success" : msg.stance === "challenge" ? "badge-error" : "badge badge-warning";

  return (
    <div className="divider-subtle py-5 motion-safe:animate-[fadeIn_0.25s_ease-out]">
      <div className="mb-3 flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-7 w-7 items-center justify-center border border-[var(--card-border)] font-mono text-[11px] text-[var(--accent)]">
            {stance}
          </span>
          <span className="truncate text-sm font-medium">{msg.label}</span>
        </div>
        <span className={`badge ${stanceBadge}`}>{msg.stance}</span>
      </div>
      <RichText text={msg.summary} />
      {msg.recommendation && (
        <div className="mt-4 border-l border-[var(--accent)] pl-4">
          <div className="mb-1 section-label">{t("assistant.recommendation")}</div>
          <RichText text={msg.recommendation} />
        </div>
      )}
    </div>
  );
}

type AssistantRunParams = {
  topic: string;
  domain_id: string;
  subject_name: string;
  tick_count: number;
  session_name?: string;
};

type CurrentDebateRound = {
  round_number: number;
  role: string;
} | null;

function debateRoleLabel(role: string) {
  const labels: Record<string, string> = {
    advocate: "支持方",
    challenger: "反对方",
    arbitrator: "裁决方",
    strategist: "支持方",
    risk_analyst: "反对方",
    opportunist: "裁决方",
  };
  return labels[role] || role;
}

function debateArgumentText(value: unknown) {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["content", "text", "argument", "summary", "title"]) {
      if (typeof record[key] === "string" && record[key]) return record[key] as string;
    }
  }
  return String(value ?? "");
}

function DebateRoundCard({ round }: { round: DebateRound }) {
  const { t } = useTranslation();
  const confidence = Math.max(0, Math.min(1, round.confidence));
  const confidenceBadge = confidence >= 0.7 ? "badge-success" : confidence >= 0.4 ? "badge badge-warning" : "badge-error";
  const keyArguments = (round.arguments || []).map(debateArgumentText).filter(Boolean).slice(0, 4);

  return (
    <div className="grid grid-cols-[48px_minmax(0,1fr)] divider-subtle py-5 motion-safe:animate-[slideIn_0.25s_ease-out]">
      <div className="font-mono text-xs text-[var(--muted)]">{String(round.round_number).padStart(2, "0")}</div>
      <div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium capitalize">{round.role}</span>
            <span className="text-xs text-[var(--muted)]">{t("assistant.round")} {round.round_number}</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="h-1 w-24 overflow-hidden bg-[var(--code-bg)]">
              <div className="h-full origin-left bg-[var(--accent)] motion-safe:transition-transform" style={{ transform: `scaleX(${confidence})` }} />
            </div>
            <span className={`badge ${confidenceBadge}`}>{(confidence * 100).toFixed(0)}%</span>
          </div>
        </div>
        <div className="mt-3">
          <RichText text={round.position} />
        </div>
        {keyArguments.length > 0 && (
          <div className="mt-4 border-l border-[var(--card-border)] pl-4">
            <div className="mb-2 section-label !text-[var(--muted)]">关键论据</div>
            <div className="space-y-1.5">
              {keyArguments.map((argument, index) => (
                <div key={`${argument}-${index}`} className="grid grid-cols-[22px_1fr] text-xs leading-5 text-[var(--muted-foreground)]">
                  <span className="font-mono text-[var(--accent)]">+</span>
                  <span>{argument}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DebateStatusBar({ status, currentRound }: { status: "idle" | "in_progress" | "complete"; currentRound: CurrentDebateRound }) {
  if (status !== "in_progress" || !currentRound) return null;
  return (
    <div className="mt-5 flex items-center gap-3 rounded-md border border-[var(--card-border)] bg-[var(--background)] px-4 py-3 text-sm text-[var(--foreground)] motion-safe:animate-[fadeIn_0.25s_ease-out]">
      <span className="h-2 w-2 rounded-full bg-[var(--accent)] motion-safe:animate-pulse" />
      <span>第{currentRound.round_number}/4轮 · {debateRoleLabel(currentRound.role)}正在陈述...</span>
    </div>
  );
}

function DebateVerdictCard({ verdict }: { verdict: Pick<DebateVerdict, "verdict" | "confidence" | "winning_arguments"> }) {
  return (
    <div className="my-5 rounded-lg border border-[var(--accent)]/40 bg-[var(--background)] p-5 motion-safe:animate-[scaleIn_0.25s_ease-out]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="section-label !text-[var(--accent)]">最终裁决</div>
          <div className="mt-2 text-lg font-semibold uppercase">{verdict.verdict}</div>
        </div>
        <span className="badge badge-success">{(Math.max(0, Math.min(1, verdict.confidence)) * 100).toFixed(0)}%</span>
      </div>
      {verdict.winning_arguments.length > 0 && (
        <div className="space-y-2">
          {verdict.winning_arguments.map((argument, index) => (
            <div key={`${argument}-${index}`} className="grid grid-cols-[28px_1fr] text-sm leading-6 text-[var(--muted-foreground)]">
              <span className="font-mono text-xs text-[var(--accent)]">{String(index + 1).padStart(2, "0")}</span>
              <span>{argument}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ProcessTimeline({
  steps,
  debateMessages,
  sourceSearches,
  currentStage,
  isStreaming,
}: {
  steps: ProcessStep[];
  debateMessages: DebateMessage[];
  sourceSearches: SourceSearchState[];
  currentStage: string;
  isStreaming: boolean;
}) {
  const { t } = useTranslation();

  if (steps.length === 0 && debateMessages.length === 0 && sourceSearches.length === 0 && !isStreaming) {
    return <EmptyState title={t("assistant.waitingForAnalysis")} description={t("assistant.waitingForAnalysisDescription")} />;
  }

  return (
    <div>
      <div className="grid grid-cols-[48px_minmax(0,1fr)] divider-subtle py-4 text-xs text-[var(--muted)]">
        <span>ST</span>
        <span className="section-label">{currentStage}</span>
      </div>
      <SourceSearchProgress sources={sourceSearches} />
      {steps.map((step, index) => (
        <div key={step.id} className="grid grid-cols-[48px_minmax(0,1fr)] divider-subtle py-5">
          <div className="font-mono text-xs text-[var(--muted)]">{String(index + 1).padStart(2, "0")}</div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="section-label">{step.stage}</span>
              <span className="text-xs text-[var(--muted)]">{step.timestamp}</span>
            </div>
            <div className="mt-2 text-sm font-medium">{step.title}</div>
            {step.description && <div className="mt-1 text-sm leading-6 text-[var(--muted)]">{step.description}</div>}
            {step.sources && step.sources.length > 0 && (
              <div className="mt-3 space-y-1 border-l border-[var(--card-border)] pl-3">
                {step.sources.map((source, sourceIndex) => (
                  <a key={sourceIndex} href={source.url} target="_blank" rel="noopener noreferrer" className="block truncate text-xs text-[var(--muted-foreground)] hover:text-[var(--accent)]">
                    {source.title}
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
      {debateMessages.map((message, index) => (
        <div key={`${message.role}-${message.round}-${index}`} className="grid grid-cols-[48px_minmax(0,1fr)] divider-subtle py-5">
          <div className="font-mono text-xs text-[var(--muted)]">D{message.round}</div>
          <div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium capitalize">{message.role}</span>
              <span className="font-mono text-xs text-[var(--muted)]">{(message.confidence * 100).toFixed(0)}%</span>
            </div>
            <div className="mt-2">
              <RichText text={message.content} />
            </div>
          </div>
        </div>
      ))}
      {isStreaming && <StreamingSkeleton label={t("common.processing")} />}
    </div>
  );
}

function SessionDetailPanel({ detail, onBack }: { detail: StrategicSessionDetail; onBack: () => void }) {
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

function ResultSection({
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
                <span className="text-sm leading-6 text-[var(--muted-foreground)]">{typeof risk === "string" ? risk : JSON.stringify(risk)}</span>
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

export default function AssistantPage() {
  const { t } = useTranslation();
  const { data: sessions, error: sessionsError, mutate: refreshSessions } = useSWR("sessions", fetchSessions);
  const [steps, setSteps] = useState<AnalysisStep[]>([]);
  const [sources, setSources] = useState<{ title: string; url: string }[]>([]);
  const [discussions, setDiscussions] = useState<PanelMessage[]>([]);
  const [debateRounds, setDebateRounds] = useState<DebateRound[]>([]);
  const [debateStatus, setDebateStatus] = useState<"idle" | "in_progress" | "complete">("idle");
  const [currentDebateRound, setCurrentDebateRound] = useState<CurrentDebateRound>(null);
  const [debateVerdict, setDebateVerdict] = useState<DebateVerdict | null>(null);
  const [result, setResult] = useState<AssistantResult | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastRunParamsRef = useRef<AssistantRunParams | null>(null);
  const [topic, setTopic] = useState("");
  const [domainId, setDomainId] = useState("auto");
  const [subjectName, setSubjectName] = useState("");
  const [tickCount, setTickCount] = useState(4);
  const [activeTab, setActiveTab] = useState<"reasoning" | "sources" | "panel" | "debate" | "process">("reasoning");
  const [showGuide, setShowGuide] = useState(false);
  const [guideStep, setGuideStep] = useState(0);
  const [events, setEvents] = useState<Array<{ event: string; payload: any }>>([]);
  const [processSteps, setProcessSteps] = useState<ProcessStep[]>([]);
  const [debateMessages, setDebateMessages] = useState<DebateMessage[]>([]);
  const [sourceSearches, setSourceSearches] = useState<SourceSearchState[]>([]);
  const [currentStage, setCurrentStage] = useState("ingest");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const { data: sessionDetail, isLoading: sessionDetailLoading } = useSWR(
    selectedSessionId ? `session-detail/${selectedSessionId}` : null,
    () => fetchSessionDetail(selectedSessionId!),
  );

  useEffect(() => {
    const openSessionFromLocation = () => {
      const storedSessionId = window.sessionStorage.getItem("planagent_notification_session_id");
      const hashSessionId = window.location.hash.startsWith("#session-")
        ? decodeURIComponent(window.location.hash.slice("#session-".length))
        : "";
      const nextSessionId = storedSessionId || hashSessionId;
      if (nextSessionId) {
        setSelectedSessionId(nextSessionId);
        window.sessionStorage.removeItem("planagent_notification_session_id");
      }
    };

    const handleOpenSession = (event: Event) => {
      const sessionId = (event as CustomEvent<string>).detail;
      if (sessionId) {
        setSelectedSessionId(sessionId);
        window.sessionStorage.removeItem("planagent_notification_session_id");
      } else {
        openSessionFromLocation();
      }
    };

    openSessionFromLocation();
    window.addEventListener("hashchange", openSessionFromLocation);
    window.addEventListener("planagent-open-session", handleOpenSession);
    return () => {
      window.removeEventListener("hashchange", openSessionFromLocation);
      window.removeEventListener("planagent-open-session", handleOpenSession);
    };
  }, []);

  useEffect(() => {
    const hasVisited = localStorage.getItem("planagent_assistant_visited");
    if (!hasVisited) {
      setShowGuide(true);
      localStorage.setItem("planagent_assistant_visited", "true");
    }
  }, []);

  const handleRun = useCallback(async (overrideParams?: AssistantRunParams) => {
    const runParams = overrideParams || {
      topic,
      domain_id: domainId,
      subject_name: subjectName || topic.slice(0, 50),
      tick_count: tickCount,
      session_name: topic.slice(0, 80),
    };
    if (!runParams.topic.trim()) return;
    lastRunParamsRef.current = runParams;
    setSelectedSessionId(null);
    setStreaming(true);
    setError(null);
    setSteps([]);
    setSources([]);
    setDiscussions([]);
    setDebateRounds([]);
    setDebateStatus("idle");
    setCurrentDebateRound(null);
    setDebateVerdict(null);
    setResult(null);
    setActiveTab("process");
    setEvents([]);
    setProcessSteps([]);
    setDebateMessages([]);
    setSourceSearches([]);
    setCurrentStage("ingest");
    let hasError = false;
    toast.info('分析已启动');
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await streamAssistant(
        runParams,
        (evt) => {
          setEvents(prev => [...prev, evt]);

          if (evt.event === "source_start") {
            const payload = evt.payload as { provider: string; label?: string; agent_name?: string; agent_icon?: string; task_desc?: string };
            setSourceSearches(prev => {
              const next = prev.filter((source) => source.provider !== payload.provider);
              return [
                ...next,
                {
                  provider: payload.provider,
                  label: payload.label || payload.agent_name || payload.provider,
                  status: "searching",
                  icon: payload.agent_icon,
                },
              ];
            });
            setCurrentStage("fetch");
          } else if (evt.event === "source_complete") {
            const payload = evt.payload as { provider: string; label?: string; count?: number; items_preview?: string[] };
            setSourceSearches(prev => {
              const existing = prev.find((source) => source.provider === payload.provider);
              const next = prev.filter((source) => source.provider !== payload.provider);
              return [
                ...next,
                {
                  provider: payload.provider,
                  label: payload.label || existing?.label || payload.provider,
                  status: "completed",
                  count: payload.count || 0,
                  icon: existing?.icon,
                  itemsPreview: payload.items_preview,
                },
              ];
            });
          } else if (evt.event === "source_error") {
            const payload = evt.payload as { provider: string; label?: string; error?: string };
            setSourceSearches(prev => {
              const existing = prev.find((source) => source.provider === payload.provider);
              const next = prev.filter((source) => source.provider !== payload.provider);
              return [
                ...next,
                {
                  provider: payload.provider,
                  label: payload.label || existing?.label || payload.provider,
                  status: "failed",
                  error: payload.error,
                },
              ];
            });
          } else if (evt.event === "step") {
            const step = evt.payload as AnalysisStep;
            setSteps(p => [...p, step]);
            setProcessSteps(prev => [...prev, {
              id: `step-${Date.now()}`,
              stage: step.stage as any || "analyze",
              title: step.message || t("common.processing"),
              description: step.detail || "",
              details: step.detail ? [step.detail] : undefined,
              status: "completed",
              timestamp: new Date().toLocaleTimeString()
            }]);
            if (step.stage) setCurrentStage(step.stage);
          } else if (evt.event === "ingest_run") {
            const payload = evt.payload as { ingest_run?: string; summary?: Record<string, number> };
            setCurrentStage("ingest");
            setProcessSteps(prev => [...prev, {
              id: `ingest-${Date.now()}`,
              stage: "ingest",
              title: t("assistant.ingestStarted"),
              description: payload.ingest_run?.slice(0, 8) || "",
              status: "completed",
              timestamp: new Date().toLocaleTimeString(),
            }]);
          } else if (evt.event === "simulation_run") {
            const payload = evt.payload as { simulation_run?: string; status?: string };
            setCurrentStage("simulate");
            setProcessSteps(prev => [...prev, {
              id: `sim-${Date.now()}`,
              stage: "simulate",
              title: t("assistant.simulationStarted"),
              description: payload.simulation_run?.slice(0, 8) || "",
              status: "completed",
              timestamp: new Date().toLocaleTimeString(),
            }]);
          } else if (evt.event === "source") {
            const source = evt.payload as { title: string; url: string };
            setSources(p => [...p, source]);
            setProcessSteps(prev => {
              const newSteps = [...prev];
              if (newSteps.length > 0) {
                const lastStep = newSteps[newSteps.length - 1];
                if (!lastStep.sources) lastStep.sources = [];
                lastStep.sources.push({
                  title: source.title,
                  url: source.url
                });
              }
              return newSteps;
            });
          } else if (evt.event === "discussion") {
            setDiscussions(p => [...p, evt.payload as PanelMessage]);
          } else if (evt.event === "debate_round_start") {
            const payload = evt.payload as { round_number: number; role: string };
            setDebateStatus("in_progress");
            setCurrentDebateRound(payload);
            setCurrentStage("debate");
          } else if (evt.event === "debate_round_complete") {
            const payload = evt.payload as { round_number: number; role: string; position: string; confidence: number; key_arguments?: string[] };
            const round: DebateRound = {
              round_number: payload.round_number,
              role: payload.role,
              position: payload.position,
              confidence: payload.confidence,
              arguments: (payload.key_arguments || []).map((argument) => ({ content: argument })),
              rebuttals: [],
              concessions: [],
            };
            setDebateStatus("in_progress");
            setDebateRounds(p => [...p, round]);
            setDebateMessages(prev => [...prev, {
              role: round.role as "advocate" | "challenger" | "arbitrator",
              round: round.round_number,
              content: round.position,
              confidence: round.confidence,
              arguments: payload.key_arguments || [],
              rebuttals: []
            }]);
            setCurrentStage("debate");
          } else if (evt.event === "debate_verdict") {
            const payload = evt.payload as DebateVerdict;
            setDebateVerdict(payload);
            setDebateStatus("complete");
            setCurrentDebateRound(null);
            setCurrentStage("debate");
          } else if (evt.event === "debate_round") {
            const round = evt.payload as DebateRound;
            setDebateStatus("in_progress");
            setDebateRounds(p => [...p, round]);
            setDebateMessages(prev => [...prev, {
              role: round.role as "advocate" | "challenger" | "arbitrator",
              round: round.round_number,
              content: round.position,
              confidence: round.confidence,
              arguments: round.arguments?.map((a: any) => String(a.content || a)) || [],
              rebuttals: round.rebuttals?.map((r: any) => String(r.content || r)) || []
            }]);
            setCurrentStage("debate");
          } else if (evt.event === "assistant_result") {
            const nextResult = evt.payload as AssistantResult;
            setResult(nextResult);
            if (nextResult.debate?.verdict) {
              setDebateVerdict(nextResult.debate.verdict);
              setDebateStatus("complete");
              setCurrentDebateRound(null);
            }
          } else if (evt.event === "error") {
            hasError = true;
            const errPayload = evt.payload as { message?: string } | undefined;
            setError(errPayload?.message || t("assistant.sseError"));
          }
        },
        ctrl.signal
      );
      refreshSessions();
      if (!hasError) {
        toast.success(t("assistant.analysisCompleteToast"));
      }
      // Plan A: refresh all cross-page SWR caches
      globalMutate("sim-runs");
      globalMutate("ev");
      globalMutate("cl");
      globalMutate("scoreboard");
      globalMutate("health");
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== "AbortError") setError(err.message);
    } finally {
      setStreaming(false);
      setCurrentDebateRound(null);
    }
  }, [topic, domainId, subjectName, tickCount, refreshSessions, t]);

  const handleExport = useCallback(() => {
    if (!result) return;

    const report = `# PlanAgent Analysis Report

## Topic
${result.topic}

## Domain
${result.domain_id}

## Subject
${result.subject_name}

## Analysis Summary
${result.analysis.summary}

## Key Findings
${result.analysis.findings.map((f, i) => `${i + 1}. ${f}`).join("\n")}

## Recommendations
${result.analysis.recommendations.map((r, i) => `${i + 1}. ${r}`).join("\n")}

## Sources
${result.analysis.sources.map((s, i) => `${i + 1}. [${s.title}](${s.url}) - ${s.summary}`).join("\n")}

## Panel Discussion
${result.panel_discussion.map((d, i) => `### ${d.label} (${d.stance})
${d.summary}
${d.recommendation ? `Recommendation: ${d.recommendation}` : ""}
`).join("\n")}

${result.debate ? `## Debate Verdict
- Verdict: ${result.debate.verdict?.verdict ?? "N/A"}
- Confidence: ${((result.debate.verdict?.confidence ?? 0) * 100).toFixed(0)}%
- Winning Arguments: ${result.debate.verdict?.winning_arguments?.join(", ") ?? "N/A"}
- Decisive Evidence: ${result.debate.verdict?.decisive_evidence?.join(", ") ?? "N/A"}
${result.debate.verdict?.minority_opinion ? `- Minority Opinion: ${result.debate.verdict.minority_opinion}` : ""}
` : ""}

## Simulation Results
- Run ID: ${result.simulation_run.id}
- Status: ${result.simulation_run.status}
- Ticks: ${result.simulation_run.tick_count}

---
*Generated by PlanAgent on ${new Date(result.generated_at).toLocaleString()}*
`;

    const blob = new Blob([report], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `planagent-report-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  const tabs = [
    { id: "process" as const, label: t("assistant.process"), count: processSteps.length },
    { id: "reasoning" as const, label: t("assistant.reasoning"), count: steps.length },
    { id: "sources" as const, label: t("assistant.sources"), count: sources.length },
    { id: "panel" as const, label: t("assistant.panel"), count: discussions.length },
    { id: "debate" as const, label: t("assistant.debate"), count: debateRounds.length },
  ];

  return (
    <div className="space-y-6">
      <header className="divider-subtle pb-7">
        <TextReveal>
          <SectionLabel>{t("assistant.title")}</SectionLabel>
        </TextReveal>
        <TextReveal delay={0.1}>
          <h1 className="heading-display mt-4 max-w-3xl text-balance">
            {t("assistant.subtitle")}
          </h1>
        </TextReveal>
      </header>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[390px_minmax(0,1fr)]">
        <aside className="space-y-6 xl:sticky xl:top-[76px] xl:self-start">
          <section className="overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--card)]">
            <div className="flex items-center justify-between divider-subtle px-5 py-4">
              <h2 className="heading-section">{t("assistant.missionInput")}</h2>
              <span className="badge">CMD</span>
            </div>

            <div className="p-5">
              <div className="overflow-hidden rounded-md border border-[var(--input)] bg-[var(--background)] focus-within:ring-2 focus-within:ring-[var(--accent)] focus-within:ring-offset-1 focus-within:ring-offset-[var(--card)]">
                <div className="divider-subtle px-3 py-2 section-label">
                  {t("assistant.topicPlaceholder")}
                </div>
                <textarea
                  className="min-h-[150px] w-full resize-none bg-transparent px-4 py-4 text-sm leading-7 text-[var(--foreground)] outline-none placeholder:text-[var(--muted)]"
                  placeholder={t("assistant.topicPlaceholder")}
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                />
              </div>

              <div className="mt-5">
                <label className="mb-3 block section-label">{t("assistant.quickStartExamples")}</label>
                <div className="space-y-1 divider-subtle">
                  {[
                    { topic: t("assistant.exampleTaiwan"), domain: "military" },
                    { topic: t("assistant.exampleEv"), domain: "corporate" },
                    { topic: t("assistant.exampleSemiconductor"), domain: "corporate" },
                    { topic: t("assistant.exampleMiddleEast"), domain: "military" },
                  ].map((example, index) => (
                    <button
                      key={example.topic}
                      onClick={() => {
                        setTopic(example.topic);
                        setDomainId(example.domain);
                      }}
                      className="grid w-full grid-cols-[28px_minmax(0,1fr)] gap-3 py-3 text-left text-xs outline-none motion-safe:transition-colors hover:text-[var(--foreground)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
                    >
                      <span className="font-mono text-[var(--accent)]">{String(index + 1).padStart(2, "0")}</span>
                      <span className="truncate text-[var(--muted-foreground)]">{example.topic}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-5 grid grid-cols-2 gap-4">
                <label className="block">
                  <span className="mb-2 block section-label">{t("assistant.domain")}</span>
                  <select
                    className="w-full rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-[var(--accent)]"
                    value={domainId}
                    onChange={(e) => setDomainId(e.target.value)}
                  >
                    <option value="auto">{t("assistant.autoDetect")}</option>
                    <option value="corporate">{t("assistant.corporate")}</option>
                    <option value="military">{t("assistant.military")}</option>
                  </select>
                </label>
                <label className="block">
                  <span className="mb-2 block section-label">{t("assistant.ticks")}</span>
                  <div className="flex h-[38px] items-center gap-3 rounded-md border border-[var(--input)] bg-[var(--background)] px-3">
                    <input
                      type="range"
                      min={2}
                      max={12}
                      value={tickCount}
                      onChange={(e) => setTickCount(Number(e.target.value))}
                      className="min-w-0 flex-1 accent-[var(--accent)]"
                    />
                    <span className="w-6 text-right font-mono text-sm text-[var(--accent)]">{tickCount}</span>
                  </div>
                </label>
              </div>

              <label className="mt-5 block">
                <span className="mb-2 block section-label">{t("assistant.subjectName")}</span>
                <input
                  className="w-full rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm outline-none placeholder:text-[var(--muted)] focus:ring-2 focus:ring-[var(--accent)]"
                  placeholder={t("assistant.subjectPlaceholder")}
                  value={subjectName}
                  onChange={(e) => setSubjectName(e.target.value)}
                />
              </label>

              <div className="mt-5 flex gap-3">
                <button
                  onClick={() => handleRun()}
                  disabled={streaming || !topic.trim()}
                  className="btn btn-primary flex-1 gap-2"
                >
                  {streaming ? (
                    <>
                      <span className="h-2 w-2 rounded-full bg-[var(--accent-foreground)] motion-safe:animate-pulse" />
                      {t("common.running")}
                    </>
                  ) : (
                    <>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polygon points="5 3 19 12 5 21 5 3" />
                      </svg>
                      {t("assistant.runAnalysis")}
                    </>
                  )}
                </button>
                {streaming && (
                  <button
                    onClick={() => abortRef.current?.abort()}
                    className="badge-error border border-[var(--accent-red)] px-4 py-2.5 text-sm outline-none motion-safe:transition-opacity hover:opacity-85 focus-visible:ring-2 focus-visible:ring-[var(--accent-red)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
                  >
                    {t("common.cancel")}
                  </button>
                )}
              </div>

              {error && (
                <div className="mt-5 border-l border-[var(--accent-red)] bg-[var(--accent-red-bg)] px-4 py-3 text-sm text-[var(--accent-red)]">
                  <div>{error}</div>
                  <button onClick={() => handleRun()} className="mt-3 text-xs underline underline-offset-4">
                    {t("common.retry")}
                  </button>
                </div>
              )}
            </div>
          </section>

          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="heading-section">{t("assistant.recentSessions")}</h2>
              <span className="font-mono text-[11px] text-[var(--muted)]">{sessions?.length ?? 0}</span>
            </div>
            <StaggerContainer className="max-h-[310px] overflow-y-auto">
              {!sessions && !sessionsError && (
                <div className="space-y-3 py-4">
                  <SkeletonLine className="h-4 w-10/12" />
                  <SkeletonLine className="h-4 w-7/12" />
                  <SkeletonLine className="h-4 w-9/12" />
                </div>
              )}
              {sessionsError && <div className="py-4 text-sm text-[var(--accent-red)]">{sessionsError.message}</div>}
              {sessions?.map((s) => (
                <StaggerItem
                  key={s.id}
                  className={`divider-subtle last:border-0 ${
                    selectedSessionId === s.id ? "border-l-2 border-l-[var(--accent)] bg-[var(--code-bg)]" : ""
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedSessionId(s.id)}
                    className="w-full py-3 text-left outline-none motion-safe:transition-colors hover:text-[var(--foreground)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="truncate text-sm font-medium">{s.name || s.topic.slice(0, 40)}</div>
                      <span className={`badge shrink-0 ${s.auto_refresh_enabled ? "badge-success" : ""}`}>
                        {s.auto_refresh_enabled ? t("common.auto") : t("common.manual")}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-[var(--muted)]">{s.domain_id}</div>
                  </button>
                </StaggerItem>
              ))}
              {sessions && sessions.length === 0 && (
                <div className="py-6 text-sm text-[var(--muted)]">{t("assistant.noSessions")}</div>
              )}
            </StaggerContainer>
          </section>
        </aside>

        <main className="min-w-0">
          {selectedSessionId && sessionDetail ? (
            <section className="min-h-[560px] rounded-lg border border-[var(--card-border)] bg-[var(--card)]">
              <SessionDetailPanel
                detail={sessionDetail}
                onBack={() => setSelectedSessionId(null)}
              />
            </section>
          ) : selectedSessionId ? (
            <section className="min-h-[560px] rounded-lg border border-[var(--card-border)] bg-[var(--card)]">
              <div className="px-5 py-10 space-y-3">
                <SkeletonLine className="h-4 w-8/12" />
                <SkeletonLine className="h-4 w-6/12" />
                <SkeletonLine className="h-4 w-10/12" />
              </div>
            </section>
          ) : (
            <>
          <div className="sticky top-[52px] z-10 -mx-1 mb-4 bg-[var(--background)]/95 px-1 py-2">
            <div className="flex gap-0 overflow-x-auto">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`relative min-w-28 flex-1 px-4 py-3 text-sm outline-none motion-safe:transition-colors focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)] ${
                    activeTab === tab.id
                      ? "text-[var(--foreground)]"
                      : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                >
                  <span>{tab.label}</span>
                  {tab.count > 0 && <span className="ml-2 font-mono text-[11px] opacity-70">{tab.count}</span>}
                  {activeTab === tab.id && (
                    <span className="absolute inset-x-4 bottom-0 h-px bg-[var(--accent)]" />
                  )}
                </button>
              ))}
            </div>
            <div className="divider-line" />
          </div>

          <section className="min-h-[560px] rounded-lg border border-[var(--card-border)] bg-[var(--card)]">
            <div className="flex items-center justify-between divider-subtle px-5 py-4">
              <div>
                <SectionLabel>{tabs.find((tab) => tab.id === activeTab)?.label}</SectionLabel>
              </div>
              <div className="flex items-center gap-2">
                {streaming ? (
                  <span className="badge badge-warning">{t("common.running")}</span>
                ) : result ? (
                  <span className="badge badge-success">{t("assistant.analysisComplete")}</span>
                ) : (
                  <span className="badge">{t("common.auto")}</span>
                )}
              </div>
            </div>
            <div className="px-5">
              {activeTab === "process" && (
                <ProcessTimeline
                  steps={processSteps}
                  debateMessages={debateMessages}
                  sourceSearches={sourceSearches}
                  currentStage={currentStage}
                  isStreaming={streaming}
                />
              )}

              {activeTab === "reasoning" && (
                <>
                  {steps.length > 0 ? (
                    <div>
                      {steps.map((s, i) => (
                        <StepIndicator key={i} step={s} index={i} />
                      ))}
                      {streaming && <StreamingSkeleton label={t("assistant.liveReasoning")} />}
                    </div>
                  ) : streaming ? (
                    <StreamingSkeleton label={t("assistant.liveReasoning")} />
                  ) : (
                    <EmptyState title={t("assistant.waitingForAnalysis")} description={t("assistant.waitingForAnalysisDescription")} />
                  )}
                </>
              )}

              {activeTab === "sources" && (
                <>
                  {sources.length > 0 ? (
                    <div>
                      {sources.map((s, i) => (
                        <SourceCard key={i} source={s} index={i} />
                      ))}
                      {streaming && <StreamingSkeleton label={t("assistant.sources")} />}
                    </div>
                  ) : streaming ? (
                    <StreamingSkeleton label={t("assistant.sources")} />
                  ) : (
                    <EmptyState title={t("assistant.noSources")} description={t("assistant.noSourcesDescription")} />
                  )}
                </>
              )}

              {activeTab === "panel" && (
                <>
                  {discussions.length > 0 ? (
                    <div>
                      {discussions.map((d, i) => (
                        <PanelMessageCard key={i} msg={d} />
                      ))}
                      {streaming && <StreamingSkeleton label={t("assistant.panelDiscussion")} />}
                    </div>
                  ) : streaming ? (
                    <StreamingSkeleton label={t("assistant.panelDiscussion")} />
                  ) : (
                    <EmptyState title={t("assistant.noPanelDiscussion")} description={t("assistant.noPanelDiscussionDescription")} />
                  )}
                </>
              )}

              {activeTab === "debate" && (
                <>
                  {debateRounds.length > 0 ? (
                    <div>
                      <DebateStatusBar status={debateStatus} currentRound={currentDebateRound} />
                      {debateRounds.map((r, i) => (
                        <DebateRoundCard key={i} round={r} />
                      ))}
                      {debateVerdict && <DebateVerdictCard verdict={debateVerdict} />}
                      {streaming && <StreamingSkeleton label={t("assistant.debateTrace")} />}
                    </div>
                  ) : streaming ? (
                    <div>
                      <DebateStatusBar status={debateStatus} currentRound={currentDebateRound} />
                      <StreamingSkeleton label={t("assistant.debateTrace")} />
                    </div>
                  ) : (
                    debateVerdict ? (
                      <DebateVerdictCard verdict={debateVerdict} />
                    ) : (
                      <EmptyState title={t("assistant.noDebate")} description={t("assistant.noDebateDescription")} />
                    )
                  )}
                </>
              )}
            </div>
          </section>

          {result && <ResultSection result={result} onExport={handleExport} onReanalyze={() => { const p = lastRunParamsRef.current; if (p) handleRun(p); }} streaming={streaming} />}
            </>
          )}
        </main>
      </div>

      {showGuide && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] px-4">
          <div className="w-full max-w-md rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-6 motion-safe:animate-[fadeIn_0.25s_ease-out]">
            <div className="mb-6">
              <SectionLabel>{t("assistant.onboardingTitle")}</SectionLabel>
              <h2 className="heading-display mt-3 text-balance">{t("assistant.onboardingSubtitle")}</h2>
            </div>

            <div className="mb-6">
              {[
                { title: t("assistant.onboardingEnterTopic"), desc: t("assistant.onboardingEnterTopicDesc") },
                { title: t("assistant.onboardingAiAnalysis"), desc: t("assistant.onboardingAiAnalysisDesc") },
                { title: t("assistant.onboardingDebate"), desc: t("assistant.onboardingDebateDesc") },
                { title: t("assistant.onboardingInsights"), desc: t("assistant.onboardingInsightsDesc") },
              ].map((step, i) => (
                <div key={i} className={`grid grid-cols-[34px_minmax(0,1fr)] gap-3 py-4 divider-subtle motion-safe:transition-opacity ${i === guideStep ? "opacity-100" : "opacity-45"}`}>
                  <span className="font-mono text-xs text-[var(--accent)]">{String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <div className="text-sm font-medium">{step.title}</div>
                    <div className="mt-1 text-xs leading-5 text-[var(--muted)]">{step.desc}</div>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowGuide(false)}
                className="btn btn-ghost flex-1"
              >
                {t("common.skip")}
              </button>
              <button
                onClick={() => {
                  if (guideStep < 3) {
                    setGuideStep(guideStep + 1);
                  } else {
                    setShowGuide(false);
                  }
                }}
                className="btn btn-primary flex-1"
              >
                {guideStep < 3 ? t("common.next") : t("common.getStarted")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
