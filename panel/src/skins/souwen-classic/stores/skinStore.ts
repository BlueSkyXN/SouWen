import { create } from 'zustand'
import type { Theme } from '@core/types'
import { skinConfig } from '../skin.config'

const validSchemes = new Set(skinConfig.schemes.map((s) => s.id))

interface SkinState {
  mode: Theme
  scheme: string
  toggleMode: () => void
  setScheme: (s: string) => void
  loadSkin: () => void
}

function applyAttrs(mode: Theme, scheme: string) {
  document.documentElement.setAttribute('data-mode', mode)
  document.documentElement.setAttribute('data-scheme', scheme)
}

export const useSkinStore = create<SkinState>((set, get) => ({
  mode: 'light',
  scheme: skinConfig.defaultScheme,

  toggleMode: () => {
    const next = get().mode === 'light' ? 'dark' : 'light'
    applyAttrs(next, get().scheme)
    localStorage.setItem('souwen_mode', next)
    set({ mode: next })
  },

  setScheme: (s: string) => {
    if (!validSchemes.has(s)) return
    applyAttrs(get().mode, s)
    localStorage.setItem('souwen_scheme', s)
    set({ scheme: s })
  },

  loadSkin: () => {
    // Backward compat: migrate old keys
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
    const mode: Theme = savedMode === 'dark' ? 'dark' : 'light'
    const savedScheme = localStorage.getItem('souwen_scheme')
    const scheme = savedScheme && validSchemes.has(savedScheme) ? savedScheme : skinConfig.defaultScheme
    applyAttrs(mode, scheme)
    set({ mode, scheme })
  },
}))
