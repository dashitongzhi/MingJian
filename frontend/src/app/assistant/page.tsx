"use client";
import { useCallback, useRef, useState } from "react";
import useSWR from "swr";
import { fetchSessions, streamAssistant, type AssistantEvent, type AssistantResult, type AnalysisStep, type PanelMessage, type DebateRound } from "@/lib/api";

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

  const handleRun = useCallback(async () => {
    if (!topic.trim()) return;
    setStreaming(true); setError(null); setSteps([]); setSources([]); setDiscussions([]); setDebateRounds([]); setResult(null);
    const ctrl = new AbortController(); abortRef.current = ctrl;
    try {
      await streamAssistant({ topic, domain_id: domainId, subject_name: subjectName || topic.slice(0, 50), tick_count: tickCount }, (evt) => {
        if (evt.event === "step") setSteps((p) => [...p, evt.payload as AnalysisStep]);
        else if (evt.event === "source") setSources((p) => [...p, evt.payload as { title: string; url: string }]);
        else if (evt.event === "discussion") setDiscussions((p) => [...p, evt.payload as PanelMessage]);
        else if (evt.event === "debate_round") setDebateRounds((p) => [...p, evt.payload as DebateRound]);
        else if (evt.event === "assistant_result") setResult(evt.payload as AssistantResult);
      }, ctrl.signal);
      refreshSessions();
    } catch (err: unknown) { if (err instanceof Error && err.name !== "AbortError") setError(err.message); }
    finally { setStreaming(false); }
  }, [topic, domainId, subjectName, tickCount, refreshSessions]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr_360px] gap-6">
      <div className="space-y-4">
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4 space-y-3">
          <h2 className="text-sm font-semibold">Mission Input</h2>
          <textarea className="w-full bg-[var(--background)] border border-[var(--card-border)] rounded p-2 text-sm h-24 resize-none focus:border-[var(--accent)] outline-none" placeholder="Enter topic..." value={topic} onChange={(e) => setTopic(e.target.value)} />
          <select className="w-full bg-[var(--background)] border border-[var(--card-border)] rounded p-2 text-sm" value={domainId} onChange={(e) => setDomainId(e.target.value)}>
            <option value="auto">Auto-detect</option><option value="corporate">Corporate</option><option value="military">Military</option>
          </select>
          <input className="w-full bg-[var(--background)] border border-[var(--card-border)] rounded p-2 text-sm" placeholder="Subject name" value={subjectName} onChange={(e) => setSubjectName(e.target.value)} />
          <div><label className="text-xs text-[var(--muted)]">Ticks: {tickCount}</label><input type="range" min={2} max={12} value={tickCount} onChange={(e) => setTickCount(Number(e.target.value))} className="w-full" /></div>
          <button onClick={handleRun} disabled={streaming || !topic.trim()} className="w-full bg-[var(--accent)] text-white rounded py-2 text-sm font-medium disabled:opacity-40">{streaming ? "Running..." : "Run Analysis"}</button>
          {streaming && <button onClick={() => abortRef.current?.abort()} className="w-full bg-[var(--accent-red)] text-white rounded py-2 text-sm">Cancel</button>}
          {error && <div className="text-xs text-[var(--accent-red)]">{error}</div>}
        </div>
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4"><h2 className="text-sm font-semibold mb-2">Sessions</h2>
          <div className="space-y-1 max-h-60 overflow-y-auto">{sessions?.map((s) => <div key={s.id} className="text-xs p-2 rounded hover:bg-[var(--background)]"><div className="font-medium">{s.name || s.topic.slice(0, 40)}</div><div className="text-[var(--muted)]">{s.domain_id}</div></div>)}</div>
        </div>
      </div>
      <div className="space-y-4">
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4"><h2 className="text-sm font-semibold mb-2">Live Reasoning</h2>
          <div className="space-y-1 max-h-64 overflow-y-auto">{steps.map((s, i) => <div key={i} className="text-xs py-1 border-b border-[var(--card-border)] last:border-0"><span className="text-[var(--accent)] font-mono mr-2">[{s.stage}]</span>{s.message}</div>)}{steps.length === 0 && !streaming && <div className="text-xs text-[var(--muted)]">Run an analysis to see reasoning steps</div>}</div>
        </div>
        {sources.length > 0 && <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4"><h2 className="text-sm font-semibold mb-2">Sources ({sources.length})</h2><div className="space-y-1 max-h-40 overflow-y-auto">{sources.map((s, i) => <a key={i} href={s.url} target="_blank" rel="noopener noreferrer" className="block text-xs text-[var(--accent)] hover:underline truncate">{s.title}</a>)}</div></div>}
        {result && <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4 space-y-3"><h2 className="text-sm font-semibold">Result</h2><div className="text-sm">{result.analysis.summary}</div>
          {result.analysis.findings.length > 0 && <div><div className="text-xs text-[var(--muted)] mb-1">Findings</div><ul className="list-disc list-inside text-xs space-y-1">{result.analysis.findings.map((f, i) => <li key={i}>{f}</li>)}</ul></div>}
          {result.simulation_run && <div className="text-xs"><span className="text-[var(--muted)]">Simulation: </span><span className="font-mono">{result.simulation_run.id.slice(0, 8)}</span> <span className="text-[var(--muted)]">— {result.simulation_run.status}</span></div>}
          {result.debate?.verdict && <div className="text-xs"><span className="text-[var(--muted)]">Debate: </span><span className={result.debate.verdict.verdict === "support" ? "text-[var(--accent-green)]" : "text-[var(--accent-red)]"}>{result.debate.verdict.verdict}</span> <span className="text-[var(--muted)]">({(result.debate.verdict.confidence * 100).toFixed(0)}%)</span></div>}
        </div>}
      </div>
      <div className="space-y-4">
        {discussions.length > 0 && <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4"><h2 className="text-sm font-semibold mb-2">Panel Discussion</h2><div className="space-y-3">{discussions.map((d, i) => <div key={i} className="border border-[var(--card-border)] rounded p-3"><div className="flex justify-between mb-1"><span className="text-xs font-medium">{d.label}</span><span className={`text-xs px-2 py-0.5 rounded ${d.stance === "support" ? "bg-[var(--accent-green)]/20 text-[var(--accent-green)]" : d.stance === "challenge" ? "bg-[var(--accent-red)]/20 text-[var(--accent-red)]" : "bg-[var(--accent-yellow)]/20 text-[var(--accent-yellow)]"}`}>{d.stance}</span></div><div className="text-xs">{d.summary}</div>{d.recommendation && <div className="text-xs text-[var(--accent)] mt-1">{"→"} {d.recommendation}</div>}</div>)}</div></div>}
        {debateRounds.length > 0 && <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4"><h2 className="text-sm font-semibold mb-2">Debate Trace</h2><div className="space-y-2">{debateRounds.map((r, i) => <div key={i} className="border-l-2 border-[var(--card-border)] pl-3 py-1"><div className="flex justify-between"><span className="text-xs font-medium capitalize">{r.role} {"—"} R{r.round_number}</span><span className="text-xs text-[var(--muted)]">{(r.confidence * 100).toFixed(0)}%</span></div><div className="text-xs text-[var(--muted)]">{r.position}</div></div>)}</div></div>}
      </div>
    </div>
  );
}
