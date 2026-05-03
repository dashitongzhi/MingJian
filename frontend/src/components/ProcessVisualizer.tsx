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

interface ProcessVisualizerProps {
  steps: ProcessStep[];
  debateMessages: DebateMessage[];
  currentStage: string;
  isStreaming: boolean;
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

export function ProcessVisualizer({
  steps,
  debateMessages,
  currentStage,
  isStreaming
}: ProcessVisualizerProps) {
  const { t } = useTranslation();
  const [expandedStep, setExpandedStep] = useState<string | null>(null);
  const [showModelOutput, setShowModelOutput] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [steps, debateMessages]);

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
        <div className="flex items-center gap-2 mb-6">
          {Object.entries(stageConfig).map(([stage, config], index) => {
            const isActive = currentStage === stage;
            const isCompleted = steps.some(s => s.stage === stage && s.status === "completed");
            const isPending = !isActive && !isCompleted;

            return (
              <div key={stage} className="flex-1">
                <div
                  className={`h-2 rounded-full transition-all duration-500 ${
                    isActive
                      ? "bg-gradient-to-r from-blue-500 to-purple-500 animate-pulse"
                      : isCompleted
                        ? "bg-[var(--accent-green)]"
                        : "bg-[var(--background)]"
                  }`}
                />
                <div className="mt-2 text-center">
                  <span className="text-lg">{config.icon}</span>
                  <p className={`text-xs mt-1 ${isActive ? "text-[var(--accent)] font-medium" : "text-[var(--muted)]"}`}>
                    {t(config.labelKey)}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

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
        timestamp: new Date().toLocaleTimeString()
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
