const API = process.env.NEXT_PUBLIC_API_URL || "/api";

export async function fetch_<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json", ...init?.headers }, ...init });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text().catch(() => "")}`);
  return res.json();
}

export const apiFetch = fetch_;

export interface AnalysisSource { source_type: string; title: string; url: string; summary: string; published_at: string | null }
export interface AnalysisStep { stage: string; message: string; detail: string | null }
export interface AnalysisResponse { query: string; domain_id: string; summary: string; reasoning_steps: AnalysisStep[]; findings: string[]; recommendations: string[]; sources: AnalysisSource[]; generated_at: string }
export interface IngestRun { id: string; status: string; source_types: string[]; summary: Record<string, number>; created_at: string }
export interface SimulationRun { id: string; domain_id: string; actor_template: string; status: string; tick_count: number; summary: Record<string, unknown>; created_at: string; military_use_mode: string | null }
export interface DebateRound { round_number: number; role: string; position: string; confidence: number; arguments: Record<string, unknown>[]; rebuttals: Record<string, unknown>[]; concessions: Record<string, unknown>[] }
export interface DebateVerdict { verdict: string; confidence: number; winning_arguments: string[]; decisive_evidence: string[]; minority_opinion: string | null }
export interface DebateDetail { id: string; topic: string; trigger_type: string; status: string; rounds: DebateRound[]; verdict: DebateVerdict | null; created_at: string }
export interface PanelMessage { participant_id: string; label: string; model_target: string; stance: "support" | "challenge" | "monitor"; summary: string; key_points: string[]; recommendation: string; confidence: number }
export interface StrategicSession { id: string; name: string; topic: string; domain_id: string; subject_name: string | null; auto_refresh_enabled: boolean; latest_brief_summary: string | null; latest_run_summary: string | null; created_at: string }
export interface StrategicSessionDetail { session: StrategicSession; daily_briefs: Array<{ id: string; summary: string; generated_at: string }>; recent_runs: Array<{ id: string; result: AssistantResult; generated_at: string }> }
export interface KPIMetric { metric: string; start: number | null; end: number | null; delta: number | null }
export interface WorkbenchData { run_id: string; domain_id: string; timeline: Array<{ event_id: string; event_type: string; tick: number | null; title: string }>; geo_map: { theater: string | null; assets: Array<{ name: string; asset_type: string; latitude: number; longitude: number }> }; kpi_comparator: { metrics: KPIMetric[] }; debate_records: Array<{ debate_id: string; topic: string; verdict: string | null; confidence: number | null }> }
export interface GeneratedReport { id: string; title: string; summary: string }
export interface AssistantResult { session_id: string | null; topic: string; domain_id: string; subject_name: string; analysis: AnalysisResponse; ingest_run: IngestRun; simulation_run: SimulationRun; latest_report: GeneratedReport | null; debate: DebateDetail | null; workbench: WorkbenchData; panel_discussion: PanelMessage[]; generated_at: string }
export interface PredictionScoreboard { total_hypotheses: number; confirmed: number; refuted: number; pending: number; accuracy: number; brier_score: number | null; human_baseline_accuracy: number | null; lift_over_human_baseline: number | null }
export interface SourceReputation { source_key: string; source_type: string | null; display_name: string | null; domain_id: string; confirmed_count: number; refuted_count: number; reputation_score: number; noise_rate: number }
export interface WatchRule { id: string; name: string; domain_id: string; query: string; enabled: boolean; poll_interval_minutes: number; auto_trigger_simulation: boolean; created_at: string }
export interface RuntimeQueueHealth { queues: Array<{ queue: string; pending: number; processing: number; completed: number; failed: number }>; dead_letter_count: number }

export const fetchHealth = () => fetch_<{ status: string }>("/health");
export const fetchSessions = () => fetch_<StrategicSession[]>("/assistant/sessions");
export const fetchSessionDetail = (id: string) => fetch_<StrategicSessionDetail>(`/assistant/sessions/${id}`);
export const fetchSimulationRuns = (limit = 20) => fetch_<SimulationRun[]>(`/simulation/runs?limit=${limit}`);
export const fetchWorkbench = (runId: string) => fetch_<WorkbenchData>(`/runs/${runId}/workbench`);
export const createSimulationRun = (data: Record<string, unknown>) => fetch_<SimulationRun>("/simulation/runs", { method: "POST", body: JSON.stringify(data) });
export const fetchDebateDetail = (id: string) => fetch_<DebateDetail>(`/debates/${id}`);
export const fetchEvidence = (limit = 50) => fetch_<Array<{ id: string; title: string; summary: string; confidence: number; created_at: string }>>(`/evidence?limit=${limit}`);
export const fetchClaims = (limit = 50) => fetch_<Array<{ id: string; statement: string; confidence: number; status: string }>>(`/claims?limit=${limit}`);
export const fetchKnowledgeGraph = (limit = 100) => fetch_<{ nodes: Array<{ node_id: string; label: string; node_type: string }>; edges: Array<{ source_id: string; target_id: string; relation_type: string }> }>(`/knowledge/graph?limit=${limit}`);
export const searchKnowledge = (q: string) => fetch_<Array<{ node_id: string; label: string; score: number }>>(`/knowledge/search?q=${encodeURIComponent(q)}`);
export const fetchScoreboard = () => fetch_<PredictionScoreboard>("/hypotheses/scoreboard");
export const fetchSourceReputations = () => fetch_<SourceReputation[]>("/sources/reputation");
export const fetchWatchRules = () => fetch_<WatchRule[]>("/admin/watch-rules");
export const fetchQueueHealth = () => fetch_<RuntimeQueueHealth>("/admin/runtime/queues");

export type AssistantEvent = { event: string; payload: unknown };

export async function streamAssistant(body: Record<string, unknown>, onEvent: (evt: AssistantEvent) => void, signal?: AbortSignal): Promise<void> {
  const res = await fetch(`${API}/assistant/stream`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  if (!res.ok || !res.body) throw new Error(`Stream failed: ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const blocks = buf.split("\n\n");
    buf = blocks.pop() || "";
    for (const block of blocks) {
      let ev = "";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) ev = line.slice(7);
        if (line.startsWith("data: ")) data.push(line.slice(6));
      }
      if (ev && data.length) try { onEvent({ event: ev, payload: JSON.parse(data.join("\n")) }); } catch {}
    }
  }
}
