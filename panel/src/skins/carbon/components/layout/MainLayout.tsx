import { useState, useCallback, useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { m, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard,
  Search,
  Database,
  Wifi,
  Settings,
  Terminal,
  LogOut,
  Menu,
  User,
} from 'lucide-react'
import { useAuthStore } from '@core/stores/authStore'
import styles from './MainLayout.module.scss'

const NAV_ITEMS = [
  { to: '/search', icon: Search, labelKey: 'nav.search' },
  { to: '/', icon: LayoutDashboard, labelKey: 'nav.dashboard' },
  { to: '/sources', icon: Database, labelKey: 'nav.sources' },
  { to: '/network', icon: Wifi, labelKey: 'nav.network' },
  { to: '/config', icon: Settings, labelKey: 'nav.config' },
]

const pageVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
}

const pageTransition = {
  type: 'spring' as const,
  stiffness: 400,
  damping: 36,
  mass: 0.8,
}

export function MainLayout() {
  const { t } = useTranslation()
  const location = useLocation()
  const logout = useAuthStore((s) => s.logout)
  const [mobileOpen, setMobileOpen] = useState(false)

  const handleLogout = useCallback(() => {
    logout()
  }, [logout])

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  return (
    <div className={styles.layout}>
      {/* ── Top Navigation Bar ── */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <button
            className={styles.hamburger}
            onClick={() => setMobileOpen((o) => !o)}
            aria-label={t('nav.menu', 'Menu')}
          >
            <Menu size={18} />
          </button>

          <div className={styles.brand}>
            <span className={styles.brandIcon}>
              <Terminal size={20} />
            </span>
            SouWen<span className={styles.brandDot}>.</span>
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
                <span className={styles.navIcon}>
                  <item.icon size={14} />
                </span>
                {t(item.labelKey)}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className={styles.headerRight}>
          <div className={styles.statusBadge}>
            <span className={styles.statusDot} />
            SYS.ONLINE
          </div>

          <div className={styles.avatar}>
            <User size={14} />
          </div>

          <button className={styles.logoutBtn} onClick={handleLogout}>
            <LogOut size={14} />
            <span>{t('nav.logout')}</span>
          </button>
        </div>
      </header>

      {/* ── Mobile Overlay ── */}
      <AnimatePresence>
        {mobileOpen && (
          <m.div
            className={styles.overlay}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={() => setMobileOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* ── Mobile Drawer ── */}
      <AnimatePresence>
        {mobileOpen && (
          <m.div
            className={styles.mobileDrawer}
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ type: 'spring' as const, stiffness: 400, damping: 36 }}
          >
            <div className={styles.drawerBrand}>
              <Terminal size={18} />
              SouWen.
            </div>
            <nav className={styles.drawerNav}>
              {NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `${styles.drawerItem} ${isActive ? styles.active : ''}`
                  }
                >
                  <item.icon size={16} />
                  {t(item.labelKey)}
                </NavLink>
              ))}
            </nav>
          </m.div>
        )}
      </AnimatePresence>

      {/* ── Main Content ── */}
      <main className={styles.main}>
        <AnimatePresence mode="wait">
          <m.div
            key={location.pathname}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={pageTransition}
          >
            <Outlet />
          </m.div>
        </AnimatePresence>
      </main>
    </div>
  )
}
