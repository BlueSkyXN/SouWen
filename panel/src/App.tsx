import { useEffect, useState } from 'react'
import { HashRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { LazyMotion, domAnimation, AnimatePresence } from 'framer-motion'
import { useAuthStore } from '@core/stores/authStore'
import { useSkinStore } from '@skin/stores/skinStore'
import { AppShell, LoginPage, skinRoutes } from '@skin'
import { ToastContainer } from '@skin/components/common/Toast'
import { Spinner } from '@skin/components/common/Spinner'
import '@skin/styles/global.scss'

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
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage)
  const loadSkin = useSkinStore((s) => s.loadSkin)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    loadSkin()
    loadFromStorage()
    setReady(true)
  }, [loadFromStorage, loadSkin])

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
