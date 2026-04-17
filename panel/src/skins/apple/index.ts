/**
 * 文件用途：Apple 皮肤的导出接口，统一对外暴露该皮肤的所有关键组件、配置和启动函数
 *
 * 导出清单：
 *   AppShell - 主布局组件（来自 MainLayout）
 *   LoginPage - 登录页面组件
 *   skinRoutes - 该皮肤的路由配置
 *   skinConfig - 该皮肤的配置对象
 *   ErrorBoundary - 错误边界组件
 *   ToastContainer - 消息提示容器组件
 *   Spinner - 加载旋转圈组件
 *   bootstrap() - 皮肤启动函数，在应用初始化时调用，加载持久化的皮肤配置
 *
 * 使用场景：
 *   应用通过动态导入该文件中的导出，运行时加载特定皮肤的组件和配置
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
 * 皮肤启动函数 - 在应用初始化时调用
 * 从 localStorage 恢复用户之前保存的皮肤主题和配色方案，应用到 DOM 根元素上
 */
export function bootstrap() {
  useSkinStore.getState().loadSkin()
}
