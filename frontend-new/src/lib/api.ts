const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text().catch(() => "")}`);
  return res.json();
}

// ===== Types =====
export interface AnalysisSource {
  source_type: string;
  title: string;
  url: string;
  summary: string;
  published_at: string | null;
}

export interface AnalysisStep {
  stage: string;
  message: string;
  detail: string | null;
}

export interface AnalysisResponse {
  query: string;
  domain_id: string;
  summary: string;
  reasoning_steps: AnalysisStep[];
  findings: string[];
  recommendations: string[];
  sources: AnalysisSource[];
  generated_at: string;
}

export interface SimulationRun {
  id: string;
  domain_id: string;
  status: string;
  tick_count: number;
  created_at: string;
}

export interface DebateRound {
  round_number: number;
  role: string;
  position: string;
  confidence: number;
  arguments: Record<string, unknown>[];
  rebuttals: Record<string, unknown>[];
  concessions: Record<string, unknown>[];
}

export interface DebateVerdict {
  verdict: string;
  confidence: number;
  winning_arguments: string[];
  decisive_evidence: string[];
  minority_opinion: string | null;
}

export interface DebateDetail {
  id: string;
  topic: string;
  status: string;
  rounds: DebateRound[];
  verdict: DebateVerdict | null;
  created_at: string;
}

export interface DebateSummary {
  debate_id: string;
  topic: string;
  verdict: string | null;
  confidence: number | null;
  created_at: string;
}

export interface StrategicSession {
  id: string;
  name: string;
  topic: string;
  domain_id: string;
  created_at: string;
}

export interface PredictionVersion {
  id: string;
  series_id: string;
  version_number: number;
  probability: number;
  confidence: number;
  prediction_text: string;
  status: string;
  created_at: string;
}

export interface WatchRule {
  id: string;
  name: string;
  domain_id: string;
  enabled: boolean;
  last_poll_at: string | null;
  created_at: string;
}

export interface DashboardStats {
  active_sessions: number;
  prediction_accuracy: number;
  pending_items: number;
}

export interface AgentStatus {
  role: string;
  name: string;
  icon: string;
  description: string;
  effective_model: string;
  has_key: boolean;
}

export interface CustomSource {
  key: string;
  label: string;
  type: string;
  url: string;
  enabled: boolean;
}

// ===== API Endpoints =====

// Health & Stats
export const fetchHealth = () => apiFetch<{ status: string }>("/health");
export const fetchStats = () => apiFetch<DashboardStats>("/stats");

// Assistant & Sessions
export const fetchSessions = () => apiFetch<StrategicSession[]>("/assistant/sessions");
export const fetchSessionDetail = (id: string) => apiFetch<any>(`/assistant/sessions/${id}`);

// Simulation
export const fetchSimulationRuns = (limit = 20) =>
  apiFetch<SimulationRun[]>(`/simulation/runs?limit=${limit}`);
export const createSimulationRun = (data: Record<string, unknown>) =>
  apiFetch<SimulationRun>("/simulation/runs", { method: "POST", body: JSON.stringify(data) });

// Debate
export const fetchDebates = (limit = 50) => apiFetch<DebateSummary[]>(`/debates?limit=${limit}`);
export const fetchDebateDetail = (id: string) => apiFetch<DebateDetail>(`/debates/${id}`);

// Predictions
export const fetchPredictions = () => apiFetch<PredictionVersion[]>("/predictions");

// Monitoring
export const fetchMonitoringDashboard = () => apiFetch<any>("/monitoring/dashboard");
export const fetchWatchRules = () => apiFetch<WatchRule[]>("/admin/watch-rules");
export const fetchQueueHealth = () => apiFetch<any>("/admin/runtime/queues");

// Agents
export const fetchAgentStatus = () => apiFetch<{ agents: AgentStatus[] }>("/agents/status");
export const configureAgents = (keys: any[]) =>
  apiFetch<any>("/agents/configure", { method: "POST", body: JSON.stringify({ keys }) });

// Sources
export const fetchCustomSources = () => apiFetch<CustomSource[]>("/sources/custom");
export const createCustomSource = (data: Partial<CustomSource>) =>
  apiFetch<CustomSource>("/sources/custom", { method: "POST", body: JSON.stringify(data) });
export const updateCustomSource = (key: string, data: Partial<CustomSource>) =>
  apiFetch<CustomSource>(`/sources/custom/${key}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteCustomSource = (key: string) =>
  apiFetch<void>(`/sources/custom/${key}`, { method: "DELETE" });

// Predictions
export const fetchPredictions = () => apiFetch<PredictionVersion[]>("/predictions");
export async function streamAssistant(
  params: {
    topic: string;
    domain_id: string;
    subject_name: string;
    tick_count: number;
  },
  onEvent: (event: { event: string; payload: any }) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${API}/assistant/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal,
  });

  if (!res.ok) throw new Error(`Stream failed: ${res.status}`);
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim() || !line.startsWith("data: ")) continue;
      try {
        const data = JSON.parse(line.slice(6));
        onEvent(data);
      } catch (e) {
        console.error("Failed to parse SSE:", e);
      }
    }
  }
}
