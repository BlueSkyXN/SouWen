import { create } from 'zustand'

interface AuthState {
  baseUrl: string
  token: string
  isAuthenticated: boolean
  version: string
  setAuth: (baseUrl: string, token: string, version: string, remember?: boolean) => void
  logout: () => void
  loadFromStorage: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  baseUrl: '',
  token: '',
  isAuthenticated: false,
  version: '',

  setAuth: (baseUrl, token, version, remember = false) => {
    set({ baseUrl, token, isAuthenticated: true, version })
    // 清除两端旧数据，防止残留
    localStorage.removeItem('souwen_baseUrl')
    localStorage.removeItem('souwen_token')
    sessionStorage.removeItem('souwen_baseUrl')
    sessionStorage.removeItem('souwen_token')
    // 默认存 sessionStorage（标签页关闭即清除）；仅"记住我"时用 localStorage
    const storage = remember ? localStorage : sessionStorage
    storage.setItem('souwen_baseUrl', baseUrl)
    storage.setItem('souwen_token', token)
    if (remember) {
      localStorage.setItem('souwen_remember', 'true')
    } else {
      localStorage.removeItem('souwen_remember')
    }
  },

  logout: () => {
    set({ baseUrl: '', token: '', isAuthenticated: false, version: '' })
    localStorage.removeItem('souwen_baseUrl')
    localStorage.removeItem('souwen_token')
    localStorage.removeItem('souwen_remember')
    sessionStorage.removeItem('souwen_baseUrl')
    sessionStorage.removeItem('souwen_token')
  },

  loadFromStorage: () => {
    // 优先 sessionStorage（更安全）；回退 localStorage（记住我）
    const baseUrl = sessionStorage.getItem('souwen_baseUrl') ?? localStorage.getItem('souwen_baseUrl') ?? ''
    const token = sessionStorage.getItem('souwen_token') ?? localStorage.getItem('souwen_token') ?? ''
    if (baseUrl) {
      set({ baseUrl, token, isAuthenticated: true })
    }
  },
}))
