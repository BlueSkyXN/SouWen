import { create } from 'zustand'
import type { Theme } from '../types'

interface ThemeState {
  theme: Theme
  toggleTheme: () => void
  loadTheme: () => void
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: 'light',

  toggleTheme: () => {
    const next = get().theme === 'light' ? 'dark' : 'light'
    document.documentElement.setAttribute('data-theme', next)
    localStorage.setItem('souwen_theme', next)
    set({ theme: next })
  },

  loadTheme: () => {
    const saved = localStorage.getItem('souwen_theme') as Theme | null
    const theme = saved ?? 'light'
    document.documentElement.setAttribute('data-theme', theme)
    set({ theme })
  },
}))
