import { useState, useCallback, useEffect, useRef } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { m, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard,
  Search,
  Database,
  Settings,
  Globe,
  ChevronsLeft,
  ChevronsRight,
  Menu,
  Moon,
  Sun,
  LogOut,
  Palette,
  Check,
  Layers,
} from 'lucide-react'
import { useAuthStore } from '@core/stores/authStore'
import { useSkinStore } from '../../stores/skinStore'
import { skinConfig } from '../../skin.config'
import { getSkinOrDefault, isSingleSkin, listSkinIds } from '@core/skin-registry'
import styles from './MainLayout.module.scss'

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, labelKey: 'nav.dashboard' },
  { to: '/search', icon: Search, labelKey: 'nav.search' },
  { to: '/sources', icon: Database, labelKey: 'nav.sources' },
  { to: '/network', icon: Globe, labelKey: 'nav.network' },
  { to: '/config', icon: Settings, labelKey: 'nav.config' },
]

const PAGE_TITLE_KEYS: Record<string, string> = {
  '/': 'nav.dashboard',
  '/search': 'nav.search',
  '/sources': 'nav.sources',
  '/network': 'nav.network',
  '/config': 'nav.config',
}

const pageVariants = {
  initial: { opacity: 0, y: 12, scale: 0.995 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: -8, scale: 0.995 },
}

const pageTransition = {
  type: 'spring' as const,
  stiffness: 380,
  damping: 34,
  mass: 0.8,
}

const overlayVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
}

const drawerVariants = {
  closed: { x: '-100%' },
  open: { x: 0 },
}

const drawerTransition = {
  type: 'spring' as const,
  stiffness: 400,
  damping: 36,
  mass: 0.8,
}

export function MainLayout() {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const logout = useAuthStore((s) => s.logout)
  const version = useAuthStore((s) => s.version)
  const { mode, toggleMode, scheme, setScheme } = useSkinStore()
  const [themePaletteOpen, setThemePaletteOpen] = useState(false)
  const [skinPaletteOpen, setSkinPaletteOpen] = useState(false)
  const paletteRef = useRef<HTMLDivElement>(null)
  const skinPaletteRef = useRef<HTMLDivElement>(null)

  const pageTitleKey = PAGE_TITLE_KEYS[location.pathname] ?? 'nav.dashboard'

  const THEME_DOTS = Object.fromEntries(
    skinConfig.schemes.map((s) => [s.id, s.dotColor])
  ) as Record<string, string>

  const currentSkinId = document.documentElement.getAttribute('data-skin') || 'souwen-classic'

  // Close palettes on outside click or Escape
  useEffect(() => {
    if (!themePaletteOpen && !skinPaletteOpen) return
    const handleClick = (e: MouseEvent) => {
      if (themePaletteOpen && paletteRef.current && !paletteRef.current.contains(e.target as Node)) {
        setThemePaletteOpen(false)
      }
      if (skinPaletteOpen && skinPaletteRef.current && !skinPaletteRef.current.contains(e.target as Node)) {
        setSkinPaletteOpen(false)
      }
    }
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setThemePaletteOpen(false)
        setSkinPaletteOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [themePaletteOpen, skinPaletteOpen])

  const handleLogout = useCallback(() => {
    logout()
  }, [logout])

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

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

  const sidebarContent = (
    <>
      <div className={styles.brand}>
        <span className={styles.logo}>
          <Search size={22} />
        </span>
        <span className={styles.brandText}>{t('app.name')}</span>
      </div>
      <div className={styles.brandSeparator} />

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
        <a
          className={styles.authorLink}
          href="https://github.com/BlueSkyXN/SouWen"
          target="_blank"
          rel="noopener noreferrer"
        >
          @BlueSkyXN · GPLv3
        </a>
        <button
          className={styles.collapseBtn}
          onClick={() => setCollapsed((c) => !c)}
        >
          <span className={styles.collapseIcon}>
            {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
          </span>
          <span className={styles.label}>{t('nav.collapse')}</span>
        </button>
      </div>
    </>
  )

  return (
    <div className={styles.layout}>
      {/* Mobile overlay + drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <m.div
            className={styles.overlay}
            variants={overlayVariants}
            initial="hidden"
            animate="visible"
            exit="hidden"
            transition={{ duration: 0.25 }}
            onClick={() => setMobileOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Desktop sidebar */}
      <aside
        className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''} ${styles.desktopOnly}`}
      >
        {sidebarContent}
      </aside>

      {/* Mobile drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <m.aside
            className={`${styles.sidebar} ${styles.mobileDrawer}`}
            variants={drawerVariants}
            initial="closed"
            animate="open"
            exit="closed"
            transition={drawerTransition}
          >
            {sidebarContent}
          </m.aside>
        )}
      </AnimatePresence>

      <div className={`${styles.main} ${collapsed ? styles.mainCollapsed : ''}`}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <button
              className={styles.hamburger}
              onClick={() => setMobileOpen((o) => !o)}
              aria-label={t('nav.menu', 'Menu')}
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
            <button
              className={styles.themeBtn}
              onClick={toggleMode}
              aria-label={mode === 'light' ? t('common.darkMode') : t('common.lightMode')}
            >
              {mode === 'light' ? <Moon size={16} /> : <Sun size={16} />}
            </button>
            <div className={styles.themePaletteWrap} ref={paletteRef}>
              <button
                className={styles.themeBtn}
                onClick={() => { setThemePaletteOpen((o) => !o); setSkinPaletteOpen(false) }}
                aria-label={t('theme.label')}
                aria-expanded={themePaletteOpen}
                aria-haspopup="listbox"
              >
                <Palette size={16} />
              </button>
              <AnimatePresence>
                {themePaletteOpen && (
                  <m.div
                    className={styles.themePalette}
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
                        onClick={() => { setScheme(s.id); setThemePaletteOpen(false) }}
                      >
                        <span
                          className={styles.paletteDot}
                          style={{ background: THEME_DOTS[s.id] }}
                        />
                        <span className={styles.paletteName}>{t(s.labelKey)}</span>
                        {scheme === s.id && <Check size={14} className={styles.paletteCheck} />}
                      </button>
                    ))}
                  </m.div>
                )}
              </AnimatePresence>
            </div>
            {!isSingleSkin() && (
              <div className={styles.skinPaletteWrap} ref={skinPaletteRef}>
                <button
                  className={styles.skinSwitcherBtn}
                  onClick={() => { setSkinPaletteOpen((o) => !o); setThemePaletteOpen(false) }}
                  title={t('skin.switchSkin')}
                  aria-expanded={skinPaletteOpen}
                  aria-haspopup="listbox"
                >
                  <Layers size={15} />
                  <span>{t('skin.switchSkin')}</span>
                </button>
                <AnimatePresence>
                  {skinPaletteOpen && (
                    <m.div
                      className={styles.themePalette}
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
                            <span className={styles.skinDesc}>{t(cfg.descriptionKey)}</span>
                            {id === currentSkinId && <Check size={14} className={styles.paletteCheck} />}
                          </button>
                        )
                      })}
                    </m.div>
                  )}
                </AnimatePresence>
              </div>
            )}
            <button className={styles.logoutBtn} onClick={handleLogout}>
              <LogOut size={15} />
              <span>{t('nav.logout')}</span>
            </button>
          </div>
        </header>

        <main className={styles.content}>
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
    </div>
  )
}
