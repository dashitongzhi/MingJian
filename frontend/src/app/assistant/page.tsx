"use client";
import { useCallback, useRef, useState } from "react";
import useSWR from "swr";
import { fetchSessions, streamAssistant, type AssistantEvent, type AssistantResult, type AnalysisStep, type PanelMessage, type DebateRound } from "@/lib/api";

function StepIndicator({ step, index }: { step: AnalysisStep; index: number }) {
  const stageColors: Record<string, string> = {
    ingest: "bg-blue-500",
    extract: "bg-purple-500",
    analyze: "bg-yellow-500",
    simulate: "bg-green-500",
    debate: "bg-red-500",
    default: "bg-gray-500",
  };

  return (
    <div className="flex items-start gap-3 animate-slideIn">
      <div className="flex flex-col items-center">
        <div className={`w-2 h-2 rounded-full ${stageColors[step.stage] || stageColors.default} mt-2`} />
        {index > 0 && <div className="w-0.5 h-full bg-[var(--card-border)] mt-1" />}
      </div>
      <div className="flex-1 pb-4">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-[var(--accent)] uppercase">{step.stage}</span>
          <span className="text-xs text-[var(--muted)]">•</span>
          <span className="text-xs text-[var(--muted)]">Step {index + 1}</span>
        </div>
        <p className="text-sm mt-1">{step.message}</p>
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
      className="flex items-center gap-3 p-3 rounded-lg border border-[var(--card-border)] hover:border-[var(--accent)] hover:bg-[var(--card-hover)] transition-all animate-fadeIn"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <div className="w-8 h-8 rounded bg-[var(--background)] flex items-center justify-center text-[var(--muted)] flex-shrink-0">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
          <polyline points="15 3 21 3 21 9" />
          <line x1="10" y1="14" x2="21" y2="3" />
        </svg>
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{source.title}</div>
        <div className="text-xs text-[var(--muted)] truncate">{source.url}</div>
      </div>
    </a>
  );
}

