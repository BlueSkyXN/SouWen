import { create } from 'zustand'
import type { Theme, VisualTheme } from '../types'
import { isVisualTheme } from '../types'

interface ThemeState {
  theme: Theme
  visualTheme: VisualTheme
  toggleTheme: () => void
  setVisualTheme: (vt: VisualTheme) => void
  loadTheme: () => void
}

function applyAttrs(theme: Theme, visualTheme: VisualTheme) {
  document.documentElement.setAttribute('data-theme', theme)
  document.documentElement.setAttribute('data-visual-theme', visualTheme)
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: 'light',
  visualTheme: 'nebula',

  toggleTheme: () => {
    const next = get().theme === 'light' ? 'dark' : 'light'
    applyAttrs(next, get().visualTheme)
    localStorage.setItem('souwen_theme', next)
    set({ theme: next })
  },

  setVisualTheme: (vt: VisualTheme) => {
    applyAttrs(get().theme, vt)
    localStorage.setItem('souwen_visual_theme', vt)
    set({ visualTheme: vt })
  },

  loadTheme: () => {
    const savedTheme = localStorage.getItem('souwen_theme')
    const theme: Theme = savedTheme === 'dark' ? 'dark' : 'light'
    const savedVt = localStorage.getItem('souwen_visual_theme')
    const visualTheme: VisualTheme = isVisualTheme(savedVt) ? savedVt : 'nebula'
    applyAttrs(theme, visualTheme)
    set({ theme, visualTheme })
  },
}))
