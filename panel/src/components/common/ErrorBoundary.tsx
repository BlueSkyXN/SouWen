import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[SouWen] Uncaught render error:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', minHeight: '100vh', padding: 32,
          fontFamily: 'system-ui, sans-serif', color: '#333', background: '#f5f6f8',
        }}>
          <h2 style={{ marginBottom: 8 }}>页面渲染出错</h2>
          <p style={{ color: '#666', marginBottom: 16 }}>
            {this.state.error?.message || '未知错误'}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null })
              window.location.hash = '#/login'
              window.location.reload()
            }}
            style={{
              padding: '8px 20px', borderRadius: 6, border: 'none',
              background: '#3b82f6', color: '#fff', cursor: 'pointer', fontSize: 14,
            }}
          >
            重新加载
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
