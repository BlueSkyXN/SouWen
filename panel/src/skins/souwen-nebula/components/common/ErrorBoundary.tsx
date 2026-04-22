/**
 * 错误边界组件 - React 渲染错误捕获
 *
 * 文件用途：类组件错误边界，捕获子组件树中的渲染错误，显示降级 UI 并提供重新加载功能
 *
 * 类/方法清单：
 *   ErrorBoundary（React.Component<Props, State>）
 *     - 职责：捕获并处理渲染阶段的错误
 *     - State: hasError (boolean), error (Error | null)
 *
 *   getDerivedStateFromError(error: Error) -> State
 *     - 功能：在捕获到错误时更新状态，触发 UI 降级
 *     - 返回值：{ hasError: true, error }
 *
 *   componentDidCatch(error: Error, info: ErrorInfo)
 *     - 功能：在错误被捕获后的副作用处理（日志记录）
 *     - 日志信息：包括原始错误和组件栈追踪
 *
 *   render()
 *     - 功能：返回降级 UI（包含重新加载按钮）或正常渲染子组件
 */

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
    // 捕获错误后立即更新状态，触发 UI 降级
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // 记录错误日志以便调试
    console.error('[SouWen] Uncaught render error:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        // 错误降级 UI - 中心显示错误信息和重新加载按钮
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', minHeight: '100vh', padding: 32,
          fontFamily: 'system-ui, sans-serif', color: '#333', background: '#f5f6f8',
        }}>
          <h2 style={{ marginBottom: 8 }}>{i18n.t('common.pageRenderError')}</h2>
          <p style={{ color: '#666', marginBottom: 16 }}>
            {this.state.error?.message || i18n.t('common.unknownError')}
          </p>
          <button
            onClick={() => {
              // 重置错误状态并重新加载页面，返回登录页面
              this.setState({ hasError: false, error: null })
              window.location.hash = '#/login'
              window.location.reload()
            }}
            style={{
              padding: '8px 20px', borderRadius: 6, border: 'none',
              background: '#3b82f6', color: '#fff', cursor: 'pointer', fontSize: 14,
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
