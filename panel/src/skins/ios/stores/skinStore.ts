/**
 * 文件用途：iOS 皮肤的主题状态管理 store，使用 Zustand 管理明暗模式和配色方案的切换
 *
 * 函数/Store 清单：
 *   useSkinStore（Zustand store）
 *     - 功能：集中管理皮肤的主题模式（light/dark）和配色方案（scheme）状态
 *     - State 属性：
 *       mode (Theme) - 当前主题模式：'light' 或 'dark'
 *       scheme (string) - 当前配色方案 ID
 *     - 方法：
 *       toggleMode() - 在 light 和 dark 之间切换，保存到 localStorage，更新 DOM
 *       setScheme(s: string) - 设置配色方案（验证有效性后应用），持久化到 localStorage
 *       loadSkin() - 启动时从 localStorage 恢复主题配置，支持旧格式迁移
 *     - 关键常量：validSchemes Set 存储合法的 scheme ID，防止无效值应用
 *
 * localStorage 键说明：
 *   souwen_mode - 保存主题模式（'light' | 'dark'）
 *   souwen_scheme - 保存配色方案 ID
 *   souwen_theme / souwen_visual_theme - 旧格式键，启动时自动迁移并删除
 *
 * 模块依赖：
 *   - zustand: 轻量级状态管理库
 *   - @core/types: Theme 类型定义
 *   - ../skin.config: 皮肤配置对象（schemes 列表）
 */

import { create } from 'zustand'
import type { Theme } from '@core/types'
import { skinConfig } from '../skin.config'

// 验证配色方案的合法性
// 将 skinConfig 中的 schemes ID 转换为 Set，用于后续快速验证
const validSchemes = new Set(skinConfig.schemes.map((s) => s.id))

/**
 * Zustand Store 的 State 接口
 * @property {Theme} mode - 当前主题模式（'light' 或 'dark'）
 * @property {string} scheme - 当前配色方案 ID
 * @property {() => void} toggleMode - 切换主题模式的方法
 * @property {(s: string) => void} setScheme - 设置配色方案的方法
 * @property {() => void} loadSkin - 启动时加载保存的皮肤配置的方法
 */
interface SkinState {
  mode: Theme
  scheme: string
  toggleMode: () => void
  setScheme: (s: string) => void
  loadSkin: () => void
}

/**
 * 应用主题属性到 DOM 根元素
 * 设置 data-mode 和 data-scheme 属性，CSS 通过属性选择器改变样式
 * @param {Theme} mode - 主题模式
 * @param {string} scheme - 配色方案 ID
 */
function applyAttrs(mode: Theme, scheme: string) {
  document.documentElement.setAttribute('data-mode', mode)
  document.documentElement.setAttribute('data-scheme', scheme)
}

/**
 * Zustand 皮肤状态 Store
 * 管理应用的主题模式和配色方案，与 localStorage 同步
 */
export const useSkinStore = create<SkinState>((set, get) => ({
  mode: 'light',
  scheme: skinConfig.defaultScheme,

  /**
   * 切换明暗模式 - light ↔ dark
   * 更新 state、DOM 属性和 localStorage
   */
  toggleMode: () => {
    const next = get().mode === 'light' ? 'dark' : 'light'
    applyAttrs(next, get().scheme)
    localStorage.setItem('souwen_mode', next)
    set({ mode: next })
  },

  /**
   * 设置配色方案
   * 验证 scheme 有效性，应用到 DOM 和 localStorage（无效值会被忽略）
   * @param {string} s - 目标配色方案 ID
   */
  setScheme: (s: string) => {
    if (!validSchemes.has(s)) return
    applyAttrs(get().mode, s)
    localStorage.setItem('souwen_scheme', s)
    set({ scheme: s })
  },

  /**
   * 启动时加载皮肤配置
   * 1. 迁移旧版本 localStorage 键（souwen_theme / souwen_visual_theme → souwen_mode / souwen_scheme）
   * 2. 从 localStorage 恢复用户保存的模式和方案
   * 3. 默认值为 skin.config 中定义的 defaultMode/defaultScheme
   * 4. 应用到 DOM 根元素
   */
  loadSkin: () => {
    // 迁移旧版本的 localStorage 键
    const oldTheme = localStorage.getItem('souwen_theme')
    const oldVt = localStorage.getItem('souwen_visual_theme')
    if (oldTheme) {
      localStorage.setItem('souwen_mode', oldTheme)
      localStorage.removeItem('souwen_theme')
    }
    if (oldVt) {
      localStorage.setItem('souwen_scheme', oldVt)
      localStorage.removeItem('souwen_visual_theme')
    }

    // 从 localStorage 恢复，验证合法性，使用配置中的默认值作为后备
    const savedMode = localStorage.getItem('souwen_mode')
    const mode: Theme = savedMode === 'dark' ? 'dark' : 'light'
    const savedScheme = localStorage.getItem('souwen_scheme')
    const scheme = savedScheme && validSchemes.has(savedScheme) ? savedScheme : skinConfig.defaultScheme
    applyAttrs(mode, scheme)
    set({ mode, scheme })
  },
}))
