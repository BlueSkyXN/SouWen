import { useEffect, useState } from 'react'
import { HashRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { LazyMotion, domAnimation, AnimatePresence } from 'framer-motion'
import { useAuthStore } from '@core/stores/authStore'
import { getActiveSkin } from '@core/skin-registry'

function AuthGuard({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AnimatedRoutes() {
  const location = useLocation()
  const { AppShell, LoginPage, skinRoutes } = getActiveSkin().skinModule
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <AuthGuard>
              <AppShell />
            </AuthGuard>
          }
        >
          {skinRoutes}
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  )
}

export default function App() {
  const { ToastContainer, Spinner } = getActiveSkin().skinModule
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    loadFromStorage()
    // 若已登录但 token 已过期，自动登出，避免使用陈旧凭证
    const state = useAuthStore.getState()
    if (state.isAuthenticated && state.isExpired()) {
      state.logout()
    }
    setReady(true)
  }, [loadFromStorage])

  if (!ready) return <Spinner size="lg" />

  return (
    <LazyMotion features={domAnimation}>
      <HashRouter>
        <ToastContainer />
        <AnimatedRoutes />
      </HashRouter>
    </LazyMotion>
  )
}
