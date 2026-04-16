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
          fontFamily: 'var(--font-body, -apple-system, BlinkMacSystemFont, sans-serif)',
          color: 'var(--text-secondary, #1c1c1e)',
          background: 'var(--bg, #f2f2f7)',
        }}>
          <h2 style={{
            marginBottom: 8, color: 'var(--error, #ff3b30)',
            fontWeight: 600, fontSize: '21px', lineHeight: 1.19,
          }}>
            {i18n.t('common.pageRenderError')}
          </h2>
          <p style={{
            color: 'var(--text-muted, #8e8e93)', marginBottom: 20,
            fontSize: '14px', lineHeight: 1.43,
          }}>
            {this.state.error?.message || i18n.t('common.unknownError')}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null })
              window.location.hash = '#/login'
              window.location.reload()
            }}
            style={{
              padding: '8px 20px', border: 'none', borderRadius: '10px',
              background: 'var(--accent, #007aff)', color: '#fff', cursor: 'pointer',
              fontSize: '17px', fontFamily: 'var(--font-body, -apple-system, sans-serif)',
              fontWeight: 400,
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
