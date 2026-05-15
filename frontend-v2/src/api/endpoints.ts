import { api } from './client'

// ==================== 总览 ====================
export const consoleApi = {
  get: () => api.get('/console'),
  health: () => api.get('/health'),
}

// ==================== AI 助手 ====================
export const assistantApi = {
  listSessions: () => api.get<unknown[]>('/assistant/sessions'),
  getSession: (id: string) => api.get(`/assistant/sessions/${id}`),
  createSession: (data: unknown) => api.post('/assistant/sessions', data),
  createRun: (data: unknown) => api.post('/assistant/runs', data),
  dailyBrief: (data: unknown) => api.post('/assistant/daily-brief', data),
}

// ==================== 智能体 ====================
export const agentsApi = {
  list: () => api.get<{ agents: unknown[]; total: number }>('/agents'),
  status: () => api.get('/agents/status'),
  listAll: () => api.get<unknown[]>('/agents/all'),
  configure: (data: unknown) => api.post('/agents/configure', data),
  setModel: (data: unknown) => api.post('/agents/model', data),
  reset: () => api.post('/agents/reset'),
  createCustom: (data: unknown) => api.post('/agents/custom', data),
  getCustom: (roleKey: string) => api.get(`/agents/custom/${roleKey}`),
  updateCustom: (roleKey: string, data: unknown) => api.put(`/agents/custom/${roleKey}`, data),
  deleteCustom: (roleKey: string) => api.delete(`/agents/custom/${roleKey}`),
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
  listCustom: () => api.get('/sources/custom'),
  createCustom: (data: unknown) => api.post('/sources/custom', data),
  updateCustom: (sourceKey: string, data: unknown) => api.put(`/sources/custom/${sourceKey}`, data),
  deleteCustom: (sourceKey: string) => api.delete(`/sources/custom/${sourceKey}`),
  testCustom: (sourceKey: string) => api.post(`/sources/custom/${sourceKey}/test`),
  listProviders: () => api.get('/sources/providers'),
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
  getCalibration: () => api.get('/monitoring/calibration'),
  getCalibrationHistory: () => api.get('/monitoring/calibration/history'),
  listBacktests: () => api.get('/predictions/backtests'),
  listRevisionJobs: () => api.get('/predictions/revision-jobs'),
  getPredictionTimeline: (id: string) => api.get(`/predictions/${id}/timeline`),
  listDecisions: () => api.get<unknown[]>('/decisions'),
  createDecision: (data: unknown) => api.post('/decisions', data),
  getDecisionStats: () => api.get<Record<string, unknown>>('/decisions/stats'),
  getDecisionAccuracy: () => api.get('/decisions/accuracy'),
  getPendingVerifications: () => api.get('/decisions/pending-verifications'),
}

// ==================== 设置 ====================
export const settingsApi = {
  getModelSettings: () => api.get('/model/settings'),
  updateModelSettings: (data: unknown) => api.put('/model/settings', data),
  getModelCapabilities: () => api.get('/model/capabilities'),
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
  getDashboard: () => api.get('/monitoring/dashboard'),
  getQueueHealth: () => api.get('/admin/runtime/queues'),
  getAnalysisCache: () => api.get('/admin/analysis/cache'),
  getKnowledgeGraph: () => api.get('/knowledge/graph'),
  searchKnowledge: (q: string) => api.get(`/knowledge/search?q=${encodeURIComponent(q)}`),
  getScoreboard: () => api.get('/hypotheses/scoreboard'),
  getCalibration: () => api.get('/calibration'),
  computeCalibration: () => api.post('/calibration/compute'),
}

// ==================== 供应商 ====================
export const providersApi = {
  presets: () => api.get('/admin/providers/presets'),
  list: () => api.get('/admin/providers'),
  save: (data: unknown) => api.post('/admin/providers', data),
  delete: (providerId: string) => api.delete(`/admin/providers/${providerId}`),
  test: (data: unknown) => api.post('/admin/providers/test', data),
}

// ==================== 批处理 ====================
export const batchApi = {
  list: () => api.get<unknown[]>('/batch'),
  get: (batchId: string) => api.get(`/batch/${batchId}`),
  tasks: (batchId: string) => api.get<unknown[]>(`/batch/${batchId}/tasks`),
  submit: (data: unknown) => api.post('/batch/submit', data),
  cancel: (batchId: string) => api.post(`/batch/${batchId}/cancel`),
}

// ==================== 工作台/导出/通知 ====================
export const workbenchApi = {
  sessions: () => api.get<unknown[]>('/assistant/sessions'),
  getSession: (id: string) => api.get(`/assistant/sessions/${id}`),
  getRunWorkbench: (runId: string) => api.get(`/runs/${runId}/workbench`),
  getDecisionTrace: (runId: string) => api.get(`/runs/${runId}/decision-trace`),
  getScenarioCompare: (runId: string) => api.get(`/runs/${runId}/scenario-compare`),
  getReplayPackage: (runId: string) => api.get(`/runs/${runId}/replay-package`),
  exportAssistantSession: (sessionId: string) => api.get(`/export/assistant/session/${sessionId}`),
  exportSimulation: (runId: string) => api.get(`/export/simulation/${runId}`),
  notificationStats: () => api.get('/stats'),
}
