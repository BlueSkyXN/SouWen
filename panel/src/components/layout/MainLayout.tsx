import { useState, useCallback, useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  LayoutDashboard,
  Search,
  Database,
  Settings,
  ChevronsLeft,
  ChevronsRight,
  Menu,
  Moon,
  Sun,
  LogOut,
} from 'lucide-react'
import { useAuthStore } from '../../stores/authStore'
import { useThemeStore } from '../../stores/themeStore'
import styles from './MainLayout.module.scss'

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, labelKey: 'nav.dashboard' },
  { to: '/search', icon: Search, labelKey: 'nav.search' },
  { to: '/sources', icon: Database, labelKey: 'nav.sources' },
  { to: '/config', icon: Settings, labelKey: 'nav.config' },
]

const PAGE_TITLE_KEYS: Record<string, string> = {
  '/': 'nav.dashboard',
  '/search': 'nav.search',
  '/sources': 'nav.sources',
  '/config': 'nav.config',
}

export function MainLayout() {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const logout = useAuthStore((s) => s.logout)
  const version = useAuthStore((s) => s.version)
  const { theme, toggleTheme } = useThemeStore()

  const pageTitleKey = PAGE_TITLE_KEYS[location.pathname] ?? 'nav.dashboard'

  const handleLogout = useCallback(() => {
    logout()
  }, [logout])

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  return (
    <div className={styles.layout}>
      {mobileOpen && (
        <div className={styles.overlay} onClick={() => setMobileOpen(false)} />
      )}

      <m.aside
        className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''} ${mobileOpen ? styles.mobileOpen : ''}`}
        animate={{ width: collapsed ? 64 : 220 }}
        transition={{ duration: 0.2, ease: 'easeInOut' }}
      >
        <div className={styles.brand}>
          <span className={styles.logo}>
            <Search size={22} />
          </span>
          <span className={styles.brandText}>{t('app.name')}</span>
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
              <span className={styles.icon}>
                <item.icon size={18} />
              </span>
              <span className={styles.label}>{t(item.labelKey)}</span>
            </NavLink>
          ))}
        </nav>

        <div className={styles.footer}>
          {version && <div className={styles.version}>v{version}</div>}
          <button
            className={styles.collapseBtn}
            onClick={() => setCollapsed((c) => !c)}
          >
            <span>{collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}</span>
            <span className={styles.label}>{t('nav.collapse')}</span>
          </button>
        </div>
      </m.aside>

      <div className={`${styles.main} ${collapsed ? styles.mainCollapsed : ''}`}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <button
              className={styles.hamburger}
              onClick={() => setMobileOpen((o) => !o)}
            >
              <Menu size={20} />
            </button>
            <h2>{t(pageTitleKey)}</h2>
          </div>
          <div className={styles.headerRight}>
            <span className={styles.connBadge}>
              <span className={styles.connDot} />
              {t('common.connected')}
            </span>
            <button className={styles.themeBtn} onClick={toggleTheme}>
              {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            <button className={styles.logoutBtn} onClick={handleLogout}>
              <LogOut size={16} />
              <span>{t('nav.logout')}</span>
            </button>
          </div>
        </header>

        <main className={styles.content}>
          <m.div
            key={location.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <Outlet />
          </m.div>
        </main>
      </div>
    </div>
  )
}
