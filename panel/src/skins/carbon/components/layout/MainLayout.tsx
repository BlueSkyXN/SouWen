import { useState, useCallback, useEffect, useRef } from 'react'
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
  Layers,
  Moon,
  Sun,
  Check,
} from 'lucide-react'
import { useAuthStore } from '@core/stores/authStore'
import { useSkinStore } from '../../stores/skinStore'
import { skinConfig } from '../../skin.config'
import { isSingleSkin, listSkinIds, getSkinOrDefault } from '@core/skin-registry'
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
  const { mode, toggleMode, scheme, setScheme } = useSkinStore()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [skinPaletteOpen, setSkinPaletteOpen] = useState(false)
  const [schemePaletteOpen, setSchemePaletteOpen] = useState(false)
  const skinPaletteRef = useRef<HTMLDivElement>(null)
  const schemePaletteRef = useRef<HTMLDivElement>(null)

  const handleLogout = useCallback(() => {
    logout()
  }, [logout])

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  // Close palettes on outside click or Escape
  useEffect(() => {
    if (!skinPaletteOpen && !schemePaletteOpen) return
    const handleClick = (e: MouseEvent) => {
      if (skinPaletteOpen && skinPaletteRef.current && !skinPaletteRef.current.contains(e.target as Node)) {
        setSkinPaletteOpen(false)
      }
      if (schemePaletteOpen && schemePaletteRef.current && !schemePaletteRef.current.contains(e.target as Node)) {
        setSchemePaletteOpen(false)
      }
    }
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSkinPaletteOpen(false)
        setSchemePaletteOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [skinPaletteOpen, schemePaletteOpen])

  const currentSkinId = document.documentElement.getAttribute('data-skin') || 'carbon'

  const handleSkinSwitch = (nextId: string) => {
    if (nextId === currentSkinId) {
      setSkinPaletteOpen(false)
      return
    }
    const nextSkin = getSkinOrDefault(nextId)
    localStorage.setItem('souwen_skin', nextId)
    localStorage.setItem('souwen_mode', nextSkin.skinModule.skinConfig.defaultMode)
    localStorage.setItem('souwen_scheme', nextSkin.skinModule.skinConfig.defaultScheme)
    window.location.reload()
  }

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

          {/* Mode toggle */}
          <button
            className={styles.toolBtn}
            onClick={toggleMode}
            aria-label={mode === 'dark' ? t('common.lightMode', 'Light Mode') : t('common.darkMode', 'Dark Mode')}
            title={mode === 'dark' ? t('common.lightMode', 'Light Mode') : t('common.darkMode', 'Dark Mode')}
          >
            {mode === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>

          {/* Scheme palette */}
          <div className={styles.paletteWrap} ref={schemePaletteRef}>
            <button
              className={styles.toolBtn}
              onClick={() => { setSchemePaletteOpen((o) => !o); setSkinPaletteOpen(false) }}
              aria-label={t('theme.label')}
              aria-expanded={schemePaletteOpen}
              aria-haspopup="listbox"
            >
              <span className={styles.schemeDot} style={{ background: skinConfig.schemes.find((s) => s.id === scheme)?.dotColor }} />
            </button>
            <AnimatePresence>
              {schemePaletteOpen && (
                <m.div
                  className={styles.palette}
                  role="listbox"
                  initial={{ opacity: 0, y: -4, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -4, scale: 0.95 }}
                  transition={{ type: 'spring' as const, stiffness: 500, damping: 30 }}
                >
                  <div className={styles.paletteTitle}>{t('theme.label')}</div>
                  {skinConfig.schemes.map((s) => (
                    <button
                      key={s.id}
                      role="option"
                      aria-selected={scheme === s.id}
                      className={`${styles.paletteItem} ${scheme === s.id ? styles.paletteActive : ''}`}
                      onClick={() => { setScheme(s.id); setSchemePaletteOpen(false) }}
                    >
                      <span className={styles.paletteDot} style={{ background: s.dotColor }} />
                      <span className={styles.paletteName}>{t(s.labelKey)}</span>
                      {scheme === s.id && <Check size={12} className={styles.paletteCheck} />}
                    </button>
                  ))}
                </m.div>
              )}
            </AnimatePresence>
          </div>

          {/* Skin switcher */}
          {!isSingleSkin() && (
            <div className={styles.paletteWrap} ref={skinPaletteRef}>
              <button
                className={styles.skinSwitcherBtn}
                onClick={() => { setSkinPaletteOpen((o) => !o); setSchemePaletteOpen(false) }}
                aria-label={t('skin.switchSkin')}
                aria-expanded={skinPaletteOpen}
                aria-haspopup="listbox"
              >
                <Layers size={14} />
                <span>{t('skin.switchSkin')}</span>
              </button>
              <AnimatePresence>
                {skinPaletteOpen && (
                  <m.div
                    className={styles.palette}
                    role="listbox"
                    initial={{ opacity: 0, y: -4, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -4, scale: 0.95 }}
                    transition={{ type: 'spring' as const, stiffness: 500, damping: 30 }}
                  >
                    <div className={styles.paletteTitle}>{t('skin.switchSkin')}</div>
                    {listSkinIds().map((id) => {
                      const skin = getSkinOrDefault(id)
                      const cfg = skin.skinModule.skinConfig
                      return (
                        <button
                          key={id}
                          role="option"
                          aria-selected={id === currentSkinId}
                          className={`${styles.paletteItem} ${id === currentSkinId ? styles.paletteActive : ''}`}
                          onClick={() => handleSkinSwitch(id)}
                        >
                          <span className={styles.paletteName}>{t(cfg.labelKey)}</span>
                          <span className={styles.paletteDesc}>{t(cfg.descriptionKey)}</span>
                          {id === currentSkinId && <Check size={12} className={styles.paletteCheck} />}
                        </button>
                      )
                    })}
                  </m.div>
                )}
              </AnimatePresence>
            </div>
          )}

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
