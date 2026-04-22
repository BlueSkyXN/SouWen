/**
 * Skin 状态管理 store - 主题和配色方案管理
 *
 * 文件用途：使用 Zustand 管理 skin 的主题模式（light/dark）和配色方案，并持久化到 localStorage
 *
 * 状态结构（SkinState）：
 *   - mode (Theme): 当前主题模式（'light' | 'dark'）
 *   - scheme (string): 当前配色方案 ID
 *
 * 方法清单：
 *   toggleMode() - void
 *     - 功能：切换 light ↔ dark 模式，同时保存到 localStorage 和 DOM 属性
 *
 *   setScheme(s: string) - void
 *     - 功能：切换配色方案（仅限有效方案），同时保存到 localStorage 和 DOM 属性
 *
 *   loadSkin() - void
 *     - 功能：应用启动时调用，从 localStorage 恢复用户偏好
 *     - 向后兼容：迁移旧版本的 souwen_theme / souwen_visual_theme 键名
 *
 * 辅助函数：
 *   applyAttrs(mode: Theme, scheme: string) - void
 *     - 功能：将主题设置应用到 document.documentElement 属性，CSS 通过属性选择器响应
 */

import { create } from 'zustand'
import type { Theme } from '@core/types'
import { skinConfig } from '../skin.config'

// 验证配色方案有效性
const validSchemes = new Set(skinConfig.schemes.map((s) => s.id))

interface SkinState {
  mode: Theme
  scheme: string
  toggleMode: () => void
  setScheme: (s: string) => void
  loadSkin: () => void
}

/**
 * 应用主题属性到 DOM 根元素
 * 
 * 将 mode 和 scheme 设置为 data-mode 和 data-scheme 属性，
 * CSS 样式表通过属性选择器（如 [data-mode="dark"]）响应切换
 */
function applyAttrs(mode: Theme, scheme: string) {
  document.documentElement.setAttribute('data-mode', mode)
  document.documentElement.setAttribute('data-scheme', scheme)
}

export const useSkinStore = create<SkinState>((set, get) => ({
  mode: 'light',
  scheme: skinConfig.defaultScheme,

  toggleMode: () => {
    // 在 light 和 dark 之间切换
    const next = get().mode === 'light' ? 'dark' : 'light'
    applyAttrs(next, get().scheme)
    localStorage.setItem('souwen_mode', next)
    set({ mode: next })
  },

  setScheme: (s: string) => {
    // 仅允许设置有效的配色方案
    if (!validSchemes.has(s)) return
    applyAttrs(get().mode, s)
    localStorage.setItem('souwen_scheme', s)
    set({ scheme: s })
  },

  loadSkin: () => {
    // 向后兼容：迁移旧版本的 localStorage 键名
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

    // 从 localStorage 恢复用户偏好，不存在时使用默认值
    const savedMode = localStorage.getItem('souwen_mode')
    const mode: Theme = savedMode === 'dark' ? 'dark' : 'light'
    const savedScheme = localStorage.getItem('souwen_scheme')
    const scheme = savedScheme && validSchemes.has(savedScheme) ? savedScheme : skinConfig.defaultScheme
    applyAttrs(mode, scheme)
    set({ mode, scheme })
  },
}))
