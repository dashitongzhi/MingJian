"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import {
  fetchSessionDetail,
  fetchSessions,
  streamAssistant,
  type AnalysisStep,
  type AssistantResult,
  type DebateRound,
  type DebateVerdict,
  type PanelMessage,
} from "@/lib/api";
import type { DebateMessage, ProcessStep } from "@/components/ProcessVisualizer";
import { useTranslation } from "@/contexts/LanguageContext";
import { toast } from "@/lib/toast";

export type SourceSearchState = {
  provider: string;
  label: string;
  status: "searching" | "completed" | "failed";
  count?: number;
  error?: string;
  icon?: string;
  itemsPreview?: string[];
};

export type AssistantRunParams = {
  topic: string;
  domain_id: string;
  subject_name: string;
  tick_count: number;
  session_name?: string;
};

export type CurrentDebateRound = {
  round_number: number;
  role: string;
} | null;

export function useAssistantController() {
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


  const handleReanalyze = useCallback(() => {
    const params = lastRunParamsRef.current;
    if (params) handleRun(params);
  }, [handleRun]);

  return {
    abortRef,
    activeTab,
    currentDebateRound,
    currentStage,
    debateMessages,
    debateRounds,
    debateStatus,
    debateVerdict,
    discussions,
    domainId,
    error,
    guideStep,
    handleExport,
    handleReanalyze,
    handleRun,
    processSteps,
    result,
    selectedSessionId,
    sessionDetail,
    sessionDetailLoading,
    sessions,
    sessionsError,
    setActiveTab,
    setDomainId,
    setGuideStep,
    setSelectedSessionId,
    setShowGuide,
    setSubjectName,
    setTickCount,
    setTopic,
    showGuide,
    sourceSearches,
    sources,
    steps,
    streaming,
    subjectName,
    tabs,
    tickCount,
    topic,
  };
}

export type AssistantController = ReturnType<typeof useAssistantController>;
