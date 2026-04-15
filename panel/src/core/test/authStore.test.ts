import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '../stores/authStore'

function clearStorage() {
  localStorage.clear()
  sessionStorage.clear()
}

describe('authStore', () => {
  beforeEach(() => {
    clearStorage()
    useAuthStore.setState({
      baseUrl: '',
      token: '',
      isAuthenticated: false,
      version: '',
    })
  })

  it('setAuth stores state and persists to sessionStorage by default', () => {
    useAuthStore.getState().setAuth('http://localhost:8000', 'secret', '0.3.0')
    const state = useAuthStore.getState()
    expect(state.baseUrl).toBe('http://localhost:8000')
    expect(state.token).toBe('secret')
    expect(state.version).toBe('0.3.0')
    expect(state.isAuthenticated).toBe(true)

    expect(sessionStorage.getItem('souwen_baseUrl')).toBe('http://localhost:8000')
    expect(sessionStorage.getItem('souwen_token')).toBe('secret')
    expect(sessionStorage.getItem('souwen_version')).toBe('0.3.0')
    expect(localStorage.getItem('souwen_baseUrl')).toBeNull()
  })

  it('setAuth with remember=true persists to localStorage', () => {
    useAuthStore.getState().setAuth('http://localhost:8000', 'pw', '0.3.0', true)
    expect(localStorage.getItem('souwen_baseUrl')).toBe('http://localhost:8000')
    expect(localStorage.getItem('souwen_version')).toBe('0.3.0')
    expect(localStorage.getItem('souwen_remember')).toBe('true')
    expect(sessionStorage.getItem('souwen_baseUrl')).toBeNull()
  })

  it('logout clears state and both storages', () => {
    useAuthStore.getState().setAuth('http://localhost:8000', 'pw', '0.3.0', true)
    useAuthStore.getState().logout()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.version).toBe('')
    expect(localStorage.getItem('souwen_baseUrl')).toBeNull()
    expect(localStorage.getItem('souwen_version')).toBeNull()
    expect(sessionStorage.getItem('souwen_baseUrl')).toBeNull()
    expect(sessionStorage.getItem('souwen_version')).toBeNull()
  })

  it('loadFromStorage restores version from sessionStorage', () => {
    sessionStorage.setItem('souwen_baseUrl', 'http://x')
    sessionStorage.setItem('souwen_token', 'tok')
    sessionStorage.setItem('souwen_version', '1.2.3')
    useAuthStore.getState().loadFromStorage()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.version).toBe('1.2.3')
  })

  it('loadFromStorage falls back to localStorage', () => {
    localStorage.setItem('souwen_baseUrl', 'http://y')
    localStorage.setItem('souwen_token', 'tok2')
    localStorage.setItem('souwen_version', '2.0.0')
    useAuthStore.getState().loadFromStorage()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.version).toBe('2.0.0')
  })

  it('loadFromStorage does nothing when storage is empty', () => {
    useAuthStore.getState().loadFromStorage()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
})
