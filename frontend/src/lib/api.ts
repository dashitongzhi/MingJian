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
export interface DebateVote { id: string; debate_session_id: string; round_number: number; role: "advocate" | "challenger" | "arbitrator"; vote: "agree" | "disagree" | "neutral"; comment: string | null; created_at: string }
export interface WorkbenchRecommendation { title: string; priority?: string | null; rationale?: string | null; action_items?: string[]; text?: string | null }
export interface WorkbenchAlternativeScenario { name: string; description?: string | null; expected_outcome?: string | null; probability?: number | null }
export interface WorkbenchPredictionVersion { id: string; series_id?: string | null; run_id?: string | null; version_number: number; probability?: number | null; confidence?: number | null; trigger_type?: string | null; prediction_text?: string | null; summary_delta?: string | null; status?: string | null; created_at?: string | null; updated_at?: string | null }
export interface DebateVerdict { verdict: string; confidence: number; winning_arguments: string[]; decisive_evidence: string[]; minority_opinion: string | null; recommendations?: WorkbenchRecommendation[]; risk_factors?: string[]; alternative_scenarios?: WorkbenchAlternativeScenario[]; conclusion_summary?: string | null }
export interface DebateDetail { id: string; topic: string; trigger_type: string; status: string; rounds: DebateRound[]; verdict: DebateVerdict | null; created_at: string }
export interface DebateRoundStartEvent { event: "debate_round_start"; payload: { round_number: number; role: string; debate_id?: string } }
export interface DebateRoundCompleteEvent { event: "debate_round_complete"; payload: { round_number: number; role: string; position: string; confidence: number; key_arguments: string[]; debate_id?: string } }
export interface DebateVerdictEvent { event: "debate_verdict"; payload: { verdict: string; confidence: number; winning_arguments: string[]; decisive_evidence: string[]; debate_id?: string } }
export type DebateStreamEvent = DebateRoundStartEvent | DebateRoundCompleteEvent | DebateVerdictEvent;
export interface PanelMessage { participant_id: string; label: string; model_target: string; stance: "support" | "challenge" | "monitor"; summary: string; key_points: string[]; recommendation: string; confidence: number }
export interface StrategicSession { id: string; name: string; topic: string; domain_id: string; subject_name: string | null; auto_refresh_enabled: boolean; latest_brief_summary: string | null; latest_run_summary: string | null; created_at: string }
export interface StrategicRunSnapshot { id: string; session_id?: string; ingest_run_id?: string | null; simulation_run_id?: string | null; debate_id?: string | null; generated_report_id?: string | null; latest_prediction_version?: WorkbenchPredictionVersion | null; result: AssistantResult; generated_at: string }
export interface StrategicSessionDetail { session: StrategicSession; daily_briefs: Array<{ id: string; summary: string; generated_at: string }>; recent_runs: StrategicRunSnapshot[] }
export interface KPIMetric { metric: string; start: number | null; end: number | null; delta: number | null }
export interface WorkbenchData { run_id: string; domain_id: string; timeline: Array<{ event_id: string; event_type: string; tick: number | null; title: string }>; geo_map: { theater: string | null; assets: Array<{ name: string; asset_type: string; latitude: number; longitude: number }> }; evidence_graph?: { nodes: Array<{ node_id: string; label: string; node_type: string; metadata?: Record<string, unknown> }>; edges: Array<{ source_id: string; target_id: string; relation_type: string }> }; prediction_versions?: WorkbenchPredictionVersion[]; kpi_comparator: { metrics: KPIMetric[] }; debate_records: Array<{ debate_id: string; topic: string; verdict: string | null; confidence: number | null }> }
export interface GeneratedReport { id: string; title: string; summary: string }
export interface AssistantResult { session_id: string | null; topic: string; domain_id: string; subject_name: string; analysis: AnalysisResponse; ingest_run: IngestRun; simulation_run: SimulationRun; latest_report: GeneratedReport | null; debate: DebateDetail | null; workbench: WorkbenchData; panel_discussion: PanelMessage[]; generated_at: string }
export interface WorkbenchDecisionData {
  session: StrategicSession;
  generated_at: string | null;
  current_recommendation: { verdict: string; confidence: number | null; summary: string | null };
  findings: string[];
  risk_factors: string[];
  recommendations: WorkbenchRecommendation[];
  alternative_scenarios: WorkbenchAlternativeScenario[];
  evidence: { evidence_count: number; claims_count: number; confidence: number | null; decisive_evidence: string[] };
  prediction_versions: WorkbenchPredictionVersion[];
}
export interface PredictionScoreboard { total_hypotheses: number; confirmed: number; refuted: number; pending: number; accuracy: number; brier_score: number | null; human_baseline_accuracy: number | null; lift_over_human_baseline: number | null }
export interface SourceReputation { source_key: string; source_type: string | null; display_name: string | null; domain_id: string; confirmed_count: number; refuted_count: number; reputation_score: number; noise_rate: number }
export interface WatchRule { id: string; name: string; domain_id: string; query: string; enabled: boolean; poll_interval_minutes: number; auto_trigger_simulation: boolean; created_at: string }
export interface RuntimeQueueHealth { queues: Array<{ queue: string; pending: number; processing: number; completed: number; failed: number }>; dead_letter_count: number }
export type UserDecisionValue = "adopt" | "defer" | "need_more_info" | "reject";
export interface UserDecision { id: string; session_id: string; decision: UserDecisionValue; notes: string | null; outcome: string | null; outcome_recorded_at: string | null; created_at: string; updated_at: string }

