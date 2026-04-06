import { useState, useCallback, useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { useThemeStore } from '../../stores/themeStore'
import styles from './MainLayout.module.scss'

const NAV_ITEMS = [
  { to: '/', icon: '📊', label: '仪表盘' },
  { to: '/search', icon: '🔍', label: '搜索' },
  { to: '/sources', icon: '📚', label: '数据源' },
  { to: '/config', icon: '⚙️', label: '配置' },
]

const PAGE_TITLES: Record<string, string> = {
  '/': '仪表盘',
  '/search': '搜索',
  '/sources': '数据源',
  '/config': '配置',
}

export function MainLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const logout = useAuthStore((s) => s.logout)
  const version = useAuthStore((s) => s.version)
  const { theme, toggleTheme } = useThemeStore()

  const pageTitle = PAGE_TITLES[location.pathname] ?? '管理面板'

  const handleLogout = useCallback(() => {
    logout()
  }, [logout])

  /* close mobile sidebar on navigate */
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  return (
    <div className={styles.layout}>
      {/* Overlay */}
      {mobileOpen && (
        <div className={styles.overlay} onClick={() => setMobileOpen(false)} />
      )}

      {/* Sidebar */}
      <aside
        className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''} ${mobileOpen ? styles.mobileOpen : ''}`}
      >
        <div className={styles.brand}>
          <span className={styles.logo}>🔍</span>
          <span className={styles.brandText}>SouWen 搜文</span>
        </div>

        <nav className={styles.nav}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `${styles.navItem} ${isActive ? styles.active : ''}`
              }
            >
              <span className={styles.icon}>{item.icon}</span>
              <span className={styles.label}>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className={styles.footer}>
          {version && (
            <div className={styles.version}>v{version}</div>
          )}
          <button
            className={styles.collapseBtn}
            onClick={() => setCollapsed((c) => !c)}
          >
            <span>{collapsed ? '▶' : '◀'}</span>
            <span className={styles.label}>收起</span>
          </button>
        </div>
      </aside>

      {/* Main Area */}
      <div className={`${styles.main} ${collapsed ? styles.mainCollapsed : ''}`}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <button
              className={styles.hamburger}
              onClick={() => setMobileOpen((o) => !o)}
            >
              ☰
            </button>
            <h2>{pageTitle}</h2>
          </div>
          <div className={styles.headerRight}>
            <span className={styles.connBadge}>
              <span className={styles.connDot} />
              已连接
            </span>
            <button className={styles.themeBtn} onClick={toggleTheme}>
              {theme === 'light' ? '🌙' : '☀️'}
            </button>
            <button className={styles.logoutBtn} onClick={handleLogout}>
              退出
            </button>
          </div>
        </header>

        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
