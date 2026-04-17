/**
 * 文件用途：SouWen 应用主组件，负责路由管理、认证守卫、主题切换与动画处理
 *
 * 组件/函数清单：
 *     AuthGuard（函数组件）
 *         - 功能：认证守卫，检查用户是否已登录；未登录时重定向到登录页
 *         - 输入：children React.ReactNode 要保护的子组件内容
 *         - 输出：已认证时返回子组件，否则返回 Navigate 重定向指令
 *
 *     AnimatedRoutes（函数组件）
 *         - 功能：路由配置与动画管理，使用 Framer Motion 提供页面过渡动画
 *         - 输入：无
 *         - 输出：Routes 路由组件，包含登录、应用壳层、皮肤路由及通配符重定向
 *
 *     App（函数组件，默认导出）
 *         - 功能：应用根组件，初始化认证状态、皮肤系统、过期令牌检测与加载状态
 *         - 输入：无
 *         - 输出：LazyMotion 包装的完整应用组件树
 *         - 关键变量：ready boolean 应用加载完成标志
 *
 * 模块依赖：
 *     - react: 核心 React 库，用于组件与状态管理
 *     - react-router-dom: 客户端路由管理（HashRouter、Routes、Navigate）
 *     - framer-motion: 动画库（LazyMotion、AnimatePresence）
 *     - @core/stores/authStore: 认证全局状态存储
 *     - @core/skin-registry: 皮肤主题注册与管理系统
 */

import { useEffect, useState } from 'react'
import { HashRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { LazyMotion, domAnimation, AnimatePresence } from 'framer-motion'
import { useAuthStore } from '@core/stores/authStore'
import { getActiveSkin } from '@core/skin-registry'

/**
 * AuthGuard 组件：认证保护装饰器
 * 检查当前用户是否已认证；未认证时自动重定向到登录页
 */
function AuthGuard({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

/**
 * AnimatedRoutes 组件：动画路由管理
 * 使用 Framer Motion 的 AnimatePresence 包装路由，为页面切换提供平滑的过渡动画
 */
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

/**
 * App 主组件
 * 负责应用初始化：加载认证状态、检测令牌过期、管理全局加载状态与主题系统
 *
 * 关键逻辑：
 *   - 挂载时从本地存储加载认证凭证
 *   - 若已认证但令牌过期（超过 TTL），自动登出以防使用陈旧凭证
 *   - 使用 ready 状态控制加载期间的 UI 显示
 *   - 用 LazyMotion 包装以优化 Framer Motion 性能（按需加载动画库）
 */
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
