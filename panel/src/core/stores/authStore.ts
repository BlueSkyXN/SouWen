import { create } from 'zustand'

interface AuthState {
  baseUrl: string
  token: string
  isAuthenticated: boolean
  version: string
  issuedAt: number // token 发放时间戳 (ms since epoch)；0 表示未登录
  setAuth: (baseUrl: string, token: string, version: string, remember?: boolean) => void
  logout: () => void
  loadFromStorage: () => void
  isExpired: (ttlMs?: number) => boolean
}

// 默认 token 有效期：30 分钟。超过则视为过期，组件挂载时会自动登出
const DEFAULT_TTL_MS = 30 * 60 * 1000

export const useAuthStore = create<AuthState>((set, get) => ({
  baseUrl: '',
  token: '',
  isAuthenticated: false,
  version: '',
  issuedAt: 0,

  setAuth: (baseUrl, token, version, remember = false) => {
    const issuedAt = Date.now()
    set({ baseUrl, token, isAuthenticated: true, version, issuedAt })
    // 清除两端旧数据，防止残留
    localStorage.removeItem('souwen_baseUrl')
    localStorage.removeItem('souwen_token')
    localStorage.removeItem('souwen_version')
    localStorage.removeItem('souwen_issuedAt')
    sessionStorage.removeItem('souwen_baseUrl')
    sessionStorage.removeItem('souwen_token')
    sessionStorage.removeItem('souwen_version')
    sessionStorage.removeItem('souwen_issuedAt')
    // 默认存 sessionStorage（标签页关闭即清除）；仅"记住我"时用 localStorage
    const storage = remember ? localStorage : sessionStorage
    storage.setItem('souwen_baseUrl', baseUrl)
    storage.setItem('souwen_token', token)
    storage.setItem('souwen_version', version)
    storage.setItem('souwen_issuedAt', String(issuedAt))
    if (remember) {
      localStorage.setItem('souwen_remember', 'true')
    } else {
      localStorage.removeItem('souwen_remember')
    }
  },

  logout: () => {
    set({ baseUrl: '', token: '', isAuthenticated: false, version: '', issuedAt: 0 })
    localStorage.removeItem('souwen_baseUrl')
    localStorage.removeItem('souwen_token')
    localStorage.removeItem('souwen_version')
    localStorage.removeItem('souwen_issuedAt')
    localStorage.removeItem('souwen_remember')
    sessionStorage.removeItem('souwen_baseUrl')
    sessionStorage.removeItem('souwen_token')
    sessionStorage.removeItem('souwen_version')
    sessionStorage.removeItem('souwen_issuedAt')
  },

  loadFromStorage: () => {
    // 优先 sessionStorage（更安全）；回退 localStorage（记住我）
    const baseUrl = sessionStorage.getItem('souwen_baseUrl') ?? localStorage.getItem('souwen_baseUrl') ?? ''
    const token = sessionStorage.getItem('souwen_token') ?? localStorage.getItem('souwen_token') ?? ''
    const version = sessionStorage.getItem('souwen_version') ?? localStorage.getItem('souwen_version') ?? ''
    const issuedAtRaw = sessionStorage.getItem('souwen_issuedAt') ?? localStorage.getItem('souwen_issuedAt') ?? '0'
    const issuedAt = Number(issuedAtRaw) || 0
    if (baseUrl) {
      set({ baseUrl, token, isAuthenticated: true, version, issuedAt })
    }
  },

  isExpired: (ttlMs = DEFAULT_TTL_MS) => {
    const { issuedAt, isAuthenticated } = get()
    if (!isAuthenticated) return false
    if (!issuedAt) return true
    return Date.now() - issuedAt > ttlMs
  },
}))
