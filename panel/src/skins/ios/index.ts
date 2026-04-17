/**
 * 文件用途：iOS 皮肤的导出入口，提供皮肤配置和初始化函数
 */

export { MainLayout as AppShell } from './components/layout/MainLayout'
export { LoginPage } from './pages/LoginPage'
export { skinRoutes } from './routes'
export { skinConfig } from './skin.config'
export { ErrorBoundary } from './components/common/ErrorBoundary'
export { ToastContainer } from './components/common/Toast'
export { Spinner } from './components/common/Spinner'

import { useSkinStore } from './stores/skinStore'
export function bootstrap() {
  useSkinStore.getState().loadSkin()
}
