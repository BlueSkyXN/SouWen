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
  LogOut,
  Menu,
  X,
  Moon,
  Sun,
  Layers,
  Check,
} from 'lucide-react'
import { useAuthStore } from '@core/stores/authStore'
import { useSkinStore } from '../../stores/skinStore'
import { isSingleSkin, listSkinIds, getSkinOrDefault } from '@core/skin-registry'
import styles from './MainLayout.module.scss'

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, labelKey: 'nav.dashboard' },
  { to: '/search', icon: Search, labelKey: 'nav.search' },
  { to: '/sources', icon: Database, labelKey: 'nav.sources' },
  { to: '/network', icon: Wifi, labelKey: 'nav.network' },
  { to: '/config', icon: Settings, labelKey: 'nav.config' },
]

const pageVariants = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
}

const pageTransition = {
  type: 'spring' as const,
  stiffness: 350,
  damping: 32,
  mass: 0.9,
}

export function MainLayout() {
  const { t } = useTranslation()
  const location = useLocation()
  const logout = useAuthStore((s) => s.logout)
  const version = useAuthStore((s) => s.version)
  const { mode, toggleMode } = useSkinStore()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [skinPaletteOpen, setSkinPaletteOpen] = useState(false)
  const skinPaletteRef = useRef<HTMLDivElement>(null)

  const currentSkinId = document.documentElement.getAttribute('data-skin') || 'apple'

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!skinPaletteOpen) return
    const handleClick = (e: MouseEvent) => {
      if (skinPaletteRef.current && !skinPaletteRef.current.contains(e.target as Node)) {
        setSkinPaletteOpen(false)
      }
    }
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSkinPaletteOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [skinPaletteOpen])

  const handleLogout = useCallback(() => { logout() }, [logout])

  const handleSkinSwitch = (nextId: string) => {
    if (nextId === currentSkinId) { setSkinPaletteOpen(false); return }
    const nextSkin = getSkinOrDefault(nextId)
    localStorage.setItem('souwen_skin', nextId)
    localStorage.setItem('souwen_mode', nextSkin.skinModule.skinConfig.defaultMode)
    localStorage.setItem('souwen_scheme', nextSkin.skinModule.skinConfig.defaultScheme)
    window.location.reload()
  }

  return (
    <div className={styles.layout}>
      {/* Glass navigation bar */}
      <nav className={styles.nav}>
        <div className={styles.navInner}>
          <div className={styles.navLeft}>
            <button
              className={styles.hamburger}
              onClick={() => setMobileOpen((o) => !o)}
              aria-label="Menu"
            >
              <Menu size={20} />
            </button>
            <NavLink to="/" className={styles.brand}>
              <Search size={18} />
              <span>SouWen</span>
            </NavLink>
            <div className={styles.navLinks}>
              {NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `${styles.navLink} ${isActive ? styles.navActive : ''}`
                  }
                >
                  {t(item.labelKey)}
                </NavLink>
              ))}
            </div>
          </div>
          <div className={styles.navRight}>
            <button
              className={styles.iconBtn}
              onClick={toggleMode}
              aria-label={mode === 'light' ? t('common.darkMode') : t('common.lightMode')}
            >
              {mode === 'light' ? <Moon size={16} /> : <Sun size={16} />}
            </button>
            {!isSingleSkin() && (
              <div className={styles.skinWrap} ref={skinPaletteRef}>
                <button
                  className={styles.iconBtn}
                  onClick={() => setSkinPaletteOpen((o) => !o)}
                  title={t('skin.switchSkin')}
                  aria-expanded={skinPaletteOpen}
                  aria-haspopup="listbox"
                >
                  <Layers size={16} />
                </button>
                <AnimatePresence>
                  {skinPaletteOpen && (
                    <m.div
                      className={styles.palette}
                      role="listbox"
                      initial={{ opacity: 0, y: -4, scale: 0.96 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -4, scale: 0.96 }}
                      transition={{ type: 'spring', stiffness: 500, damping: 30 }}
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
                            {id === currentSkinId && <Check size={14} className={styles.paletteCheck} />}
                          </button>
                        )
                      })}
                    </m.div>
                  )}
                </AnimatePresence>
              </div>
            )}
            <button className={styles.iconBtn} onClick={handleLogout} title={t('nav.logout')}>
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile overlay */}
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

      {/* Mobile drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <m.div
            className={styles.mobileDrawer}
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ type: 'spring', stiffness: 400, damping: 36 }}
          >
            <div className={styles.drawerHeader}>
              <span className={styles.drawerBrand}>SouWen</span>
              <button className={styles.iconBtn} onClick={() => setMobileOpen(false)}>
                <X size={20} />
              </button>
            </div>
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `${styles.drawerLink} ${isActive ? styles.navActive : ''}`
                }
              >
                <item.icon size={18} />
                {t(item.labelKey)}
              </NavLink>
            ))}
          </m.div>
        )}
      </AnimatePresence>

      {/* Page content */}
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

      <footer className={styles.pageFooter}>
        <span>
          SouWen 搜文 · <a href="https://github.com/BlueSkyXN/SouWen" target="_blank" rel="noopener noreferrer">@BlueSkyXN</a> · GPLv3
          {version && <> · v{version}</>}
        </span>
      </footer>
    </div>
  )
}
