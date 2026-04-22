/**
 * 导出文件 - skin 公开接口
 *
 * 文件用途：导出 skin 的公开组件、页面、路由和配置，供核心系统集成
 *
 * 导出项清单：
 *   AppShell - 主布局容器（来自 MainLayout）
 *   LoginPage - 登录页面
 *   skinRoutes - 应用内容区路由定义
 *   skinConfig - 主题配置元数据
 *   ErrorBoundary - 错误捕获边界组件
 *   ToastContainer - 全局消息提示容器
 *   Spinner - 通用加载微调器
 *   bootstrap() - Skin 初始化函数，应用启动时调用以恢复主题偏好
 */

export { MainLayout as AppShell } from './components/layout/MainLayout'
export { LoginPage } from './pages/LoginPage'
export { skinRoutes } from './routes'
export { skinConfig } from './skin.config'
export { ErrorBoundary } from './components/common/ErrorBoundary'
export { ToastContainer } from './components/common/Toast'
export { Spinner } from './components/common/Spinner'

import { useSkinStore } from './stores/skinStore'

/**
 * Skin 引导程序 - 应用启动时调用
 * 
 * 从 localStorage 恢复用户的主题和配色方案偏好
 */
export function bootstrap() {
  useSkinStore.getState().loadSkin()
}
