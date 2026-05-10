import { useState, useEffect } from 'react'
import { Moon, Sun, Brain, MessageSquare, TrendingUp, Pause, Play, Minimize2, Maximize2 } from 'lucide-react'
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
  const [debateRounds, setDebateRounds] = useState<DebateRound[]>([
    {
      round: 1,
      role: '支持方',
      position: '基于当前市场趋势和技术发展，该战略具有可行性',
      confidence: 0.85,
      arguments: ['市场需求持续增长', '技术成熟度达标', '竞争优势明显']
    },
    {
      round: 2,
      role: '质询方',
      position: '存在潜在风险需要谨慎评估',
      confidence: 0.72,
      arguments: ['市场波动性较大', '资源投入需求高', '时间窗口有限']
    }
  ])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(theme === 'light' ? 'dark' : 'light')
  const toggleViewMode = () => setViewMode(viewMode === 'default' ? 'compact' : 'default')

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
              <span className="stat-value">12</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">预测准确率</span>
              <span className="stat-value">87%</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">待处理项</span>
              <span className="stat-value">5</span>
            </div>
          </div>
        </aside>

        {/* Content Area */}
        <section className="content-area">
          {/* Pause Control */}
          {activeTab === 'assistant' && (
            <div className="pause-control glass-card">
              <button className="pause-btn" onClick={() => setIsPaused(!isPaused)}>
                {isPaused ? <Play size={16} /> : <Pause size={16} />}
                <span>{isPaused ? '已暂停' : '实时更新'}</span>
              </button>
              {isPaused && (
                <div className="pause-actions">
                  <span className="pending-count">12条待处理</span>
                  <button className="action-btn">全部应用</button>
                  <button className="action-btn">逐条播放</button>
                  <button className="action-btn danger">丢弃</button>
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
              <div className="verdict-card glass-card accent-border">
                <div className="verdict-header">
                  <span className="verdict-label">最终裁决</span>
                  <span className="verdict-result">ACCEPTED</span>
                </div>
                <div className="verdict-confidence">
                  <span>置信度</span>
                  <span className="confidence-badge">92%</span>
                </div>
              </div>
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
                />
                <div className="input-actions">
                  <select className="domain-select">
                    <option>自动识别</option>
                    <option>企业战略</option>
                    <option>军事分析</option>
                  </select>
                  <button className="run-btn">执行分析</button>
                </div>
              </div>

              <div className="process-card glass-card">
                <div className="process-header">
                  <span className="process-stage">数据采集</span>
                  <span className="process-status">进行中</span>
                </div>
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: '65%' }} />
                </div>
                <div className="process-details">
                  <div className="detail-item">
                    <span className="detail-icon">🔍</span>
                    <span>正在搜索公共来源...</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-icon">📊</span>
                    <span>已采集 127 条数据</span>
                  </div>
                </div>
              </div>
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
