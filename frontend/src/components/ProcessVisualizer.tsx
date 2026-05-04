"use client";
import { useState, useEffect, useRef } from "react";
import { useTranslation } from "@/contexts/LanguageContext";

export interface ProcessStep {
  id: string;
  stage: "ingest" | "extract" | "analyze" | "simulate" | "debate" | "synthesis";
  title: string;
  description: string;
  details?: string[];
  status: "pending" | "running" | "completed" | "error";
  timestamp?: string;
  startTime?: string;
  endTime?: string;
  modelOutput?: string;
  sources?: Array<{ title: string; url: string; snippet?: string }>;
}

export interface DebateMessage {
  role: "advocate" | "challenger" | "arbitrator";
  round: number;
  content: string;
  confidence: number;
  arguments: string[];
  rebuttals?: string[];
}

export interface AgentState {
  provider: string;
  agent_name: string;
  agent_icon: string;
  task_desc: string;
  status: "searching" | "completed" | "failed";
  count?: number;
  error?: string;
  items_preview?: string[];
}

interface ProcessVisualizerProps {
  steps: ProcessStep[];
  debateMessages: DebateMessage[];
  currentStage: string;
  isStreaming: boolean;
  agents?: AgentState[];
}

const stageConfig = {
  ingest: {
    icon: "📥",
    color: "blue",
    labelKey: "process.stages.ingest",
  },
  extract: {
    icon: "🔍",
    color: "purple",
    labelKey: "process.stages.extract",
  },
  analyze: {
    icon: "📊",
    color: "yellow",
    labelKey: "process.stages.analyze",
  },
  simulate: {
    icon: "🎯",
    color: "green",
    labelKey: "process.stages.simulate",
  },
  debate: {
    icon: "⚖️",
    color: "red",
    labelKey: "process.stages.debate",
  },
  synthesis: {
    icon: "📝",
    color: "indigo",
    labelKey: "process.stages.synthesis",
  }
};

