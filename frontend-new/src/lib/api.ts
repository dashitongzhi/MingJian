const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text().catch(() => "")}`);
  return res.json();
}

// Types
export interface AnalysisStep {
  stage: string;
  message: string;
  detail: string | null;
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

export interface SimulationRun {
  id: string;
  domain_id: string;
  status: string;
  tick_count: number;
  created_at: string;
}

export interface AssistantResult {
  topic: string;
  domain_id: string;
  analysis: {
    summary: string;
    findings: string[];
    recommendations: string[];
  };
  debate: {
    rounds: DebateRound[];
    verdict: DebateVerdict | null;
  } | null;
  simulation_run: SimulationRun;
}

// Stream assistant analysis
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

export interface DashboardStats {
  active_sessions: number;
  prediction_accuracy: number;
  pending_items: number;
}

// API endpoints
export const fetchHealth = () => apiFetch<{ status: string }>("/health");
export const fetchStats = () => apiFetch<DashboardStats>("/stats");
export const fetchSimulationRuns = (limit = 20) =>
  apiFetch<SimulationRun[]>(`/simulation/runs?limit=${limit}`);
export const createSimulationRun = (data: Record<string, unknown>) =>
  apiFetch<SimulationRun>("/simulation/runs", { method: "POST", body: JSON.stringify(data) });
