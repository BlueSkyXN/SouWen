import { Component, type ReactNode } from 'react'
import i18n from '@core/i18n'

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
          fontFamily: '"JetBrains Mono", "Fira Code", monospace', color: 'var(--text-secondary, #a1a1aa)',
          background: 'var(--bg, #09090b)',
        }}>
          <h2 style={{ marginBottom: 8, color: 'var(--error, #f43f5e)', fontWeight: 700 }}>
            [ERR] {i18n.t('common.pageRenderError')}
          </h2>
          <p style={{ color: 'var(--text-muted, #71717a)', marginBottom: 16, fontFamily: 'monospace' }}>
            {this.state.error?.message || i18n.t('common.unknownError')}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null })
              window.location.hash = '#/login'
              window.location.reload()
            }}
            style={{
              padding: '8px 20px', border: '1px solid var(--accent, #3b82f6)',
              background: 'var(--accent, #3b82f6)', color: '#fff', cursor: 'pointer',
              fontSize: 13, fontFamily: 'monospace', textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}
          >
            {i18n.t('common.reload')}
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