export const fetchHealth = () => fetch_<{ status: string }>("/health");
export const fetchSessions = () => fetch_<StrategicSession[]>("/assistant/sessions");
export const fetchSessionDetail = (id: string) => fetch_<StrategicSessionDetail>(`/assistant/sessions/${id}`);
export const fetchSimulationRuns = (limit = 20) => fetch_<SimulationRun[]>(`/simulation/runs?limit=${limit}`);
export const fetchWorkbench = (runId: string) => fetch_<WorkbenchData>(`/runs/${runId}/workbench`);
export const fetchWorkbenchData = async (sessionId: string) => buildWorkbenchDataFromSessionDetail(await fetchSessionDetail(sessionId));
export const createSimulationRun = (data: Record<string, unknown>) => fetch_<SimulationRun>("/simulation/runs", { method: "POST", body: JSON.stringify(data) });
export interface DebateSummary { debate_id: string; topic: string; trigger_type: string; verdict: string | null; confidence: number | null; created_at: string }
export const fetchDebateDetail = (id: string) => fetch_<DebateDetail>(`/debates/${id}`);
export const fetchDebates = (limit = 50) => fetch_<DebateSummary[]>(`/debates?limit=${limit}`);
export const fetchDebateVotes = (debateSessionId: string) => fetch_<DebateVote[]>(`/debate/votes?debate_session_id=${encodeURIComponent(debateSessionId)}`);
export const createDebateVote = (data: { debate_session_id: string; round_number: number; role: "advocate" | "challenger" | "arbitrator"; vote: "agree" | "disagree" | "neutral"; comment?: string | null }) => fetch_<DebateVote>("/debate/votes", { method: "POST", body: JSON.stringify(data) });
export const fetchEvidence = async (limit = 50) => {
  const res = await fetch_<{ items: Array<{ id: string; title: string; summary: string; confidence: number; created_at: string }>; total: number }>(`/evidence?limit=${limit}`);
  return res.items;
};
export const fetchClaims = async (limit = 50) => {
  const res = await fetch_<{ items: Array<{ id: string; statement: string; confidence: number; status: string }>; total: number }>(`/claims?limit=${limit}`);
  return res.items;
};
export const fetchKnowledgeGraph = (limit = 100) => fetch_<{ nodes: Array<{ node_id: string; label: string; node_type: string }>; edges: Array<{ source_id: string; target_id: string; relation_type: string }> }>(`/knowledge/graph?limit=${limit}`);
export const searchKnowledge = (q: string) => fetch_<Array<{ node_id: string; label: string; score: number }>>(`/knowledge/search?q=${encodeURIComponent(q)}`);
export const fetchScoreboard = () => fetch_<PredictionScoreboard>("/hypotheses/scoreboard");
export const fetchSourceReputations = () => fetch_<SourceReputation[]>("/sources/reputation");
export const fetchWatchRules = () => fetch_<WatchRule[]>("/admin/watch-rules");
export const fetchQueueHealth = () => fetch_<RuntimeQueueHealth>("/admin/runtime/queues");
export const createUserDecision = (data: { session_id: string; decision: UserDecisionValue; notes?: string | null }) => (
  fetch_<UserDecision>("/decisions", { method: "POST", body: JSON.stringify(data) })
);

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function textValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value == null) return "";
  const record = asRecord(value);
  if (record) {
    for (const key of ["title", "name", "summary", "description", "statement", "text", "content"]) {
      if (typeof record[key] === "string" && record[key]) return record[key];
    }
  }
  return JSON.stringify(value);
}

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(textValue).filter(Boolean);
  const text = textValue(value);
  return text ? [text] : [];
}

function recommendationList(value: unknown, fallback: unknown): WorkbenchRecommendation[] {
  const items = Array.isArray(value) && value.length > 0 ? value : Array.isArray(fallback) ? fallback : [];
  return items.map((item) => {
    const record = asRecord(item);
    if (!record) return { title: textValue(item), action_items: [] };
    return {
      title: textValue(record.title ?? record.name ?? record.recommendation ?? record.text ?? record.summary ?? item),
      priority: typeof record.priority === "string" ? record.priority : null,
      rationale: typeof record.rationale === "string" ? record.rationale : typeof record.reason === "string" ? record.reason : null,
      action_items: stringList(record.action_items ?? record.actions),
      text: typeof record.text === "string" ? record.text : null,
    };
  }).filter((item) => item.title);
}

