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
