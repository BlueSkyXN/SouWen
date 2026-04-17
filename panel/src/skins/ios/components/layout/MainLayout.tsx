/**
 * 文件用途：iOS 皮肤的主布局组件，包含导航栏、移动端抽屉菜单、页面内容区域和页脚
 * 采用 iOS HIG（Human Interface Guidelines）设计规范，支持明暗模式和皮肤切换
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { m, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard,
  Search,
  Database,
  Globe,
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
  { to: '/', icon: LayoutDashboard, labelKey: 'nav.dashboard', color: '#007aff' },
  { to: '/search', icon: Search, labelKey: 'nav.search', color: '#5ac8fa' },
  { to: '/sources', icon: Database, labelKey: 'nav.sources', color: '#5856d6' },
  { to: '/network', icon: Globe, labelKey: 'nav.network', color: '#34c759' },
  { to: '/config', icon: Settings, labelKey: 'nav.config', color: '#8e8e93' },
]

const pageVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
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

  const currentSkinId = document.documentElement.getAttribute('data-skin') || 'ios'

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

  const sidebarContent = (
    <>
      {/* Search bar (macOS style) */}
      <div className={styles.sidebarSearch}>
        <Search size={14} className={styles.searchIcon} />
        <span className={styles.searchPlaceholder}>SouWen</span>
      </div>

      {/* Navigation items */}
      <nav className={styles.sidebarNav}>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `${styles.sidebarItem} ${isActive ? styles.sidebarItemActive : ''}`
            }
          >
            <span className={styles.squircleIcon} style={{ background: item.color }}>
              <item.icon size={14} color="#fff" />
            </span>
            <span className={styles.sidebarLabel}>{t(item.labelKey)}</span>
          </NavLink>
        ))}
      </nav>

      {/* Bottom actions */}
      <div className={styles.sidebarFooter}>
        <button className={styles.sidebarAction} onClick={toggleMode}>
          {mode === 'light' ? <Moon size={16} /> : <Sun size={16} />}
          <span>{mode === 'light' ? t('common.darkMode') : t('common.lightMode')}</span>
        </button>

        {!isSingleSkin() && (
          <div className={styles.skinWrap} ref={skinPaletteRef}>
            <button
              className={styles.sidebarAction}
              onClick={() => setSkinPaletteOpen((o) => !o)}
              aria-expanded={skinPaletteOpen}
              aria-haspopup="listbox"
            >
              <Layers size={16} />
              <span>{t('skin.switchSkin')}</span>
            </button>
            <AnimatePresence>
              {skinPaletteOpen && (
                <m.div
                  className={styles.palette}
                  role="listbox"
                  initial={{ opacity: 0, y: 4, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 4, scale: 0.96 }}
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

        <button className={styles.sidebarAction} onClick={handleLogout}>
          <LogOut size={16} />
          <span>{t('nav.logout')}</span>
        </button>

        {version && (
          <div className={styles.versionTag}>v{version}</div>
        )}
      </div>
    </>
  )

  return (
    <div className={styles.layout}>
      {/* ── Desktop Sidebar ── */}
      <aside className={styles.sidebar}>
        {sidebarContent}
      </aside>

      {/* ── Mobile Top Bar ── */}
      <header className={styles.mobileHeader}>
        <button
          className={styles.hamburger}
          onClick={() => setMobileOpen((o) => !o)}
          aria-label="Menu"
        >
          <Menu size={22} />
        </button>
        <span className={styles.mobileTitle}>SouWen</span>
        <div style={{ width: 36 }} />
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
          <m.aside
            className={styles.mobileDrawer}
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ type: 'spring', stiffness: 400, damping: 36 }}
          >
            <div className={styles.drawerHeader}>
              <span className={styles.drawerBrand}>SouWen</span>
              <button className={styles.drawerClose} onClick={() => setMobileOpen(false)}>
                <X size={20} />
              </button>
            </div>
            {sidebarContent}
          </m.aside>
        )}
      </AnimatePresence>

      {/* ── Content Area ── */}
      <main className={styles.content}>
        <div className={styles.contentInner}>
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
        </div>
      </main>
    </div>
  )
}