function alternativeScenarioList(value: unknown): WorkbenchAlternativeScenario[] {
  if (!Array.isArray(value)) return [];
  return value.map((item, index) => {
    const record = asRecord(item);
    if (!record) return { name: textValue(item) || `Scenario ${index + 1}` };
    return {
      name: textValue(record.name ?? record.title ?? item) || `Scenario ${index + 1}`,
      description: textValue(record.description ?? record.summary),
      expected_outcome: textValue(record.expected_outcome ?? record.outcome),
      probability: typeof record.probability === "number" ? record.probability : null,
    };
  });
}

function predictionVersionList(...sources: unknown[]): WorkbenchPredictionVersion[] {
  const versions = sources.flatMap((source) => Array.isArray(source) ? source : source ? [source] : []);
  const seen = new Set<string>();
  return versions.map((item, index) => {
    const record = asRecord(item) || {};
    const id = textValue(record.id) || `prediction-${index}`;
    return {
      id,
      series_id: textValue(record.series_id) || null,
      run_id: textValue(record.run_id) || null,
      version_number: typeof record.version_number === "number" ? record.version_number : Number(record.version_number ?? index + 1),
      probability: typeof record.probability === "number" ? record.probability : null,
      confidence: typeof record.confidence === "number" ? record.confidence : null,
      trigger_type: textValue(record.trigger_type) || null,
      prediction_text: textValue(record.prediction_text) || null,
      summary_delta: textValue(record.summary_delta) || null,
      status: textValue(record.status) || null,
      created_at: textValue(record.created_at) || null,
      updated_at: textValue(record.updated_at) || null,
    };
  }).filter((item) => {
    const key = item.id || `${item.run_id}-${item.version_number}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).sort((a, b) => a.version_number - b.version_number);
}

function buildWorkbenchDataFromSessionDetail(detail: StrategicSessionDetail): WorkbenchDecisionData {
  const latestRun = detail.recent_runs[0];
  const result = latestRun?.result;
  const verdict = result?.debate?.verdict;
  const workbench = result?.workbench;
  const evidenceNodes = workbench?.evidence_graph?.nodes ?? [];
  const evidenceCount = evidenceNodes.filter((node) => node.node_type === "evidence").length || result?.analysis?.sources?.length || verdict?.decisive_evidence?.length || 0;
  const claimsCount = evidenceNodes.filter((node) => node.node_type === "claim").length;
  const summary = verdict?.conclusion_summary || result?.analysis?.summary || detail.session.latest_run_summary || detail.session.latest_brief_summary || null;

  return {
    session: detail.session,
    generated_at: latestRun?.generated_at ?? result?.generated_at ?? null,
    current_recommendation: {
      verdict: verdict?.verdict || result?.latest_report?.title || detail.session.latest_run_summary || detail.session.topic,
      confidence: verdict?.confidence ?? latestRun?.latest_prediction_version?.confidence ?? null,
      summary,
    },
    findings: result?.analysis?.findings ?? [],
    risk_factors: stringList(verdict?.risk_factors),
    recommendations: recommendationList(verdict?.recommendations, result?.analysis?.recommendations),
    alternative_scenarios: alternativeScenarioList(verdict?.alternative_scenarios),
    evidence: {
      evidence_count: evidenceCount,
      claims_count: claimsCount,
      confidence: verdict?.confidence ?? latestRun?.latest_prediction_version?.confidence ?? null,
      decisive_evidence: verdict?.decisive_evidence ?? [],
    },
    prediction_versions: predictionVersionList(workbench?.prediction_versions, latestRun?.latest_prediction_version),
  };
}

export type AssistantEvent = { event: string; payload: unknown };

async function streamEvents<TEvent extends { event: string; payload: unknown }>(
  path: string,
  body: Record<string, unknown>,
  onEvent: (evt: TEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
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
      if (ev && data.length) try { onEvent({ event: ev, payload: JSON.parse(data.join("\n")) } as TEvent); } catch {}
    }
  }
}

export async function streamAssistant(body: Record<string, unknown>, onEvent: (evt: AssistantEvent) => void, signal?: AbortSignal): Promise<void> {
  return streamEvents<AssistantEvent>("/assistant/stream", body, onEvent, signal);
}

export async function streamDebate(body: Record<string, unknown>, onEvent: (evt: DebateStreamEvent) => void, signal?: AbortSignal): Promise<void> {
  return streamEvents<DebateStreamEvent>("/debates/trigger/stream", body, onEvent, signal);
}
