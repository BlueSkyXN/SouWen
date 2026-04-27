/**
 * 主布局组件 - 应用级页面框架
 *
 * 文件用途：渲染完整应用布局，包括侧边栏导航、顶部栏、页面内容区，支持移动端抽屉菜单
 * 
 * 功能模块：
 *   - 导航栏：左侧侧边栏包含应用名称、导航菜单、版本号、社交链接
 *   - 顶部栏：右侧包含连接状态、主题切换、配色选择、Skin 切换、登出按钮
 *   - 移动端：抽屉式菜单（通过 hamburger 按钮打开）和背景遮罩
 *   - 页面容器：带 Outlet 的主要内容区，支持页面过渡动画
 *   - 主题系统：支持 light/dark 模式和多种配色方案（nebula/aurora/obsidian）
 *
 * 常量定义：
 *   NAV_ITEMS - 导航菜单项列表（dashboard/search/sources/network/config）
 *   PAGE_TITLE_KEYS - URL 路径到标题 i18n 键的映射
 *   pageVariants / pageTransition - 页面进出动画配置
 *   overlayVariants / drawerVariants - 移动端抽屉动画配置
 *
 * 主要交互特性：
 *   - 侧边栏折叠/展开（desktop）
 *   - 移动端抽屉菜单（点击 hamburger 或背景遮罩关闭）
 *   - 主题模式切换（light ↔ dark）
 *   - 配色方案选择（palette dropdown）
 *   - Skin 切换（若非单皮肤模式）
 *   - ESC 键或外部点击关闭各类弹出菜单
 */

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
  Shield,
  FileText,
  Play,
  Wrench,
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

/** Google-colorful magnifier brand icon (4-color search ring) */
function BrandLogoIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="8" stroke="#4285F4" strokeWidth="3.2" />
      <path d="M11 3A8 8 0 0 1 19 11" stroke="#EA4335" strokeWidth="3.2" />
      <path d="M19 11A8 8 0 0 1 11 19" stroke="#34A853" strokeWidth="3.2" />
      <path d="M11 19A8 8 0 0 1 3 11" stroke="#FBBC05" strokeWidth="3.2" />
      <path d="M21.5 21.5l-4.85-4.85" stroke="#4285F4" strokeLinecap="round" strokeWidth="3.2" />
    </svg>
  )
}

// 导航菜单项定义
const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, labelKey: 'nav.dashboard' },
  { to: '/search', icon: Search, labelKey: 'nav.search' },
  { to: '/fetch', icon: FileText, labelKey: 'nav.fetch' },
  { to: '/video', icon: Play, labelKey: 'nav.video' },
  { to: '/tools', icon: Wrench, labelKey: 'nav.tools' },
  { to: '/sources', icon: Database, labelKey: 'nav.sources' },
  { to: '/network', icon: Globe, labelKey: 'nav.network' },
  { to: '/warp', icon: Shield, labelKey: 'nav.warp' },
  { to: '/config', icon: Settings, labelKey: 'nav.config' },
]

// URL 路径到页面标题 i18n 键的映射
const PAGE_TITLE_KEYS: Record<string, string> = {
  '/': 'nav.dashboard',
  '/search': 'nav.search',
  '/fetch': 'nav.fetch',
  '/video': 'nav.video',
  '/tools': 'nav.tools',
  '/sources': 'nav.sources',
  '/network': 'nav.network',
  '/config': 'nav.config',
}

// 页面切换动画配置
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

// 移动端背景遮罩动画配置
const overlayVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
}

// 移动端抽屉菜单动画配置
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
  // 主题调色板和 skin 选择器的显示状态
  const [themePaletteOpen, setThemePaletteOpen] = useState(false)
  const [skinPaletteOpen, setSkinPaletteOpen] = useState(false)
  const paletteRef = useRef<HTMLDivElement>(null)
  const skinPaletteRef = useRef<HTMLDivElement>(null)

  // 根据当前路径获取页面标题 i18n 键
  const pageTitleKey = PAGE_TITLE_KEYS[location.pathname] ?? 'nav.dashboard'

  // 构建主题点色映射（用于调色板 UI 中的色点显示）
  const THEME_DOTS = Object.fromEntries(
    skinConfig.schemes.map((s) => [s.id, s.dotColor])
  ) as Record<string, string>

  // 获取当前激活的 skin ID
  const currentSkinId = document.documentElement.getAttribute('data-skin') || 'souwen-google'

  // 外部点击或 ESC 关闭调色板菜单
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

  // 处理登出操作
  const handleLogout = useCallback(() => {
    logout()
  }, [logout])

  // 路径改变时关闭移动端菜单
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  // 处理 Skin 切换 - 若选中新 skin，更新 localStorage 并重新加载页面
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

  // 侧边栏内容（共享给 desktop 和 mobile 两种视图）
  const sidebarContent = (
    <>
      <div className={styles.brand}>
        <span className={styles.logo}>
          <BrandLogoIcon />
        </span>
        <span className={styles.brandText}>{t('app.name')}</span>
      </div>
      <div className={styles.brandSeparator} />

      {/* 导航菜单 */}
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
              <item.icon size={22} />
            </span>
            <span className={styles.label}>{t(item.labelKey)}</span>
          </NavLink>
        ))}
      </nav>

      {/* 底部操作区：版本号、链接、折叠按钮 */}
      <div className={styles.footer}>
        <div className={styles.footerMeta}>
          {version && <div className={styles.version}>v{version}</div>}
          <a
            className={styles.authorLink}
            href="https://github.com/BlueSkyXN/SouWen"
            target="_blank"
            rel="noopener noreferrer"
          >
            SouWen · @BlueSkyXN · GPLv3
          </a>
        </div>
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
            <h2 className={styles.pageTitle}>{t(pageTitleKey)}</h2>
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
              {mode === 'light' ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            <div className={styles.themePaletteWrap} ref={paletteRef}>
              <button
                className={styles.themeBtn}
                onClick={() => { setThemePaletteOpen((o) => !o); setSkinPaletteOpen(false) }}
                aria-label={t('theme.label')}
                aria-expanded={themePaletteOpen}
                aria-haspopup="listbox"
              >
                <Palette size={18} />
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
            <button
              className={styles.logoutBtn}
              onClick={handleLogout}
              aria-label={t('nav.logout')}
              title={t('nav.logout')}
            >
              <LogOut size={18} />
            </button>
            <div
              className={styles.userAvatar}
              role="button"
              tabIndex={0}
              aria-label="User"
              title="User"
            >
              U
            </div>
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
