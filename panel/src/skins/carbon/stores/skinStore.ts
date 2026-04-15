import { create } from 'zustand'
import type { Theme, VisualTheme } from '@core/types'
import { isVisualTheme } from '@core/types'

interface SkinState {
  mode: Theme
  scheme: VisualTheme
  toggleMode: () => void
  setScheme: (s: VisualTheme) => void
  loadSkin: () => void
}

function applyAttrs(mode: Theme, scheme: VisualTheme) {
  document.documentElement.setAttribute('data-mode', mode)
  document.documentElement.setAttribute('data-scheme', scheme)
}

export const useSkinStore = create<SkinState>((set, get) => ({
  mode: 'dark',
  scheme: 'nebula',

  toggleMode: () => {
    const next = get().mode === 'light' ? 'dark' : 'light'
    applyAttrs(next, get().scheme)
    localStorage.setItem('souwen_mode', next)
    set({ mode: next })
  },

  setScheme: (s: VisualTheme) => {
    applyAttrs(get().mode, s)
    localStorage.setItem('souwen_scheme', s)
    set({ scheme: s })
  },

  loadSkin: () => {
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

    const savedMode = localStorage.getItem('souwen_mode')
    const mode: Theme = savedMode === 'light' ? 'light' : 'dark'
    const savedScheme = localStorage.getItem('souwen_scheme')
    const scheme: VisualTheme = isVisualTheme(savedScheme) ? savedScheme : 'nebula'
    applyAttrs(mode, scheme)
    set({ mode, scheme })
  },
}))
