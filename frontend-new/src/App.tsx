import { useState, useEffect, useRef } from 'react'
import { Moon, Sun, Brain, MessageSquare, TrendingUp, Pause, Play, Minimize2, Maximize2 } from 'lucide-react'
import { streamAssistant, fetchSimulationRuns, fetchStats, type DashboardStats } from './lib/api'
import './App.css'

type Theme = 'light' | 'dark'
type ViewMode = 'default' | 'compact'

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
  const [isPaused, setIsPaused] = useState(false)
  const [activeTab, setActiveTab] = useState<'assistant' | 'debate' | 'simulation'>('assistant')
  const [debateRounds, setDebateRounds] = useState<DebateRound[]>([])
  const [streaming, setStreaming] = useState(false)
  const [topic, setTopic] = useState('')
  const [domainId, setDomainId] = useState('auto')
  const [progress, setProgress] = useState(0)
  const [currentStage, setCurrentStage] = useState('准备中')
  const [dataCount, setDataCount] = useState(0)
  const [pausedEvents, setPausedEvents] = useState<any[]>([])
  const [verdict, setVerdict] = useState<{ verdict: string; confidence: number } | null>(null)
  const [stats, setStats] = useState<DashboardStats>({ active_sessions: 0, prediction_accuracy: 87, pending_items: 0 })
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    if (activeTab === 'simulation') {
      fetchSimulationRuns(10).catch(console.error)
    }
  }, [activeTab])

  useEffect(() => {
    fetchStats().then(setStats).catch(console.error)
    const interval = setInterval(() => {
      fetchStats().then(setStats).catch(console.error)
    }, 30000)
    return () => clearInterval(interval)
  }, [])

  const toggleTheme = () => setTheme(theme === 'light' ? 'dark' : 'light')
  const toggleViewMode = () => setViewMode(viewMode === 'default' ? 'compact' : 'default')

  const processEvent = (event: any) => {
    if (event.event === 'source_complete') {
      setDataCount(prev => prev + (event.payload.count || 0))
      setProgress(prev => Math.min(prev + 15, 65))
    } else if (event.event === 'debate_round_complete') {
      const payload = event.payload
      setDebateRounds(prev => [...prev, {
        round: payload.round_number,
        role: payload.role,
        position: payload.position,
        confidence: payload.confidence,
        arguments: payload.key_arguments || []
      }])
      setCurrentStage('辩论进行中')
      setProgress(prev => Math.min(prev + 10, 90))
    } else if (event.event === 'debate_verdict') {
      const payload = event.payload
      setVerdict({
        verdict: payload.verdict || 'ACCEPTED',
        confidence: payload.confidence || 0.92
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
            setPausedEvents(prev => [...prev, event])
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
    pausedEvents.forEach(event => {
      processEvent(event)
    })
    setPausedEvents([])
    setIsPaused(false)
  }

  const handleDiscard = () => {
    setPausedEvents([])
    setIsPaused(false)
  }

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
            <button className="icon-btn" onClick={toggleViewMode} title={viewMode === 'compact' ? '默认模式' : '简洁模式'}>
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
            <button
              className={`nav-item ${activeTab === 'assistant' ? 'active' : ''}`}
              onClick={() => setActiveTab('assistant')}
            >
              <Brain size={20} />
              <span>战略助手</span>
            </button>
            <button
              className={`nav-item ${activeTab === 'debate' ? 'active' : ''}`}
              onClick={() => setActiveTab('debate')}
            >
              <MessageSquare size={20} />
              <span>辩论系统</span>
            </button>
            <button
              className={`nav-item ${activeTab === 'simulation' ? 'active' : ''}`}
              onClick={() => setActiveTab('simulation')}
            >
              <TrendingUp size={20} />
              <span>情景推演</span>
            </button>
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
          {/* Pause Control */}
          {activeTab === 'assistant' && streaming && (
            <div className="pause-control glass-card">
              <button className="pause-btn" onClick={handlePauseToggle}>
                {isPaused ? <Play size={16} /> : <Pause size={16} />}
                <span>{isPaused ? '已暂停' : '实时更新'}</span>
              </button>
              {isPaused && pausedEvents.length > 0 && (
                <div className="pause-actions">
                  <span className="pending-count">{pausedEvents.length}条待处理</span>
                  <button className="action-btn" onClick={handleResumeImmediate}>全部应用</button>
                  <button className="action-btn danger" onClick={handleDiscard}>丢弃</button>
                </div>
              )}
            </div>
          )}

          {/* Debate Panel */}
          {activeTab === 'debate' && (
            <div className="debate-panel">
              <h2 className="panel-title">多智能体辩论</h2>

              <div className="debate-rounds">
                {debateRounds.map((round, index) => (
                  <div key={index} className={`debate-round glass-card ${viewMode === 'compact' && index < debateRounds.length - 1 ? 'hidden' : ''}`}>
                    <div className="round-header">
                      <div className="round-info">
                        <span className="round-number">第 {round.round} 轮</span>
                        <span className="round-role">{round.role}</span>
                      </div>
                      <div className="confidence-bar">
                        <div className="confidence-fill" style={{ width: `${round.confidence * 100}%` }} />
                        <span className="confidence-value">{(round.confidence * 100).toFixed(0)}%</span>
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

              {/* Verdict Card */}
              {verdict && (
                <div className="verdict-card glass-card accent-border">
                  <div className="verdict-header">
                    <span className="verdict-label">最终裁决</span>
                    <span className="verdict-result">{verdict.verdict}</span>
                  </div>
                  <div className="verdict-confidence">
                    <span>置信度</span>
                    <span className="confidence-badge">{(verdict.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Assistant Panel */}
          {activeTab === 'assistant' && (
            <div className="assistant-panel">
              <h2 className="panel-title">战略助手</h2>

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
            </div>
          )}

          {/* Simulation Panel */}
          {activeTab === 'simulation' && (
            <div className="simulation-panel">
              <h2 className="panel-title">情景推演</h2>

              <div className="simulation-grid">
                <div className="sim-card glass-card">
                  <div className="sim-header">
                    <span className="sim-title">基准场景</span>
                    <span className="sim-probability">45%</span>
                  </div>
                  <p className="sim-description">基于当前趋势的标准发展路径</p>
                  <div className="sim-metrics">
                    <div className="metric">
                      <span className="metric-label">预期收益</span>
                      <span className="metric-value positive">+23%</span>
                    </div>
                    <div className="metric">
                      <span className="metric-label">风险等级</span>
                      <span className="metric-value">中</span>
                    </div>
                  </div>
                </div>

                <div className="sim-card glass-card">
                  <div className="sim-header">
                    <span className="sim-title">乐观场景</span>
                    <span className="sim-probability">30%</span>
                  </div>
                  <p className="sim-description">市场环境优于预期的发展路径</p>
                  <div className="sim-metrics">
                    <div className="metric">
                      <span className="metric-label">预期收益</span>
                      <span className="metric-value positive">+45%</span>
                    </div>
                    <div className="metric">
                      <span className="metric-label">风险等级</span>
                      <span className="metric-value">低</span>
                    </div>
                  </div>
                </div>

                <div className="sim-card glass-card">
                  <div className="sim-header">
                    <span className="sim-title">悲观场景</span>
                    <span className="sim-probability">25%</span>
                  </div>
                  <p className="sim-description">面临重大挑战的发展路径</p>
                  <div className="sim-metrics">
                    <div className="metric">
                      <span className="metric-label">预期收益</span>
                      <span className="metric-value negative">-12%</span>
                    </div>
                    <div className="metric">
                      <span className="metric-label">风险等级</span>
                      <span className="metric-value">高</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}

export default App
