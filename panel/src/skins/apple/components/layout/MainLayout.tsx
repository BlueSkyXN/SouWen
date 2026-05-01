/**
 * 文件用途：Apple 皮肤的主布局组件，包含导航栏、移动端抽屉菜单、页面内容区域和页脚
 *
 * 组件/函数清单：
 *   MainLayout（函数组件）
 *     - 功能：应用主框架，提供导航、明暗模式切换、皮肤切换、移动端响应、页面路由出口
 *     - Hooks 依赖：useTranslation, useLocation, useAuthStore, useSkinStore, useState, useCallback, useEffect, useRef
 *     - State 状态：mobileOpen (bool) 移动菜单打开状态, skinPaletteOpen (bool) 皮肤选择菜单打开状态
 *     - 关键函数：handleLogout 登出, handleSkinSwitch 切换皮肤
 *     - 关键常量：NAV_ITEMS 导航菜单项数组, pageVariants 页面进出动画配置, pageTransition 页面过渡动画配置
 *
 * 模块依赖：
 *   - react-router-dom: 路由导航与 Outlet 出口
 *   - react-i18next: 国际化翻译
 *   - framer-motion: 动画库（导航、菜单、页面过渡）
 *   - lucide-react: 图标库
 *   - @core/stores/authStore: 认证状态管理
 *   - ./stores/skinStore: 皮肤和主题状态管理
 *   - @core/skin-registry: 皮肤注册表工具函数
 *   - MainLayout.module.scss: 布局样式
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { m, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard,
  Search,
  Database,
  Wifi,
  Shield,
  Settings,
  LogOut,
  Menu,
  X,
  Moon,
  Sun,
  Layers,
  Check,
  FileText,
  Play,
  Wrench,
  Puzzle,
} from 'lucide-react'
import { useAuthStore } from '@core/stores/authStore'
import { canAccessNavItem } from '@core/lib/access'
import { useSkinStore } from '../../stores/skinStore'
import { isSingleSkin, listSkinIds, getSkinOrDefault } from '@core/skin-registry'
import styles from './MainLayout.module.scss'

/**
 * 导航菜单项配置数组
 * 每项定义路由路径、对应图标和国际化标签 key
 */
const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, labelKey: 'nav.dashboard' },
  { to: '/search', icon: Search, labelKey: 'nav.search' },
  { to: '/fetch', icon: FileText, labelKey: 'nav.fetch' },
  { to: '/video', icon: Play, labelKey: 'nav.video' },
  { to: '/tools', icon: Wrench, labelKey: 'nav.tools' },
  { to: '/sources', icon: Database, labelKey: 'nav.sources' },
  { to: '/network', icon: Wifi, labelKey: 'nav.network' },
  { to: '/warp', icon: Shield, labelKey: 'nav.warp' },
  { to: '/plugins', icon: Puzzle, labelKey: 'nav.plugins' },
  { to: '/config', icon: Settings, labelKey: 'nav.config' },
]

/**
 * 页面切换动画的起始/结束状态
 * initial: 进入时从下方淡入, exit: 退出时向上淡出
 */
const pageVariants = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
}

/**
 * 页面过渡动画的时间配置
 * spring 弹簧动画，stiffness 硬度、damping 阻尼、mass 质量影响动画弹性
 */
const pageTransition = {
  type: 'spring' as const,
  stiffness: 350,
  damping: 32,
  mass: 0.9,
}

/**
 * MainLayout 组件 - 应用主框架
 * 包含顶部导航栏（支持深色/浅色切换和皮肤切换）、移动端抽屉菜单、页面内容区域、页脚
 * 导航响应式设计，移动端隐藏导航链接并展示汉堡菜单
 */
export function MainLayout() {
  const { t } = useTranslation()
  const location = useLocation()
  const logout = useAuthStore((s) => s.logout)
  const version = useAuthStore((s) => s.version)
  const features = useAuthStore((s) => s.features)
  const role = useAuthStore((s) => s.role)
  const { mode, toggleMode } = useSkinStore()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [skinPaletteOpen, setSkinPaletteOpen] = useState(false)
  const skinPaletteRef = useRef<HTMLDivElement>(null)

  // 从 HTML 根元素的 data-skin 属性获取当前皮肤 ID，默认为 'apple'
  const currentSkinId = document.documentElement.getAttribute('data-skin') || 'apple'
  const visibleNavItems = NAV_ITEMS.filter((item) => canAccessNavItem(item.to, features, role))

  // 路由路径变化时关闭移动端菜单
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  // 皮肤选择菜单的点击外关闭和 Escape 键关闭逻辑
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

  /**
   * 处理登出操作，从 authStore 直接调用 logout 方法
   */
  const handleLogout = useCallback(() => { logout() }, [logout])

  /**
   * 切换皮肤处理函数
   * 保存选中的皮肤 ID 和其配置（模式、配色方案）到 localStorage，然后刷新页面
   * @param {string} nextId - 目标皮肤的 ID
   */
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
      {/* 玻璃态导航栏 - 固定在顶部，包含品牌 Logo、导航链接、功能按钮 */}
      <nav className={styles.nav}>
        <div className={styles.navInner}>
          <div className={styles.navLeft}>
            {/* 移动端汉堡菜单按钮 */}
            <button
              className={styles.hamburger}
              onClick={() => setMobileOpen((o) => !o)}
              aria-label="Menu"
            >
              <Menu size={20} />
            </button>
            {/* 品牌 Logo 和名称，点击回到首页 */}
            <NavLink to="/" className={styles.brand}>
              <Search size={18} />
              <span>SouWen</span>
            </NavLink>
            {/* 桌面端导航链接列表 */}
            <div className={styles.navLinks}>
              {visibleNavItems.map((item) => (
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
            {/* 明暗模式切换按钮 */}
            <button
              className={styles.iconBtn}
              onClick={toggleMode}
              aria-label={mode === 'light' ? t('common.darkMode') : t('common.lightMode')}
            >
              {mode === 'light' ? <Moon size={16} /> : <Sun size={16} />}
            </button>
            {/* 皮肤切换菜单（仅当存在多个皮肤时显示） */}
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
                {/* 皮肤选择下拉菜单，带进出动画 */}
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
                            {/* 当前活跃皮肤显示勾选图标 */}
                            {id === currentSkinId && <Check size={14} className={styles.paletteCheck} />}
                          </button>
                        )
                      })}
                    </m.div>
                  )}
                </AnimatePresence>
              </div>
            )}
            {/* 登出按钮 */}
            <button className={styles.iconBtn} onClick={handleLogout} title={t('nav.logout')}>
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </nav>

      {/* 移动端覆盖层 - 点击关闭抽屉菜单 */}
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

      {/* 移动端侧边抽屉菜单 - 从左侧滑入 */}
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
            {visibleNavItems.map((item) => (
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

      {/* 页面内容区域 - 使用 React Router 的 Outlet 渲染子路由组件 */}
      <main className={styles.main}>
        {/* 路由变化时页面动画过渡 mode="wait" 确保旧页面完全退出后新页面才进入 */}
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

      {/* 页脚 - 显示应用名、作者链接和版本号 */}
      <footer className={styles.pageFooter}>
        <span>
          SouWen 搜文 · <a href="https://github.com/BlueSkyXN/SouWen" target="_blank" rel="noopener noreferrer">@BlueSkyXN</a> · GPLv3
          {version && <> · v{version}</>}
        </span>
      </footer>
    </div>
  )
}
