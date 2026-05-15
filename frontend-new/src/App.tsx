import { useState, useEffect, useRef } from 'react'
import {
  Moon,
  Sun,
  Brain,
  MessageSquare,
  TrendingUp,
  Pause,
  Play,
  Minimize2,
  Maximize2,
  LayoutDashboard,
  Clock,
  Search,
  Shield,
  Database,
  Users,
  Layers,
  Building2,
  ClipboardCheck,
} from 'lucide-react'
import {
  streamAssistant,
  fetchSimulationRuns,
  fetchStats,
  fetchDebates,
  fetchSessions,
  fetchAgentStatus,
  fetchMonitoringDashboard,
  fetchWatchRules,
  fetchCustomSources,
  fetchPredictions,
  fetchDebateDetail,
  type DashboardStats,
  type SimulationRun,
  type DebateSummary,
  type StrategicSession,
  type AgentStatus,
  type WatchRule,
  type CustomSource,
  type PredictionVersion,
  type DebateDetail,
} from './lib/api'
import './App.css'

type Theme = 'light' | 'dark'
type ViewMode = 'default' | 'compact'
type ActivePage =
  | 'dashboard'
  | 'assistant'
  | 'workbench'
  | 'simulation'
  | 'debate'
  | 'evidence'
  | 'predictions'
  | 'monitoring'
  | 'providers'
  | 'sources'
  | 'agents'
  | 'batch'

interface DebateRound {
  round: number
  role: string
  position: string
  confidence: number
  arguments: string[]
}

