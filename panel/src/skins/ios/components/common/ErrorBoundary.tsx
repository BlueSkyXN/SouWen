/**
 * 文件用途：iOS 皮肤的错误边界组件，捕获和处理子组件抛出的 React 错误
 *
 * 组件/函数清单：
 *   ErrorBoundary（类）
 *     - 功能：React Error Boundary，捕获子组件渲染时的异常，显示友好的错误提示界面
 *     - Props 属性：children (ReactNode) 被包裹的子组件
 *     - State 状态：hasError (boolean) 是否发生错误, error (Error | null) 错误对象
 *     - 关键方法：getDerivedStateFromError 静态方法用于捕获错误, componentDidCatch 生命周期钩子记录错误日志
 *     - 使用场景：应用根组件包裹，防止单点错误导致整个应用崩溃
 *
 * 模块依赖：
 *   - react: Component 类基础，ReactNode 类型定义
 *   - @core/i18n: 国际化文本翻译
 */

import { Component, type ReactNode } from 'react'
import i18n from '@core/i18n'

/**
 * ErrorBoundary 组件的 Props 接口
 * @property {ReactNode} children - 被包裹的子组件
 */
interface Props {
  children: ReactNode
}

/**
 * ErrorBoundary 组件的 State 接口
 * @property {boolean} hasError - 标记是否发生渲染错误
 * @property {Error | null} error - 捕获的错误对象
 */
interface State {
  hasError: boolean
  error: Error | null
}

/**
 * ErrorBoundary 类 - React 错误边界，捕获并处理子树渲染错误
 * 当子组件发生未捕获异常时，显示降级 UI 并提供重新加载选项
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  // 静态生命周期方法，用于在错误发生时更新 state
  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  // 错误生命周期钩子，用于错误处理（如记录日志）
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[SouWen] Uncaught render error:', error, info.componentStack)
  }

  // 渲染方法：当发生错误时显示错误提示界面，否则正常渲染子组件
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
