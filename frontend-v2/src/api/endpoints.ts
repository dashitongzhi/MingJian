import { api } from './client'

type ApiRecord = Record<string, unknown>
type AssistantSessionRecord = ApiRecord & {
  id: string
  title: string
  created_at: string
  message_count?: number
}

function readRecord(value: unknown): ApiRecord {
  return value && typeof value === 'object' ? value as ApiRecord : {}
}

function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined
}

function normalizeAssistantSession(value: unknown): AssistantSessionRecord {
  const session = readRecord(value)
  const title = readString(session.title) || readString(session.name) || readString(session.topic) || '未命名会话'
  const id = readString(session.id) || ''
  const created_at = readString(session.created_at) || new Date().toISOString()
  const message_count = typeof session.message_count === 'number' ? session.message_count : undefined
  return { ...session, id, title, created_at, message_count }
}

function normalizeAssistantDetail(value: unknown): ApiRecord {
  const detail = readRecord(value)
  const session = normalizeAssistantSession(detail.session || detail)
  const recentRuns = Array.isArray(detail.recent_runs) ? detail.recent_runs : []
  const dailyBriefs = Array.isArray(detail.daily_briefs) ? detail.daily_briefs : []
  const messages = [
    ...dailyBriefs.map((brief) => {
      const item = readRecord(brief)
      return {
        role: 'assistant',
        content: readString(item.summary) || '已生成每日简报',
        created_at: readString(item.generated_at),
      }
    }),
    ...recentRuns.flatMap((run) => {
      const item = readRecord(run)
      const result = readRecord(item.result)
      const analysis = readRecord(result.analysis)
      const latestReport = readRecord(result.latest_report)
      return [
        {
          role: 'user',
          content: readString(result.topic) || readString(session.topic) || readString(session.title) || '',
          created_at: readString(item.generated_at),
        },
        {
          role: 'assistant',
          content: readString(latestReport.summary) || readString(analysis.summary) || '分析完成',
          created_at: readString(item.generated_at),
        },
      ]
    }),
  ]
  return { ...detail, ...session, messages }
}

// ==================== 总览 ====================
export const consoleApi = {
  get: () => api.get('/console'),
  health: () => api.get('/health'),
}

// ==================== AI 助手 ====================
export const assistantApi = {
  listSessions: async () => (await api.get<unknown[]>('/assistant/sessions')).map(normalizeAssistantSession),
  getSession: async (id: string) => normalizeAssistantDetail(await api.get(`/assistant/sessions/${id}`)),
  getRecommendations: (id: string) => api.get<unknown[]>(`/assistant/session/${id}/recommendations`),
  createSession: async (data: unknown) => normalizeAssistantSession(await api.post('/assistant/sessions', data)),
  createRun: (data: unknown) => api.post('/assistant/runs', data),
  dailyBrief: (data: unknown) => api.post('/assistant/daily-brief', data),
}

// ==================== 智能体 ====================
export const agentsApi = {
  list: () => api.get<{ agents: unknown[]; total: number }>('/agents'),
  listAll: async () => (await api.get<{ agents: unknown[]; total: number }>('/agents')).agents,
  status: () => api.get('/agents/status'),
  reset: () => api.post('/agents/reset'),
}

// ==================== 辩论 ====================
export const debateApi = {
  list: () => api.get<unknown[]>('/debates'),
  get: (id: string) => api.get(`/debates/${id}`),
  trigger: (data: unknown) => api.post('/debates/trigger', data),
  getReplay: (id: string) => api.get(`/debates/${id}/replay`),
  getTimeline: (id: string) => api.get(`/debates/${id}/timeline`),
  getSummary: (id: string) => api.get(`/debates/${id}/summary`),
  interrupt: (id: string) => api.post(`/debates/${id}/interrupt`),
  createVote: (data: unknown) => api.post('/debate/votes', data),
}

// ==================== 场景模拟 ====================
export const simulationApi = {
  listRuns: () => api.get<unknown[]>('/simulation/runs'),
  createRun: (data: unknown) => api.post('/simulation/runs', data),
  getWorkbench: (runId: string) => api.get(`/runs/${runId}/workbench`),
  getDecisionTrace: (runId: string) => api.get(`/runs/${runId}/decision-trace`),
  listOptions: (runId: string) => api.get(`/runs/${runId}/options`),
  createOption: (runId: string, data: unknown) => api.post(`/runs/${runId}/options`, data),
  listHypotheses: (runId: string) => api.get(`/runs/${runId}/hypotheses`),
  createHypothesis: (runId: string, data: unknown) => api.post(`/runs/${runId}/hypotheses`, data),
  verifyHypothesis: (hypId: string) => api.post(`/hypotheses/${hypId}/verify`),
  getDebates: (runId: string) => api.get(`/runs/${runId}/debates`),
}