function App() {
  const [theme, setTheme] = useState<Theme>('dark')
  const [viewMode, setViewMode] = useState<ViewMode>('default')
  const [activePage, setActivePage] = useState<ActivePage>('dashboard')
  const [stats, setStats] = useState<DashboardStats>({
    active_sessions: 0,
    prediction_accuracy: 87,
    pending_items: 0,
  })

  // Dashboard data
  const [sessions, setSessions] = useState<StrategicSession[]>([])
  const [simulations, setSimulations] = useState<SimulationRun[]>([])
  const [debates, setDebates] = useState<DebateSummary[]>([])
  const [agents, setAgents] = useState<AgentStatus[]>([])

  // Assistant state
  const [debateRounds, setDebateRounds] = useState<DebateRound[]>([])
  const [streaming, setStreaming] = useState(false)
  const [topic, setTopic] = useState('')
  const [domainId, setDomainId] = useState('auto')
  const [progress, setProgress] = useState(0)
  const [currentStage, setCurrentStage] = useState('准备中')
  const [dataCount, setDataCount] = useState(0)
  const [pausedEvents, setPausedEvents] = useState<any[]>([])
  const [verdict, setVerdict] = useState<{ verdict: string; confidence: number } | null>(null)
  const [isPaused, setIsPaused] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    fetchStats().then(setStats).catch(console.error)
    const interval = setInterval(() => {
      fetchStats().then(setStats).catch(console.error)
    }, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    // Load dashboard data
    fetchSessions().then(setSessions).catch(console.error)
    fetchSimulationRuns(10).then(setSimulations).catch(console.error)
    fetchDebates(10).then(setDebates).catch(console.error)
    fetchAgentStatus()
      .then((res) => setAgents(res.agents))
      .catch(console.error)
  }, [])

  const toggleTheme = () => setTheme(theme === 'light' ? 'dark' : 'light')
  const toggleViewMode = () => setViewMode(viewMode === 'default' ? 'compact' : 'default')

  const processEvent = (event: any) => {
    if (event.event === 'source_complete') {
      setDataCount((prev) => prev + (event.payload.count || 0))
      setProgress((prev) => Math.min(prev + 15, 65))
    } else if (event.event === 'debate_round_complete') {
      const payload = event.payload
      setDebateRounds((prev) => [
        ...prev,
        {
          round: payload.round_number,
          role: payload.role,
          position: payload.position,
          confidence: payload.confidence,
          arguments: payload.key_arguments || [],
        },
      ])
      setCurrentStage('辩论进行中')
      setProgress((prev) => Math.min(prev + 10, 90))
    } else if (event.event === 'debate_verdict') {
      const payload = event.payload
      setVerdict({
        verdict: payload.verdict || 'ACCEPTED',
        confidence: payload.confidence || 0.92,
      })
      setCurrentStage('分析完成')
      setProgress(100)
    } else if (event.event === 'step') {
      setCurrentStage(event.payload.message || '处理中')
    }
  }

  const handleRunAnalysis = async () => {
    if (!topic.trim() || streaming) return

    setStreaming(true)
    setDebateRounds([])
    setVerdict(null)
    setProgress(0)
    setCurrentStage('数据采集')
    setDataCount(0)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      await streamAssistant(
        {
          topic: topic.trim(),
          domain_id: domainId,
          subject_name: topic.slice(0, 50),
          tick_count: 4,
        },
        (event) => {
          if (isPaused) {
            setPausedEvents((prev) => [...prev, event])
            return
          }
          processEvent(event)
        },
        ctrl.signal
      )
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        console.error('Analysis failed:', err)
        setCurrentStage('分析失败')
      }
    } finally {
      setStreaming(false)
    }
  }

  const handlePauseToggle = () => {
    setIsPaused(!isPaused)
  }

  const handleResumeImmediate = () => {
    pausedEvents.forEach((event) => {
      processEvent(event)
    })
    setPausedEvents([])
    setIsPaused(false)
  }

  const handleDiscard = () => {
    setPausedEvents([])
    setIsPaused(false)
  }

  const navItems = [
    { id: 'dashboard' as ActivePage, label: '仪表板', icon: <LayoutDashboard size={20} /> },
    { id: 'assistant' as ActivePage, label: '战略助手', icon: <Brain size={20} /> },
    { id: 'workbench' as ActivePage, label: '工作台', icon: <ClipboardCheck size={20} /> },
    { id: 'simulation' as ActivePage, label: '情景推演', icon: <Clock size={20} /> },
    { id: 'debate' as ActivePage, label: '辩论系统', icon: <MessageSquare size={20} /> },
    { id: 'evidence' as ActivePage, label: '证据库', icon: <Search size={20} /> },
    { id: 'predictions' as ActivePage, label: '预测追踪', icon: <TrendingUp size={20} /> },
    { id: 'monitoring' as ActivePage, label: '监控中心', icon: <Shield size={20} /> },
    { id: 'providers' as ActivePage, label: '数据源', icon: <Building2 size={20} /> },
    { id: 'sources' as ActivePage, label: '自定义源', icon: <Database size={20} /> },
    { id: 'agents' as ActivePage, label: '智能体', icon: <Users size={20} /> },
    { id: 'batch' as ActivePage, label: '批处理', icon: <Layers size={20} /> },
  ]

  return (
    <div className="app">
      {/* Header */}
      <header className="glass-header">
        <div className="header-content">
          <div className="logo">
            <Brain className="logo-icon" />
            <span className="logo-text">明鉴</span>
            <span className="logo-subtitle">决策智能平台</span>
          </div>

          <div className="header-actions">
            <button
              className="icon-btn"
              onClick={toggleViewMode}
              title={viewMode === 'compact' ? '默认模式' : '简洁模式'}
            >
              {viewMode === 'compact' ? <Maximize2 size={18} /> : <Minimize2 size={18} />}
            </button>
            <button className="icon-btn" onClick={toggleTheme}>
              {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="main-content">
        {/* Sidebar */}
        <aside className="sidebar glass-card">
          <nav className="nav-menu">
            {navItems.map((item) => (
              <button
                key={item.id}
                className={`nav-item ${activePage === item.id ? 'active' : ''}`}
                onClick={() => setActivePage(item.id)}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            ))}
          </nav>

          {/* Stats Card */}
          <div className="stats-card glass-card-inner">
            <div className="stat-item">
              <span className="stat-label">活跃会话</span>
              <span className="stat-value">{stats.active_sessions}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">预测准确率</span>
              <span className="stat-value">{stats.prediction_accuracy}%</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">待处理项</span>
              <span className="stat-value">{stats.pending_items}</span>
            </div>
          </div>
        </aside>

        {/* Content Area */}
        <section className="content-area">
          {/* Dashboard Page */}
          {activePage === 'dashboard' && (
            <div className="dashboard-page">
              <h2 className="panel-title">仪表板总览</h2>

              <div className="dashboard-grid">
                {/* Sessions Card */}
                <div className="glass-card dashboard-card">
                  <div className="card-header">
                    <Brain size={20} />
                    <h3>战略会话</h3>
                    <span className="badge">{sessions.length}</span>
                  </div>
                  <div className="card-content">
                    {sessions.slice(0, 5).map((session) => (
                      <div key={session.id} className="list-item">
                        <div className="item-title">{session.name}</div>
                        <div className="item-meta">{session.domain_id}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Simulations Card */}
                <div className="glass-card dashboard-card">
                  <div className="card-header">
                    <Clock size={20} />
                    <h3>推演运行</h3>
                    <span className="badge">{simulations.length}</span>
                  </div>
                  <div className="card-content">
                    {simulations.slice(0, 5).map((sim) => (
                      <div key={sim.id} className="list-item">
                        <div className="item-title">{sim.domain_id}</div>
                        <div className="item-meta">
                          <span className={`status-badge ${sim.status.toLowerCase()}`}>
                            {sim.status}
                          </span>
                          <span>{sim.tick_count} ticks</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Debates Card */}
                <div className="glass-card dashboard-card">
                  <div className="card-header">
                    <MessageSquare size={20} />
                    <h3>辩论记录</h3>
                    <span className="badge">{debates.length}</span>
                  </div>
                  <div className="card-content">
                    {debates.slice(0, 5).map((debate) => (
                      <div key={debate.debate_id} className="list-item">
                        <div className="item-title">{debate.topic}</div>
                        <div className="item-meta">
                          {debate.verdict && (
                            <span className="verdict-badge">{debate.verdict}</span>
                          )}
                          {debate.confidence && (
                            <span>{(debate.confidence * 100).toFixed(0)}%</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Agents Card */}
                <div className="glass-card dashboard-card">
                  <div className="card-header">
                    <Users size={20} />
                    <h3>智能体状态</h3>
                    <span className="badge">{agents.length}</span>
                  </div>
                  <div className="card-content">
                    {agents.slice(0, 5).map((agent) => (
                      <div key={agent.role} className="list-item">
                        <div className="item-title">
                          <span className="agent-icon">{agent.icon}</span>
                          {agent.name}
                        </div>
                        <div className="item-meta">
                          <span className={`status-dot ${agent.has_key ? 'active' : 'inactive'}`} />
                          <span className="model-name">{agent.effective_model}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Assistant Page */}
          {activePage === 'assistant' && (
            <div className="assistant-panel">
              <h2 className="panel-title">战略助手</h2>

              {/* Pause Control */}
              {streaming && (
                <div className="pause-control glass-card">
                  <button className="pause-btn" onClick={handlePauseToggle}>
                    {isPaused ? <Play size={16} /> : <Pause size={16} />}
                    <span>{isPaused ? '已暂停' : '实时更新'}</span>
                  </button>
                  {isPaused && pausedEvents.length > 0 && (
                    <div className="pause-actions">
                      <span className="pending-count">{pausedEvents.length}条待处理</span>
                      <button className="action-btn" onClick={handleResumeImmediate}>
                        全部应用
                      </button>
                      <button className="action-btn danger" onClick={handleDiscard}>
                        丢弃
                      </button>
                    </div>
                  )}
                </div>
              )}

              <div className="input-card glass-card">
                <textarea
                  className="analysis-input"
                  placeholder="请输入分析主题..."
                  rows={3}
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  disabled={streaming}
                />
                <div className="input-actions">
                  <select
                    className="domain-select"
                    value={domainId}
                    onChange={(e) => setDomainId(e.target.value)}
                    disabled={streaming}
                  >
                    <option value="auto">自动识别</option>
                    <option value="corporate">企业战略</option>
                    <option value="military">军事分析</option>
                  </select>
                  <button
                    className="run-btn"
                    onClick={handleRunAnalysis}
                    disabled={streaming || !topic.trim()}
                  >
                    {streaming ? '分析中...' : '执行分析'}
                  </button>
                </div>
              </div>

              {streaming && (
                <div className="process-card glass-card">
                  <div className="process-header">
                    <span className="process-stage">{currentStage}</span>
                    <span className="process-status">{isPaused ? '已暂停' : '进行中'}</span>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${progress}%` }} />
                  </div>
                  <div className="process-details">
                    <div className="detail-item">
                      <span className="detail-icon">🔍</span>
                      <span>{currentStage}</span>
                    </div>
                    {dataCount > 0 && (
                      <div className="detail-item">
                        <span className="detail-icon">📊</span>
                        <span>已采集 {dataCount} 条数据</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Debate Rounds */}
              {debateRounds.length > 0 && (
                <div className="debate-rounds">
                  {debateRounds.map((round, index) => (
                    <div
                      key={index}
                      className={`debate-round glass-card ${
                        viewMode === 'compact' && index < debateRounds.length - 1 ? 'hidden' : ''
                      }`}
                    >
                      <div className="round-header">
                        <div className="round-info">
                          <span className="round-number">第 {round.round} 轮</span>
                          <span className="round-role">{round.role}</span>
                        </div>
                        <div className="confidence-bar">
                          <div
                            className="confidence-fill"
                            style={{ width: `${round.confidence * 100}%` }}
                          />
                          <span className="confidence-value">
                            {(round.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>

                      <p className="round-position">{round.position}</p>

                      {viewMode === 'default' && (
                        <div className="round-arguments">
                          <div className="arguments-label">关键论据</div>
                          {round.arguments.map((arg, i) => (
                            <div key={i} className="argument-item">
                              <span className="argument-marker">+</span>
                              <span>{arg}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}

                  {viewMode === 'compact' && debateRounds.length > 1 && (
                    <button className="view-history-btn">
                      查看历史 ({debateRounds.length - 1}轮)
                    </button>
                  )}
                </div>
              )}

              {/* Verdict Card */}
              {verdict && (
                <div className="verdict-card glass-card accent-border">
                  <div className="verdict-header">
                    <span className="verdict-label">最终裁决</span>
                    <span className="verdict-result">{verdict.verdict}</span>
                  </div>
                  <div className="verdict-confidence">
                    <span>置信度</span>
                    <span className="confidence-badge">
                      {(verdict.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Other pages - placeholder */}
          {activePage !== 'dashboard' && activePage !== 'assistant' && (
            <div className="placeholder-page glass-card">
              <h2 className="panel-title">{navItems.find((n) => n.id === activePage)?.label}</h2>
              <p className="placeholder-text">此模块正在开发中...</p>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}

export default App
