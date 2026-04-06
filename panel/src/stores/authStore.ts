import { create } from 'zustand'

interface AuthState {
  baseUrl: string
  token: string
  isAuthenticated: boolean
  version: string
  setAuth: (baseUrl: string, token: string, version: string) => void
  logout: () => void
  loadFromStorage: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  baseUrl: '',
  token: '',
  isAuthenticated: false,
  version: '',

  setAuth: (baseUrl, token, version) => {
    set({ baseUrl, token, isAuthenticated: true, version })
    if (localStorage.getItem('souwen_remember') === 'true') {
      localStorage.setItem('souwen_baseUrl', baseUrl)
      localStorage.setItem('souwen_token', token)
    } else {
      sessionStorage.setItem('souwen_baseUrl', baseUrl)
      sessionStorage.setItem('souwen_token', token)
    }
  },

  logout: () => {
    set({ baseUrl: '', token: '', isAuthenticated: false, version: '' })
    localStorage.removeItem('souwen_baseUrl')
    localStorage.removeItem('souwen_token')
    sessionStorage.removeItem('souwen_baseUrl')
    sessionStorage.removeItem('souwen_token')
  },

  loadFromStorage: () => {
    const baseUrl = localStorage.getItem('souwen_baseUrl') ?? sessionStorage.getItem('souwen_baseUrl') ?? ''
    const token = localStorage.getItem('souwen_token') ?? sessionStorage.getItem('souwen_token') ?? ''
    if (baseUrl) {
      set({ baseUrl, token, isAuthenticated: true })
    }
  },
}))