// ==================== 证据库 ====================
export const evidenceApi = {
  list: (params?: Record<string, string>) =>
    api.get<{ items: unknown[]; total: number }>(`/evidence${params ? '?' + new URLSearchParams(params) : ''}`),
  listClaims: () => api.get<{ items: unknown[]; total: number }>('/claims'),
  listSignals: () => api.get<{ items: unknown[]; total: number }>('/signals'),
  listEvents: () => api.get('/events'),
  listTrends: () => api.get('/trends'),
  listReviewItems: () => api.get<unknown[]>('/review/items'),
  acceptReview: (id: string) => api.post(`/review/items/${id}/accept`),
  rejectReview: (id: string) => api.post(`/review/items/${id}/reject`),
  createIngestRun: (data: unknown) => api.post('/ingest/runs', data),
}

// ==================== 数据源 ====================
export const sourcesApi = {
  listStates: () => api.get<unknown[]>('/sources/states'),
  listChanges: () => api.get('/sources/changes'),
  listReputations: () => api.get('/sources/reputation'),
  listHealth: () => api.get('/sources/health'),
  listSnapshots: () => api.get('/sources/snapshots'),
  resetWatchCursor: (ruleId: string) => api.post(`/watch/rules/${ruleId}/cursor/reset`),
  reanalyzeChange: (changeId: string) => api.post(`/sources/changes/${changeId}/reanalyze`),
}

// ==================== 报告中心 ====================
export const reportApi = {
  listPredictions: () => api.get<unknown[]>('/predictions'),
  getPrediction: (id: string) => api.get(`/predictions/${id}`),
  listVersions: (id: string) => api.get(`/predictions/${id}/versions`),
  getImpact: (id: string) => api.get(`/predictions/${id}/impact`),
  reforecast: (id: string) => api.post(`/predictions/${id}/reforecast`),
  getMonitoringDashboard: () => api.get('/monitoring/dashboard'),
  listRevisionJobs: () => api.get('/predictions/revision-jobs'),
  getPredictionTimeline: (id: string) => api.get(`/predictions/${id}/timeline`),
  listDecisions: (sessionId?: string) =>
    api.get<unknown[]>(sessionId ? `/decisions?session_id=${encodeURIComponent(sessionId)}` : '/decisions'),
  createDecision: (data: unknown) => api.post('/decisions', data),
  updateDecisionOutcome: (id: string, data: unknown) => api.put(`/decisions/${id}/outcome`, data),
  getDecisionStats: () => api.get<Record<string, unknown>>('/decisions/stats'),
  getDecisionAccuracy: () => api.get('/decisions/accuracy'),
  getPendingVerifications: () => api.get('/decisions/pending-verifications'),
}

// ==================== 设置 ====================
export const settingsApi = {
  getOpenaiStatus: () => api.get('/admin/openai/status'),
  testOpenai: () => api.post('/admin/openai/test'),
}

// ==================== 监控 ====================
export const monitoringApi = {
  listWatchRules: () => api.get<unknown[]>('/watch/rules'),
  createWatchRule: (data: unknown) => api.post('/watch/rules', data),
  updateWatchRule: (id: string, data: unknown) => api.patch(`/watch/rules/${id}`, data),
  deleteWatchRule: (id: string) => api.delete(`/watch/rules/${id}`),
  triggerWatchRule: (id: string) => api.post(`/watch/rules/${id}/trigger`),
  getWatchRuleSources: (id: string) =>
    api.get<unknown[]>(`/sources/states?watch_rule_id=${encodeURIComponent(id)}`),
  getDashboard: () => api.get('/monitoring/dashboard'),
  getQueueHealth: () => api.get('/admin/runtime/queues'),
  getPlatformTopology: () => api.get('/admin/runtime/platform-topology'),
  getAnalysisCache: () => api.get('/admin/analysis/cache'),
  getKnowledgeGraph: () => api.get('/knowledge/graph'),
  searchKnowledge: (q: string) => api.get(`/knowledge/search?q=${encodeURIComponent(q)}`),
}

// ==================== 工作台/导出/通知 ====================
export const workbenchApi = {
  sessions: () => api.get<unknown[]>('/assistant/sessions'),
  getSession: (id: string) => api.get(`/assistant/sessions/${id}`),
  getRunWorkbench: (runId: string) => api.get(`/runs/${runId}/workbench`),
  getDecisionTrace: (runId: string) => api.get(`/runs/${runId}/decision-trace`),
  getScenarioCompare: (runId: string) => api.get(`/runs/${runId}/scenario-compare`),
  getReplayPackage: (runId: string) => api.get(`/runs/${runId}/replay-package`),
  listJarvisRuns: (runId?: string) => api.get<unknown[]>(`/jarvis/runs${runId ? `?run_id=${encodeURIComponent(runId)}` : ''}`),
  createJarvisRun: (data: unknown) => api.post('/jarvis/runs', data),
  exportAssistantSession: (sessionId: string) => api.get(`/export/assistant/session/${sessionId}`),
  exportSimulation: (runId: string) => api.get(`/export/simulation/${runId}`),
  notificationStats: () => api.get('/stats'),
}
