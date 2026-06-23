import React from 'react'

interface ErrorBoundaryProps {
  children: React.ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  showDetails: boolean
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null, showDetails: false }
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('[ErrorBoundary] Caught error:', error, errorInfo)
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, showDetails: false })
  }

  toggleDetails = () => {
    this.setState((prev) => ({ showDetails: !prev.showDetails }))
  }

  render() {
    if (this.state.hasError) {
      const canShowDetails = import.meta.env.DEV

      return (
        <div className="app-shell flex min-h-screen items-center justify-center p-6">
          <div className="cockpit-panel w-full max-w-lg p-8">
            {/* Icon */}
            <div className="mb-6 flex justify-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-[18px] border border-red-500/20 bg-red-500/10">
                <svg
                  className="h-6 w-6 text-red-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
                  />
                </svg>
              </div>
            </div>

            {/* Title & message */}
            <h2 className="mb-2 text-center text-xl font-semibold text-slate-100">
              页面出错了
            </h2>
            <p className="editorial-copy mb-6 text-center text-sm leading-6">
              应用遇到了意外错误，请尝试刷新页面或点击重试。
            </p>

            {canShowDetails && (
              <div className="mb-6">
                <button
                  onClick={this.toggleDetails}
                  className="flex w-full items-center gap-2 text-sm text-slate-400 transition-colors hover:text-slate-300"
                >
                  <svg
                    className={`w-4 h-4 transition-transform ${this.state.showDetails ? 'rotate-90' : ''}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2}
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
                  </svg>
                  错误详情
                </button>

                {this.state.showDetails && (
                  <div className="mt-3 max-h-48 overflow-auto rounded-[18px] border border-slate-700 bg-slate-900/45 p-4">
                    <p className="mono-data whitespace-pre-wrap break-all text-xs text-red-400">
                      {this.state.error?.message}
                    </p>
                    {this.state.error?.stack && (
                      <p className="mono-data mt-2 whitespace-pre-wrap break-all text-xs text-slate-500">
                        {this.state.error.stack}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Action buttons */}
            <div className="flex justify-center">
              <button
                onClick={this.handleRetry}
                className="primary-ink-button px-6 py-2.5 text-sm font-medium transition"
              >
                重试
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
