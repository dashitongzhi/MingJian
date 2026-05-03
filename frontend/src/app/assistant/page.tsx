"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { fetchSessions, streamAssistant, type AssistantResult, type AnalysisStep, type PanelMessage, type DebateRound } from "@/lib/api";
import type { ProcessStep, DebateMessage } from "@/components/ProcessVisualizer";
import { useTranslation } from "@/contexts/LanguageContext";
import { toast } from "@/lib/toast";
import { TextReveal, StaggerContainer, StaggerItem, AnimatedGradientText } from "@/components/ui/aceternity";

function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--muted)]">{children}</div>;
}

function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`motion-safe:animate-pulse rounded bg-[var(--card-border)]/55 ${className}`} />;
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex min-h-[320px] items-center border-t border-[var(--card-border)]">
      <div className="max-w-md py-12">
        <div className="text-sm font-medium text-[var(--foreground)]">{title}</div>
        <div className="mt-2 text-sm leading-6 text-[var(--muted)]">{description}</div>
      </div>
    </div>
  );
}

function StreamingSkeleton({ label }: { label: string }) {
  return (
    <div className="border-t border-[var(--card-border)] py-5 motion-safe:animate-[fadeIn_0.25s_ease-out]">
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
    <div className="grid grid-cols-[48px_minmax(0,1fr)] border-t border-[var(--card-border)] py-5 motion-safe:animate-[slideIn_0.25s_ease-out]">
      <div className="font-mono text-xs text-[var(--muted)]">{String(index + 1).padStart(2, "0")}</div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--accent)] ${tone[step.stage] || tone.default}`}>
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
      className="grid grid-cols-[48px_minmax(0,1fr)_18px] gap-4 border-t border-[var(--card-border)] py-4 outline-none motion-safe:animate-[fadeIn_0.25s_ease-out] motion-safe:transition-opacity hover:opacity-85 focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]"
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

function PanelMessageCard({ msg }: { msg: PanelMessage }) {
  const { t } = useTranslation();
  const stance = msg.stance === "support" ? "S" : msg.stance === "challenge" ? "C" : "M";

  return (
    <div className="border-t border-[var(--card-border)] py-5 motion-safe:animate-[fadeIn_0.25s_ease-out]">
      <div className="mb-3 flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-7 w-7 items-center justify-center border border-[var(--card-border)] font-mono text-[11px] text-[var(--accent)]">
            {stance}
          </span>
          <span className="truncate text-sm font-medium">{msg.label}</span>
        </div>
        <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-[var(--muted)]">{msg.stance}</span>
      </div>
      <RichText text={msg.summary} />
      {msg.recommendation && (
        <div className="mt-4 border-l border-[var(--accent)] pl-4">
          <div className="mb-1 text-xs text-[var(--muted)]">{t("assistant.recommendation")}</div>
          <RichText text={msg.recommendation} />
        </div>
      )}
    </div>
  );
}

function DebateRoundCard({ round }: { round: DebateRound }) {
  const { t } = useTranslation();
  const confidence = Math.max(0, Math.min(1, round.confidence));

  return (
    <div className="grid grid-cols-[48px_minmax(0,1fr)] border-t border-[var(--card-border)] py-5 motion-safe:animate-[slideIn_0.25s_ease-out]">
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
            <span className="font-mono text-xs text-[var(--muted)]">{(confidence * 100).toFixed(0)}%</span>
          </div>
        </div>
        <div className="mt-3">
          <RichText text={round.position} />
        </div>
      </div>
    </div>
  );
}

function ProcessTimeline({
  steps,
  debateMessages,
  currentStage,
  isStreaming,
}: {
  steps: ProcessStep[];
  debateMessages: DebateMessage[];
  currentStage: string;
  isStreaming: boolean;
}) {
  const { t } = useTranslation();

  if (steps.length === 0 && debateMessages.length === 0 && !isStreaming) {
    return <EmptyState title={t("assistant.waitingForAnalysis")} description={t("assistant.waitingForAnalysisDescription")} />;
  }

  return (
    <div>
      <div className="grid grid-cols-[48px_minmax(0,1fr)] border-t border-[var(--card-border)] py-4 text-xs text-[var(--muted)]">
        <span>ST</span>
        <span className="font-mono uppercase tracking-[0.14em] text-[var(--accent)]">{currentStage}</span>
      </div>
      {steps.map((step, index) => (
        <div key={step.id} className="grid grid-cols-[48px_minmax(0,1fr)] border-t border-[var(--card-border)] py-5">
          <div className="font-mono text-xs text-[var(--muted)]">{String(index + 1).padStart(2, "0")}</div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--accent)]">{step.stage}</span>
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
        <div key={`${message.role}-${message.round}-${index}`} className="grid grid-cols-[48px_minmax(0,1fr)] border-t border-[var(--card-border)] py-5">
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

export default function AssistantPage() {
  const { t } = useTranslation();
  const { data: sessions, error: sessionsError, mutate: refreshSessions } = useSWR("sessions", fetchSessions);
  const [steps, setSteps] = useState<AnalysisStep[]>([]);
  const [sources, setSources] = useState<{ title: string; url: string }[]>([]);
  const [discussions, setDiscussions] = useState<PanelMessage[]>([]);
  const [debateRounds, setDebateRounds] = useState<DebateRound[]>([]);
  const [result, setResult] = useState<AssistantResult | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
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
  const [currentStage, setCurrentStage] = useState("ingest");

  useEffect(() => {
    const hasVisited = localStorage.getItem("planagent_assistant_visited");
    if (!hasVisited) {
      setShowGuide(true);
      localStorage.setItem("planagent_assistant_visited", "true");
    }
  }, []);

  const handleRun = useCallback(async () => {
    if (!topic.trim()) return;
    setStreaming(true);
    setError(null);
    setSteps([]);
    setSources([]);
    setDiscussions([]);
    setDebateRounds([]);
    setResult(null);
    setActiveTab("process");
    setEvents([]);
    setProcessSteps([]);
    setDebateMessages([]);
    setCurrentStage("ingest");
    toast.info('分析已启动');
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await streamAssistant(
        { topic, domain_id: domainId, subject_name: subjectName || topic.slice(0, 50), tick_count: tickCount },
        (evt) => {
          setEvents(prev => [...prev, evt]);

          if (evt.event === "step") {
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
          } else if (evt.event === "debate_round") {
            const round = evt.payload as DebateRound;
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
            setResult(evt.payload as AssistantResult);
          }
        },
        ctrl.signal
      );
      refreshSessions();
      toast.success('分析完成');
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
    <div className="space-y-8">
      <header className="border-b border-[var(--card-border)] pb-7">
        <TextReveal>
          <SectionLabel>{t("assistant.title")}</SectionLabel>
        </TextReveal>
        <TextReveal delay={0.1}>
          <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight tracking-tight text-balance">
            <AnimatedGradientText>{t("assistant.subtitle")}</AnimatedGradientText>
          </h1>
        </TextReveal>
      </header>

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-[390px_minmax(0,1fr)]">
        <aside className="space-y-6 xl:sticky xl:top-[76px] xl:self-start">
          <section className="overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--card)]/85 backdrop-blur">
            <div className="flex items-center justify-between border-b border-[var(--card-border)] px-5 py-4">
              <h2 className="text-sm font-semibold">{t("assistant.missionInput")}</h2>
              <span className="font-mono text-[11px] text-[var(--muted)]">CMD</span>
            </div>

            <div className="p-5">
              <div className="overflow-hidden border border-[var(--card-border)] bg-[var(--code-bg)] focus-within:ring-2 focus-within:ring-[var(--accent)]">
                <div className="border-b border-[var(--card-border)] px-3 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--muted)]">
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
                <label className="mb-3 block text-xs text-[var(--muted)]">{t("assistant.quickStartExamples")}</label>
                <div className="space-y-1 border-y border-[var(--card-border)]">
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
                      className="grid w-full grid-cols-[28px_minmax(0,1fr)] gap-3 py-3 text-left text-xs outline-none motion-safe:transition-colors hover:bg-[var(--code-bg)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
                    >
                      <span className="font-mono text-[var(--accent)]">{String(index + 1).padStart(2, "0")}</span>
                      <span className="truncate text-[var(--muted-foreground)]">{example.topic}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-5 grid grid-cols-2 gap-4">
                <label className="block">
                  <span className="mb-2 block text-xs text-[var(--muted)]">{t("assistant.domain")}</span>
                  <select
                    className="w-full border border-[var(--card-border)] bg-[var(--code-bg)] px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-[var(--accent)]"
                    value={domainId}
                    onChange={(e) => setDomainId(e.target.value)}
                  >
                    <option value="auto">{t("assistant.autoDetect")}</option>
                    <option value="corporate">{t("assistant.corporate")}</option>
                    <option value="military">{t("assistant.military")}</option>
                  </select>
                </label>
                <label className="block">
                  <span className="mb-2 block text-xs text-[var(--muted)]">{t("assistant.ticks")}</span>
                  <div className="flex h-[38px] items-center gap-3 border border-[var(--card-border)] bg-[var(--code-bg)] px-3">
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
                <span className="mb-2 block text-xs text-[var(--muted)]">{t("assistant.subjectName")}</span>
                <input
                  className="w-full border border-[var(--card-border)] bg-[var(--code-bg)] px-3 py-2 text-sm outline-none placeholder:text-[var(--muted)] focus:ring-2 focus:ring-[var(--accent)]"
                  placeholder={t("assistant.subjectPlaceholder")}
                  value={subjectName}
                  onChange={(e) => setSubjectName(e.target.value)}
                />
              </label>

              <div className="mt-5 flex gap-3">
                <button
                  onClick={handleRun}
                  disabled={streaming || !topic.trim()}
                  className="flex flex-1 items-center justify-center gap-2 bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-[var(--accent-foreground)] outline-none motion-safe:transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45 focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
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
                    className="border border-[var(--accent-red)] px-4 py-2.5 text-sm text-[var(--accent-red)] outline-none motion-safe:transition-opacity hover:opacity-85 focus-visible:ring-2 focus-visible:ring-[var(--accent-red)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
                  >
                    {t("common.cancel")}
                  </button>
                )}
              </div>

              {error && (
                <div className="mt-5 border-l border-[var(--accent-red)] bg-[var(--accent-red-bg)] px-4 py-3 text-sm text-[var(--accent-red)]">
                  <div>{error}</div>
                  <button onClick={handleRun} className="mt-3 text-xs underline underline-offset-4">
                    {t("common.retry")}
                  </button>
                </div>
              )}
            </div>
          </section>

          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">{t("assistant.recentSessions")}</h2>
              <span className="font-mono text-[11px] text-[var(--muted)]">{sessions?.length ?? 0}</span>
            </div>
            <StaggerContainer className="max-h-[310px] overflow-y-auto border-y border-[var(--card-border)]">
              {!sessions && !sessionsError && (
                <div className="space-y-3 py-4">
                  <SkeletonLine className="h-4 w-10/12" />
                  <SkeletonLine className="h-4 w-7/12" />
                  <SkeletonLine className="h-4 w-9/12" />
                </div>
              )}
              {sessionsError && <div className="py-4 text-sm text-[var(--accent-red)]">{sessionsError.message}</div>}
              {sessions?.map((s) => (
                <StaggerItem key={s.id} className="border-b border-[var(--card-border)] py-3 last:border-0">
                  <div className="flex items-center justify-between gap-3">
                    <div className="truncate text-sm font-medium">{s.name || s.topic.slice(0, 40)}</div>
                    <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
                      {s.auto_refresh_enabled ? t("common.auto") : t("common.manual")}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-[var(--muted)]">{s.domain_id}</div>
                </StaggerItem>
              ))}
              {sessions && sessions.length === 0 && (
                <div className="py-6 text-sm text-[var(--muted)]">{t("assistant.noSessions")}</div>
              )}
            </StaggerContainer>
          </section>
        </aside>

        <main className="min-w-0">
          <div className="sticky top-[56px] z-10 -mx-1 mb-4 bg-[var(--background)]/80 px-1 py-2 backdrop-blur">
            <div className="flex gap-px overflow-x-auto border border-[var(--card-border)] bg-[var(--card-border)]">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`min-w-28 flex-1 px-4 py-3 text-sm outline-none motion-safe:transition-colors focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)] ${
                    activeTab === tab.id
                      ? "bg-[var(--accent)] text-[var(--accent-foreground)]"
                      : "bg-[var(--card)] text-[var(--muted-foreground)] hover:bg-[var(--card-hover)]"
                  }`}
                >
                  <span>{tab.label}</span>
                  {tab.count > 0 && <span className="ml-2 font-mono text-[11px] opacity-70">{tab.count}</span>}
                </button>
              ))}
            </div>
          </div>

          <section className="min-h-[560px] border border-[var(--card-border)] bg-[var(--card)]/60 backdrop-blur">
            <div className="flex items-center justify-between border-b border-[var(--card-border)] px-5 py-4">
              <div>
                <SectionLabel>{tabs.find((tab) => tab.id === activeTab)?.label}</SectionLabel>
              </div>
              <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--muted)]">
                {streaming ? t("common.running") : result ? t("assistant.analysisComplete") : t("common.auto")}
              </div>
            </div>
            <div className="px-5">
              {activeTab === "process" && (
                <ProcessTimeline
                  steps={processSteps}
                  debateMessages={debateMessages}
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
                      {debateRounds.map((r, i) => (
                        <DebateRoundCard key={i} round={r} />
                      ))}
                      {streaming && <StreamingSkeleton label={t("assistant.debateTrace")} />}
                    </div>
                  ) : streaming ? (
                    <StreamingSkeleton label={t("assistant.debateTrace")} />
                  ) : (
                    <EmptyState title={t("assistant.noDebate")} description={t("assistant.noDebateDescription")} />
                  )}
                </>
              )}
            </div>
          </section>

          {result && (
            <section className="mt-6 border border-[var(--card-border)] bg-[var(--card)]/70 p-5 motion-safe:animate-[fadeIn_0.25s_ease-out]">
              <div className="mb-5 flex items-center justify-between gap-4">
                <h3 className="text-sm font-semibold">{t("assistant.analysisComplete")}</h3>
                <button
                  onClick={handleExport}
                  className="border border-[var(--card-border)] px-3 py-2 text-xs text-[var(--muted-foreground)] outline-none motion-safe:transition-colors hover:bg-[var(--card-hover)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
                >
                  {t("common.exportMd")}
                </button>
              </div>

              <RichText text={result.analysis.summary} />

              {result.analysis.findings.length > 0 && (
                <div className="mt-6">
                  <SectionLabel>{t("assistant.keyFindings")}</SectionLabel>
                  <div className="mt-3 divide-y divide-[var(--card-border)] border-y border-[var(--card-border)]">
                    {result.analysis.findings.map((f, i) => (
                      <div key={i} className="grid grid-cols-[34px_minmax(0,1fr)] gap-3 py-3">
                        <span className="font-mono text-xs text-[var(--accent)]">{String(i + 1).padStart(2, "0")}</span>
                        <RichText text={f} />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-[var(--card-border)] pt-4 text-xs text-[var(--muted)]">
                {result.simulation_run && (
                  <div className="flex items-center gap-2">
                    <span>{t("assistant.simulation")}:</span>
                    <span className="font-mono text-[var(--muted-foreground)]">{result.simulation_run.id.slice(0, 8)}</span>
                    <span className="font-mono uppercase">{result.simulation_run.status}</span>
                  </div>
                )}
                {result.debate?.verdict && (
                  <div className="flex items-center gap-2">
                    <span>{t("assistant.verdict")}:</span>
                    <span className="font-mono uppercase text-[var(--muted-foreground)]">{result.debate.verdict.verdict}</span>
                    <span className="font-mono">{(result.debate.verdict.confidence * 100).toFixed(0)}%</span>
                  </div>
                )}
              </div>
            </section>
          )}
        </main>
      </div>

      {showGuide && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] px-4 backdrop-blur">
          <div className="w-full max-w-md border border-[var(--card-border)] bg-[var(--card)] p-6 motion-safe:animate-[fadeIn_0.25s_ease-out]">
            <div className="mb-6">
              <SectionLabel>{t("assistant.onboardingTitle")}</SectionLabel>
              <h2 className="mt-3 text-2xl font-semibold leading-tight text-balance">{t("assistant.onboardingSubtitle")}</h2>
            </div>

            <div className="mb-6 divide-y divide-[var(--card-border)] border-y border-[var(--card-border)]">
              {[
                { title: t("assistant.onboardingEnterTopic"), desc: t("assistant.onboardingEnterTopicDesc") },
                { title: t("assistant.onboardingAiAnalysis"), desc: t("assistant.onboardingAiAnalysisDesc") },
                { title: t("assistant.onboardingDebate"), desc: t("assistant.onboardingDebateDesc") },
                { title: t("assistant.onboardingInsights"), desc: t("assistant.onboardingInsightsDesc") },
              ].map((step, i) => (
                <div key={i} className={`grid grid-cols-[34px_minmax(0,1fr)] gap-3 py-4 motion-safe:transition-opacity ${i === guideStep ? "opacity-100" : "opacity-45"}`}>
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
                className="flex-1 border border-[var(--card-border)] px-4 py-2.5 text-sm text-[var(--muted-foreground)] outline-none motion-safe:transition-colors hover:bg-[var(--card-hover)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
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
                className="flex-1 bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-[var(--accent-foreground)] outline-none motion-safe:transition-opacity hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
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
