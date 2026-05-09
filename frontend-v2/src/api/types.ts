export * from './endpoints'

// ---- 通用类型 ----
export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// ---- 总览 ----
export interface ConsoleData {
  stats: Record<string, unknown>
  recent_sessions: unknown[]
  quick_actions: unknown[]
}

export interface HealthStatus {
  status: string
  version?: string
  uptime?: number
}

// ---- AI 助手 ----
export interface StrategicSession {
  id: string
  title: string
  created_at: string
  status: string
}

export interface StrategicSessionDetail extends StrategicSession {
  messages: unknown[]
  analysis?: unknown
}

export interface AssistantRequest {
  topic: string
  session_id?: string
  stream?: boolean
}

// ---- 智能体 ----
export interface Agent {
  role_key: string
  name: string
  description?: string
  model?: string
  status?: string
  is_custom?: boolean
}

export interface CustomAgentCreate {
  role_key: string
  name: string
  description?: string
  model?: string
  system_prompt?: string
}

export interface Provider {
  id: string
  name: string
  type: string
  base_url?: string
  models?: string[]
  status?: string
}

// ---- 辩论 ----
export interface Debate {
  id: string
  topic: string
  status: string
  rounds?: number
  created_at: string
  agents?: string[]
}

export interface DebateVote {
  id: string
  debate_id: string
  agent: string
  vote: string
  reasoning?: string
}

// ---- 场景模拟 ----
export interface SimulationRun {
  id: string
  name: string
  status: string
  scenario_type: string
  created_at: string
  kpis?: Record<string, unknown>
}

export interface Hypothesis {
  id: string
  statement: string
  status: 'pending' | 'verified' | 'refuted'
  evidence_count?: number
}

export interface DecisionOption {
  id: string
  title: string
  description?: string
  score?: number
}

// ---- 证据库 ----
export interface Evidence {
  id: string
  title: string
  source: string
  content: string
  credibility?: number
  created_at: string
}

export interface Claim {
  id: string
  statement: string
  status: string
  evidence_ids?: string[]
}

export interface Signal {
  id: string
  name: string
  value: number
  change?: number
  source?: string
}

export interface ReviewItem {
  id: string
  title: string
  status: 'pending' | 'accepted' | 'rejected'
  source?: string
  created_at: string
}

export interface SourceState {
  key: string
  name: string
  status: string
  last_check?: string
  error_count?: number
}

// ---- 报告中心 ----
export interface Prediction {
  series_id: string
  name: string
  current_value?: number
  confidence?: number
  status: string
  last_updated?: string
}

export interface MonitoringDashboard {
  calibration_score?: number
  active_alerts?: number
  total_predictions?: number
  accuracy_trend?: unknown[]
}

export interface UserDecision {
  id: string
  title: string
  outcome?: string
  confidence?: number
  created_at: string
}

// ---- 设置 ----
export interface ModelSettings {
  provider: string
  model: string
  temperature?: number
  max_tokens?: number
}

export interface ModelCapability {
  name: string
  score: number
  description?: string
}
