import { useEffect } from 'react'
import { HashRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { LazyMotion, domAnimation, AnimatePresence } from 'framer-motion'
import { useAuthStore } from './stores/authStore'
import { useThemeStore } from './stores/themeStore'
import { MainLayout } from './components/layout/MainLayout'
import { ToastContainer } from './components/common/Toast'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { SearchPage } from './pages/SearchPage'
import { SourcesPage } from './pages/SourcesPage'
import { ConfigPage } from './pages/ConfigPage'
import './styles/global.scss'

function AuthGuard({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AnimatedRoutes() {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <AuthGuard>
              <MainLayout />
            </AuthGuard>
          }
        >
          <Route path="/" element={<DashboardPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/sources" element={<SourcesPage />} />
          <Route path="/config" element={<ConfigPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  )
}

export default function App() {
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage)
  const loadTheme = useThemeStore((s) => s.loadTheme)

  useEffect(() => {
    loadTheme()
    loadFromStorage()
  }, [loadFromStorage, loadTheme])

  return (
    <LazyMotion features={domAnimation}>
      <HashRouter>
        <ToastContainer />
        <AnimatedRoutes />
      </HashRouter>
    </LazyMotion>
  )
}