function formatDuration(start?: string, end?: string): string | null {
  if (!start) return null;
  const startTime = new Date(start).getTime();
  const endTime = end ? new Date(end).getTime() : Date.now();
  const seconds = Math.round((endTime - startTime) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}m${remaining}s`;
}

function AgentWorkPanel({ agents, t }: { agents: AgentState[]; t: (key: string) => string }) {
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  if (agents.length === 0) return null;

  const completed = agents.filter((a) => a.status === "completed").length;
  const failed = agents.filter((a) => a.status === "failed").length;
  const total = agents.length;
  const totalItems = agents.reduce((sum, a) => sum + (a.count || 0), 0);

  return (
    <div className="mb-6 rounded-xl border border-[var(--card-border)] bg-[var(--card)] p-4">
      {/* Header with overall progress */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500/20 to-purple-500/20">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent)]">
              <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
              <path d="M16 3h-8l-2 4h12l-2-4z" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold">{t("agent.title")}</h3>
            <p className="text-xs text-[var(--muted)]">
              {completed + failed}/{t("common.completed")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 font-mono text-xs text-[var(--muted)]">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-[var(--accent-green)]" />
            {completed}/{total}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-[var(--accent)]" />
            {totalItems} {t("agent.collectedItems")}
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-[var(--background)]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-500"
          style={{ width: `${total > 0 ? ((completed + failed) / total) * 100 : 0}%` }}
        />
      </div>

      {/* Agent cards */}
      <div className="grid gap-2 sm:grid-cols-2">
        {agents.map((agent) => {
          const isExpanded = expandedAgent === agent.provider;
          return (
            <div key={agent.provider} className="overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--background)]/50">
              <button
                type="button"
                onClick={() => setExpandedAgent(isExpanded ? null : agent.provider)}
                className="flex w-full items-center gap-3 p-3 text-left transition-colors hover:bg-[var(--sidebar-accent)]/30"
              >
                {/* Agent icon */}
                <div
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-base ${
                    agent.status === "searching"
                      ? "bg-blue-500/10 motion-safe:animate-pulse"
                      : agent.status === "completed"
                        ? "bg-green-500/10"
                        : "bg-red-500/10"
                  }`}
                >
                  {agent.agent_icon || "🔍"}
                </div>

                {/* Agent info */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">{agent.agent_name}</span>
                    {agent.status === "searching" && (
                      <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-blue-500" />
                      </span>
                    )}
                  </div>
                  <p className="truncate text-xs text-[var(--muted)]">{agent.task_desc}</p>
                </div>

                {/* Status & count */}
                <div className="flex shrink-0 flex-col items-end gap-1">
                  {agent.status === "searching" && (
                    <span className="flex items-center gap-1 text-xs text-blue-500">
                      <span className="h-1.5 w-8 overflow-hidden rounded-full bg-blue-500/20">
                        <span className="block h-full w-1/2 animate-[slideRight_1.2s_ease-in-out_infinite] rounded-full bg-blue-500" />
                      </span>
                    </span>
                  )}
                  {agent.status === "completed" && (
                    <span className="text-xs text-green-500">✅ {agent.count || 0} {t("agent.collectedItems")}</span>
                  )}
                  {agent.status === "failed" && (
                    <span className="text-xs text-red-500">❌ {t("agent.failed")}</span>
                  )}
                  {agent.items_preview && agent.items_preview.length > 0 && (
                    <span className="text-[10px] text-[var(--muted)]">{t("agent.clickToExpand")}</span>
                  )}
                </div>
              </button>

              {/* Expanded items preview */}
              {isExpanded && agent.items_preview && agent.items_preview.length > 0 && (
                <div className="border-t border-[var(--card-border)] bg-[var(--background)]/80 px-3 py-2 animate-fadeIn">
                  <ul className="space-y-1">
                    {agent.items_preview.slice(0, 3).map((item, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs">
                        <span className="mt-0.5 text-[var(--accent)]">•</span>
                        <span className="line-clamp-2 text-[var(--muted-foreground)]">{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Expanded error */}
              {isExpanded && agent.status === "failed" && agent.error && (
                <div className="border-t border-red-500/20 bg-red-500/5 px-3 py-2 animate-fadeIn">
                  <p className="text-xs text-red-500">{agent.error}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ProcessVisualizer({
  steps,
  debateMessages,
  currentStage,
  isStreaming,
  agents = [],
}: ProcessVisualizerProps) {
  const { t } = useTranslation();
  const [expandedStep, setExpandedStep] = useState<string | null>(null);
  const [showModelOutput, setShowModelOutput] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [steps, debateMessages, agents]);

  const getStatusIcon = (status: ProcessStep["status"]) => {
    switch (status) {
      case "pending":
        return "⏳";
      case "running":
        return "🔄";
      case "completed":
        return "✅";
      case "error":
        return "❌";
    }
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.7) return "text-green-500";
    if (confidence >= 0.4) return "text-yellow-500";
    return "text-red-500";
  };

  return (
    <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-[var(--card-border)] bg-gradient-to-r from-blue-500/10 to-purple-500/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent)]">
                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                <path d="M2 17l10 5 10-5" />
                <path d="M2 12l10 5 10-5" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold">{t("process.analysisProcess")}</h3>
              <p className="text-xs text-[var(--muted)]">
                {isStreaming
                  ? `${t("common.processing")}: ${
                      stageConfig[currentStage as keyof typeof stageConfig]
                        ? t(stageConfig[currentStage as keyof typeof stageConfig].labelKey)
                        : currentStage
                    }`
                  : t("process.analysisComplete")}
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowModelOutput(!showModelOutput)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              showModelOutput
                ? "bg-[var(--accent)] text-[var(--accent-foreground)]"
                : "bg-[var(--background)] text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
          >
            {showModelOutput ? t("process.hide") : t("process.show")} {t("process.modelOutput")}
          </button>
        </div>
      </div>

      {/* Process Timeline */}
      <div ref={scrollRef} className="max-h-[600px] overflow-y-auto p-4 space-y-4">
        {/* Stage Progress Bar */}
        <div className="flex items-stretch gap-2 mb-6">
          {Object.entries(stageConfig).map(([stage, config]) => {
            const isActive = currentStage === stage;
            const stepForStage = steps.find((s) => s.stage === stage && s.status === "completed");
            const isCompleted = !!stepForStage;
            const isPending = !isActive && !isCompleted;
            const duration = stepForStage
              ? formatDuration(stepForStage.startTime, stepForStage.endTime)
              : isActive
                ? formatDuration(steps.find((s) => s.stage === stage)?.startTime)
                : null;

            return (
              <div key={stage} className="flex flex-1 flex-col items-center">
                <div
                  className={`h-2 w-full rounded-full transition-all duration-500 ${
                    isActive
                      ? "bg-gradient-to-r from-blue-500 to-purple-500 animate-pulse"
                      : isCompleted
                        ? "bg-[var(--accent-green)]"
                        : "bg-[var(--background)]"
                  }`}
                />
                <div className="mt-2 flex flex-col items-center">
                  <span className="text-lg">{config.icon}</span>
                  <p
                    className={`mt-1 text-xs ${
                      isActive
                        ? "font-semibold text-[var(--accent)]"
                        : isCompleted
                          ? "text-[var(--accent-green)]"
                          : "text-[var(--muted)]"
                    }`}
                  >
                    {t(config.labelKey)}
                  </p>
                  {isCompleted && duration && (
                    <span className="mt-0.5 text-[10px] text-[var(--muted)]">
                      ✅ {duration}
                    </span>
                  )}
                  {isActive && (
                    <span className="mt-0.5 text-[10px] text-[var(--accent)] animate-pulse">
                      ● {duration || "..."}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Agent Work Panel */}
        {agents.length > 0 && (
          <AgentWorkPanel agents={agents} t={t} />
        )}

        {/* Steps Timeline */}
        <div className="space-y-3">
          {steps.map((step, index) => {
            const config = stageConfig[step.stage] || stageConfig.ingest;
            const isExpanded = expandedStep === step.id;

            return (
              <div
                key={step.id}
                className={`relative border rounded-lg transition-all duration-300 ${
                  step.status === "running"
                    ? "border-[var(--accent)] bg-[var(--accent)]/5"
                    : step.status === "completed"
                      ? "border-[var(--accent-green)]/30 bg-[var(--accent-green)]/5"
                      : step.status === "error"
                        ? "border-[var(--accent-red)]/30 bg-[var(--accent-red)]/5"
                        : "border-[var(--card-border)]"
                }`}
              >
                {/* Step Header */}
                <button
                  onClick={() => setExpandedStep(isExpanded ? null : step.id)}
                  className="w-full p-4 text-left"
                >
                  <div className="flex items-start gap-3">
                    {/* Timeline dot */}
                    <div className="flex flex-col items-center">
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center text-sm ${
                          step.status === "running"
                            ? "bg-[var(--accent)] text-[var(--accent-foreground)] animate-pulse"
                            : step.status === "completed"
                              ? "bg-[var(--accent-green)] text-[var(--accent-foreground)]"
                              : step.status === "error"
                                ? "bg-[var(--accent-red)] text-[var(--accent-foreground)]"
                                : "bg-[var(--background)] text-[var(--muted)]"
                        }`}
                      >
                        {getStatusIcon(step.status)}
                      </div>
                      {index < steps.length - 1 && (
                        <div className={`w-0.5 h-full mt-1 ${
                          step.status === "completed" ? "bg-[var(--accent-green)]" : "bg-[var(--card-border)]"
                        }`} />
                      )}
                    </div>

                    {/* Step content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-lg">{config.icon}</span>
                        <span className="font-medium text-sm">{step.title}</span>
                        <span className="text-xs text-[var(--muted)]">•</span>
                        <span className="text-xs text-[var(--muted)]">{t(config.labelKey)}</span>
                        {step.timestamp && (
                          <>
                            <span className="text-xs text-[var(--muted)]">•</span>
                            <span className="text-xs text-[var(--muted)]">{step.timestamp}</span>
                          </>
                        )}
                        {step.status === "completed" && step.startTime && step.endTime && (
                          <>
                            <span className="text-xs text-[var(--muted)]">•</span>
                            <span className="text-xs text-[var(--accent-green)]">
                              ✅ {formatDuration(step.startTime, step.endTime)}
                            </span>
                          </>
                        )}
                      </div>
                      <p className="text-sm text-[var(--muted)]">{step.description}</p>

                      {/* Details preview */}
                      {step.details && step.details.length > 0 && (
                        <div className="mt-2">
                          <span className="text-xs text-[var(--accent)]">
                            {isExpanded ? "▼" : "▶"} {step.details.length} {t("process.details")}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </button>

                {/* Expanded details */}
                {isExpanded && step.details && (
                  <div className="px-4 pb-4 pl-15 animate-fadeIn">
                    <div className="bg-[var(--background)] rounded-lg p-3 space-y-2">
                      {step.details.map((detail, i) => (
                        <div key={i} className="flex items-start gap-2">
                          <span className="text-[var(--accent)] mt-1">•</span>
                          <span className="text-xs">{detail}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Model output (collapsible) */}
                {showModelOutput && step.modelOutput && (
                  <div className="px-4 pb-4 pl-15">
                    <div className="bg-gradient-to-r from-purple-500/10 to-blue-500/10 border border-purple-500/20 rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-purple-500">
                          <path d="M12 2L2 7l10 5 10-5-10-5z" />
                        </svg>
                        <span className="text-xs font-medium text-purple-500">{t("process.modelOutput")}</span>
                      </div>
                      <pre className="text-xs font-mono whitespace-pre-wrap text-[var(--muted)]">
                        {step.modelOutput}
                      </pre>
                    </div>
                  </div>
                )}

                {/* Sources */}
                {step.sources && step.sources.length > 0 && isExpanded && (
                  <div className="px-4 pb-4 pl-15">
                    <div className="space-y-2">
                      <span className="text-xs text-[var(--muted)]">{t("process.sources")}:</span>
                      {step.sources.map((source, i) => (
                        <a
                          key={i}
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-2 p-2 rounded bg-[var(--background)] hover:bg-[var(--card-hover)] transition-colors"
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                            <polyline points="15 3 21 3 21 9" />
                            <line x1="10" y1="14" x2="21" y2="3" />
                          </svg>
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-medium truncate">{source.title}</div>
                            {source.snippet && (
                              <div className="text-xs text-[var(--muted)] truncate">{source.snippet}</div>
                            )}
                          </div>
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Debate Section */}
        {debateMessages.length > 0 && (
          <div className="mt-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-red-500/20 to-orange-500/20 flex items-center justify-center">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-red-500">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <div>
                <h4 className="font-medium text-sm">{t("process.multiAgentDebate")}</h4>
                <p className="text-xs text-[var(--muted)]">{t("process.debateDescription")}</p>
              </div>
            </div>

            <div className="space-y-3">
              {debateMessages.map((msg, index) => {
                const roleConfig = {
                  advocate: {
                    icon: "🟢",
                    color: "green",
                    label: t("assistant.roleAdvocate"),
                    description: t("process.roleDescriptions.advocate")
                  },
                  challenger: {
                    icon: "🔴",
                    color: "red",
                    label: t("assistant.roleChallenger"),
                    description: t("process.roleDescriptions.challenger")
                  },
                  arbitrator: {
                    icon: "🟣",
                    color: "purple",
                    label: t("assistant.roleArbitrator"),
                    description: t("process.roleDescriptions.arbitrator")
                  }
                };

                const config = roleConfig[msg.role];

                return (
                  <div
                    key={index}
                    className={`border-l-4 border-${config.color}-500 bg-${config.color}-500/5 rounded-r-lg p-4 animate-slideIn`}
                    style={{ animationDelay: `${index * 100}ms` }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{config.icon}</span>
                        <div>
                          <span className="font-medium text-sm">{config.label}</span>
                          <span className="text-xs text-[var(--muted)] ml-2">{t("process.round")} {msg.round}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-[var(--muted)]">{t("process.confidence")}:</span>
                        <span className={`text-sm font-medium ${getConfidenceColor(msg.confidence)}`}>
                          {(msg.confidence * 100).toFixed(0)}%
                        </span>
                        <div className="w-16 h-1.5 bg-[var(--background)] rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              msg.confidence > 0.7
                                ? "bg-[var(--accent-green)]"
                                : msg.confidence > 0.4
                                  ? "bg-[var(--accent-yellow)]"
                                  : "bg-[var(--accent-red)]"
                            }`}
                            style={{ width: `${msg.confidence * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>

                    <p className="text-sm mb-3">{msg.content}</p>

                    {/* Arguments */}
                    {msg.arguments.length > 0 && (
                      <div className="space-y-1 mb-2">
                        <span className="text-xs text-[var(--muted)]">{t("process.arguments")}:</span>
                        {msg.arguments.map((arg, i) => (
                          <div key={i} className="flex items-start gap-2 text-xs">
                            <span className="text-[var(--accent)]">•</span>
                            <span>{arg}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Rebuttals */}
                    {msg.rebuttals && msg.rebuttals.length > 0 && (
                      <div className="space-y-1">
                        <span className="text-xs text-[var(--muted)]">{t("process.rebuttals")}:</span>
                        {msg.rebuttals.map((rebuttal, i) => (
                          <div key={i} className="flex items-start gap-2 text-xs">
                            <span className="text-red-500">•</span>
                            <span>{rebuttal}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Loading indicator */}
        {isStreaming && (
          <div className="flex items-center justify-center gap-3 p-4 bg-[var(--background)] rounded-lg">
            <div className="flex space-x-1">
              <div className="w-2 h-2 bg-[var(--accent)] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
              <div className="w-2 h-2 bg-[var(--accent)] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
              <div className="w-2 h-2 bg-[var(--accent)] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
            <span className="text-sm text-[var(--muted)]">{t("process.processingAnalysis")}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// Helper function to convert API events to process steps
export function eventsToProcessSteps(events: Array<{ event: string; payload: any }>): ProcessStep[] {
  const steps: ProcessStep[] = [];

  events.forEach((event, index) => {
    if (event.event === "step") {
      const step = event.payload as any;
      steps.push({
        id: `step-${index}`,
        stage: step.stage || "analyze",
        title: step.message || "Processing",
        description: step.detail || "",
        details: step.detail ? [step.detail] : undefined,
        status: "completed",
        timestamp: new Date().toLocaleTimeString(),
        startTime: step.startTime,
        endTime: step.endTime,
      });
    } else if (event.event === "source") {
      const source = event.payload as any;
      // Add source to the last step
      if (steps.length > 0) {
        const lastStep = steps[steps.length - 1];
        if (!lastStep.sources) lastStep.sources = [];
        lastStep.sources.push({
          title: source.title,
          url: source.url,
          snippet: source.summary
        });
      }
    }
  });

  return steps;
}

// Helper function to convert debate rounds to debate messages
export function debateRoundsToMessages(rounds: Array<any>): DebateMessage[] {
  return rounds.map((round, index) => ({
    role: round.role as "advocate" | "challenger" | "arbitrator",
    round: round.round_number || index + 1,
    content: round.position || "",
    confidence: round.confidence || 0.5,
    arguments: round.arguments?.map((a: any) => a.content || a) || [],
    rebuttals: round.rebuttals?.map((r: any) => r.content || r) || []
  }));
}
