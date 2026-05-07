"use client";

import { useTranslation } from "@/contexts/LanguageContext";
import type { AnalysisStep } from "@/lib/api";
import type { DebateMessage, ProcessStep } from "@/components/ProcessVisualizer";
import { SkeletonLine } from "@/components/ui/status";
import type { SourceSearchState } from "./hooks";

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

export function ReasoningPanel({ steps, streaming }: { steps: AnalysisStep[]; streaming: boolean }) {
  const { t } = useTranslation();

  if (steps.length > 0) {
    return (
      <div>
        {steps.map((step, index) => (
          <StepIndicator key={index} step={step} index={index} />
        ))}
        {streaming && <StreamingSkeleton label={t("assistant.liveReasoning")} />}
      </div>
    );
  }

  if (streaming) return <StreamingSkeleton label={t("assistant.liveReasoning")} />;
  return <EmptyState title={t("assistant.waitingForAnalysis")} description={t("assistant.waitingForAnalysisDescription")} />;
}