function PanelMessageCard({ msg }: { msg: PanelMessage }) {
  const stanceColors: Record<string, { bg: string; text: string; border: string }> = {
    support: { bg: "bg-[var(--accent-green-bg)]", text: "text-[var(--accent-green)]", border: "border-[var(--accent-green)]" },
    challenge: { bg: "bg-[var(--accent-red-bg)]", text: "text-[var(--accent-red)]", border: "border-[var(--accent-red)]" },
    neutral: { bg: "bg-[var(--accent-yellow-bg)]", text: "text-[var(--accent-yellow)]", border: "border-[var(--accent-yellow)]" },
  };

  const style = stanceColors[msg.stance] || stanceColors.neutral;

  return (
    <div className={`p-4 rounded-lg border ${style.border} ${style.bg} animate-fadeIn`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium">{msg.label}</span>
        <span className={`badge ${style.bg} ${style.text}`}>{msg.stance}</span>
      </div>
      <p className="text-sm">{msg.summary}</p>
      {msg.recommendation && (
        <div className="mt-3 pt-3 border-t border-[var(--card-border)]">
          <div className="text-xs text-[var(--muted)] mb-1">Recommendation</div>
          <p className="text-sm text-[var(--accent)]">→ {msg.recommendation}</p>
        </div>
      )}
    </div>
  );
}

function DebateRoundCard({ round }: { round: DebateRound }) {
  const roleColors: Record<string, string> = {
    advocate: "border-[var(--accent-green)]",
    challenger: "border-[var(--accent-red)]",
    arbitrator: "border-[var(--accent-purple)]",
  };

  return (
    <div className={`p-4 rounded-lg border-l-4 ${roleColors[round.role] || "border-[var(--card-border)]"} bg-[var(--card)] animate-slideIn`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium capitalize">{round.role}</span>
          <span className="text-xs text-[var(--muted)]">Round {round.round_number}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-16 h-1.5 bg-[var(--background)] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${round.confidence > 0.7 ? "bg-[var(--accent-green)]" : round.confidence > 0.4 ? "bg-[var(--accent-yellow)]" : "bg-[var(--accent-red)]"}`}
              style={{ width: `${round.confidence * 100}%` }}
            />
          </div>
          <span className="text-xs text-[var(--muted)]">{(round.confidence * 100).toFixed(0)}%</span>
        </div>
      </div>
      <p className="text-sm text-[var(--muted-foreground)]">{round.position}</p>
    </div>
  );
}

export default function AssistantPage() {
  const { data: sessions, mutate: refreshSessions } = useSWR("sessions", fetchSessions);
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
  const [activeTab, setActiveTab] = useState<"reasoning" | "sources" | "panel" | "debate">("reasoning");

  const handleRun = useCallback(async () => {
    if (!topic.trim()) return;
    setStreaming(true);
    setError(null);
    setSteps([]);
    setSources([]);
    setDiscussions([]);
    setDebateRounds([]);
    setResult(null);
    setActiveTab("reasoning");
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await streamAssistant(
        { topic, domain_id: domainId, subject_name: subjectName || topic.slice(0, 50), tick_count: tickCount },
        (evt) => {
          if (evt.event === "step") {
            setSteps((p) => [...p, evt.payload as AnalysisStep]);
            setActiveTab("reasoning");
          } else if (evt.event === "source") {
            setSources((p) => [...p, evt.payload as { title: string; url: string }]);
          } else if (evt.event === "discussion") {
            setDiscussions((p) => [...p, evt.payload as PanelMessage]);
            setActiveTab("panel");
          } else if (evt.event === "debate_round") {
            setDebateRounds((p) => [...p, evt.payload as DebateRound]);
            setActiveTab("debate");
          } else if (evt.event === "assistant_result") {
            setResult(evt.payload as AssistantResult);
          }
        },
        ctrl.signal
      );
      refreshSessions();
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== "AbortError") setError(err.message);
    } finally {
      setStreaming(false);
    }
  }, [topic, domainId, subjectName, tickCount, refreshSessions]);

  const tabs = [
    { id: "reasoning" as const, label: "Reasoning", count: steps.length },
    { id: "sources" as const, label: "Sources", count: sources.length },
    { id: "panel" as const, label: "Panel", count: discussions.length },
    { id: "debate" as const, label: "Debate", count: debateRounds.length },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Strategic Assistant</h1>
        <p className="text-[var(--muted)] mt-1">AI-powered analysis with multi-agent debate and evidence synthesis</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6">
        {/* Left panel - Input */}
        <div className="space-y-4">
          {/* Input card */}
          <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
              </svg>
              Mission Input
            </h2>
            <textarea
              className="input min-h-[120px] resize-none"
              placeholder="Enter your analysis topic..."
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-[var(--muted)] mb-1 block">Domain</label>
                <select className="input select" value={domainId} onChange={(e) => setDomainId(e.target.value)}>
                  <option value="auto">Auto-detect</option>
                  <option value="corporate">Corporate</option>
                  <option value="military">Military</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-[var(--muted)] mb-1 block">Ticks</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={2}
                    max={12}
                    value={tickCount}
                    onChange={(e) => setTickCount(Number(e.target.value))}
                    className="flex-1"
                  />
                  <span className="text-sm font-mono w-8 text-center">{tickCount}</span>
                </div>
              </div>
            </div>
            <div>
              <label className="text-xs text-[var(--muted)] mb-1 block">Subject Name</label>
              <input className="input" placeholder="Optional subject name" value={subjectName} onChange={(e) => setSubjectName(e.target.value)} />
            </div>
            <div className="flex gap-3">
              <button onClick={handleRun} disabled={streaming || !topic.trim()} className="btn btn-primary flex-1">
                {streaming ? (
                  <>
                    <div className="spinner" />
                    Running...
                  </>
                ) : (
                  <>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polygon points="5 3 19 12 5 21 5 3" />
                    </svg>
                    Run Analysis
                  </>
                )}
              </button>
              {streaming && (
                <button onClick={() => abortRef.current?.abort()} className="btn btn-danger">
                  Cancel
                </button>
              )}
            </div>
            {error && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-[var(--accent-red-bg)] text-[var(--accent-red)] text-sm">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="15" y1="9" x2="9" y2="15" />
                  <line x1="9" y1="9" x2="15" y2="15" />
                </svg>
                {error}
              </div>
            )}
          </div>

          {/* Sessions list */}
          <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
            <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 8v4l3 3" />
                <circle cx="12" cy="12" r="10" />
              </svg>
              Recent Sessions
            </h2>
            <div className="space-y-2 max-h-[300px] overflow-y-auto">
              {sessions?.map((s) => (
                <div key={s.id} className="p-3 rounded-lg hover:bg-[var(--card-hover)] transition-colors cursor-pointer">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium truncate">{s.name || s.topic.slice(0, 40)}</div>
                    <span className={`badge ${s.auto_refresh_enabled ? "badge-success" : "badge-warning"}`}>
                      {s.auto_refresh_enabled ? "Auto" : "Manual"}
                    </span>
                  </div>
                  <div className="text-xs text-[var(--muted)] mt-1">{s.domain_id}</div>
                </div>
              ))}
              {(!sessions || sessions.length === 0) && (
                <div className="text-sm text-[var(--muted)] text-center py-4">No sessions yet</div>
              )}
            </div>
          </div>
        </div>

        {/* Right panel - Results */}
        <div className="space-y-4">
          {/* Tabs */}
          <div className="flex items-center gap-1 p-1 bg-[var(--card)] rounded-xl border border-[var(--card-border)]">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  activeTab === tab.id
                    ? "bg-[var(--accent)] text-white"
                    : "text-[var(--muted)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
                }`}
              >
                {tab.label}
                {tab.count > 0 && (
                  <span className={`text-xs px-1.5 py-0.5 rounded-full ${activeTab === tab.id ? "bg-white/20" : "bg-[var(--background)]"}`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5 min-h-[500px]">
            {activeTab === "reasoning" && (
              <div>
                <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2L2 7l10 5 10-5-10-5z" />
                    <path d="M2 17l10 5 10-5" />
                    <path d="M2 12l10 5 10-5" />
                  </svg>
                  Live Reasoning
                </h3>
                {steps.length > 0 ? (
                  <div className="space-y-0">
                    {steps.map((s, i) => (
                      <StepIndicator key={i} step={s} index={i} />
                    ))}
                  </div>
                ) : (
                  <div className="empty-state py-12">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                      <path d="M12 2L2 7l10 5 10-5-10-5z" />
                      <path d="M2 17l10 5 10-5" />
                      <path d="M2 12l10 5 10-5" />
                    </svg>
                    <div className="empty-state-title">Waiting for analysis</div>
                    <div className="empty-state-description">Run an analysis to see the AI reasoning process in real-time</div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "sources" && (
              <div>
                <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                    <polyline points="15 3 21 3 21 9" />
                    <line x1="10" y1="14" x2="21" y2="3" />
                  </svg>
                  Sources ({sources.length})
                </h3>
                {sources.length > 0 ? (
                  <div className="space-y-2">
                    {sources.map((s, i) => (
                      <SourceCard key={i} source={s} index={i} />
                    ))}
                  </div>
                ) : (
                  <div className="empty-state py-12">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
                    <div className="empty-state-title">No sources yet</div>
                    <div className="empty-state-description">Sources will appear here as the AI gathers evidence</div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "panel" && (
              <div>
                <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                    <circle cx="9" cy="7" r="4" />
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                  </svg>
                  Panel Discussion ({discussions.length})
                </h3>
                {discussions.length > 0 ? (
                  <div className="space-y-3">
                    {discussions.map((d, i) => (
                      <PanelMessageCard key={i} msg={d} />
                    ))}
                  </div>
                ) : (
                  <div className="empty-state py-12">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                      <circle cx="9" cy="7" r="4" />
                      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                    </svg>
                    <div className="empty-state-title">No panel discussion yet</div>
                    <div className="empty-state-description">Panel members will discuss findings during analysis</div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "debate" && (
              <div>
                <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                  Debate Trace ({debateRounds.length})
                </h3>
                {debateRounds.length > 0 ? (
                  <div className="space-y-3">
                    {debateRounds.map((r, i) => (
                      <DebateRoundCard key={i} round={r} />
                    ))}
                  </div>
                ) : (
                  <div className="empty-state py-12">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                    <div className="empty-state-title">No debate yet</div>
                    <div className="empty-state-description">Debate rounds will appear when AI models discuss the analysis</div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Result summary */}
          {result && (
            <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5 space-y-4 animate-fadeIn">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                Analysis Complete
              </h3>
              <p className="text-sm">{result.analysis.summary}</p>
              {result.analysis.findings.length > 0 && (
                <div>
                  <div className="text-xs text-[var(--muted)] mb-2">Key Findings</div>
                  <ul className="space-y-2">
                    {result.analysis.findings.map((f, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent-green)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 flex-shrink-0">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex items-center gap-4 pt-3 border-t border-[var(--card-border)]">
                {result.simulation_run && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[var(--muted)]">Simulation:</span>
                    <span className="text-xs font-mono">{result.simulation_run.id.slice(0, 8)}</span>
                    <span className={`badge ${result.simulation_run.status === "completed" ? "badge-success" : "badge-warning"}`}>
                      {result.simulation_run.status}
                    </span>
                  </div>
                )}
                {result.debate?.verdict && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[var(--muted)]">Verdict:</span>
                    <span className={`badge ${result.debate.verdict.verdict === "support" ? "badge-success" : "badge-error"}`}>
                      {result.debate.verdict.verdict}
                    </span>
                    <span className="text-xs text-[var(--muted)]">{(result.debate.verdict.confidence * 100).toFixed(0)}%</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}