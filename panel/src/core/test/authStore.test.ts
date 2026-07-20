/**
 * 文件用途：认证存储单元测试，验证 useAuthStore 的状态管理、存储持久化、令牌过期检测
 *
 * 测试套件清单：
 *
 *     describe('authStore')
 *         - 前置：每个测试前清空 localStorage 和 sessionStorage，重置 store 状态
 *
 *         it('setAuth stores state and persists to sessionStorage by default')
 *             - 验证：无 remember 参数时，凭证存入 sessionStorage（非 localStorage）
 *             - 检查：baseUrl、token、version 同步到 state 和 sessionStorage
 *
 *         it('setAuth with remember=true persists to localStorage')
 *             - 验证：remember=true 时，凭证存入 localStorage
 *             - 检查：souwen_remember 标志正确设置
 *
 *         it('logout clears state and both storages')
 *             - 验证：logout() 清空 state 和两个存储中的所有凭证
 *             - 检查：isAuthenticated 恢复为 false，version 为空字符串
 *
 *         it('loadFromStorage restores version from sessionStorage')
 *             - 验证：loadFromStorage() 优先从 sessionStorage 恢复
 *             - 检查：version 字段正确恢复
 *
 *         it('loadFromStorage falls back to localStorage')
 *             - 验证：sessionStorage 为空时，回退到 localStorage
 *             - 检查：version 从 localStorage 恢复
 *
 *         it('loadFromStorage does nothing when storage is empty')
 *             - 验证：存储全空时，loadFromStorage() 不改变状态
 *             - 检查：isAuthenticated 保持 false
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '../stores/authStore'

/**
 * 清空存储辅助函数
 */
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
      issuedAt: 0,
      role: 'guest',
      features: {},
      edition: null,
      editionCapabilities: null,
    })
  })

  /**
   * 测试：默认情况下将凭证存入 sessionStorage
   */
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

  /**
   * 测试：remember=true 时存入 localStorage
   */
  it('setAuth with remember=true persists to localStorage', () => {
    useAuthStore.getState().setAuth('http://localhost:8000', 'pw', '0.3.0', true)
    expect(localStorage.getItem('souwen_baseUrl')).toBe('http://localhost:8000')
    expect(localStorage.getItem('souwen_version')).toBe('0.3.0')
    expect(localStorage.getItem('souwen_remember')).toBe('true')
    expect(sessionStorage.getItem('souwen_baseUrl')).toBeNull()
  })

  it('setRole stores role and features beside the active session auth state', () => {
    useAuthStore.getState().setAuth('http://localhost:8000', 'pw', '0.3.0')
    useAuthStore.getState().setRole({
      role: 'user',
      features: { search: true, config_read: 'minimal', config_write: false },
      edition: 'pro',
      edition_capabilities: {
        llm: true,
        warp_modes: ['auto', 'wireproxy', 'kernel', 'usque', 'warp-cli', 'external'],
        fetch_providers: ['builtin'],
        plugin_preinstalled: false,
      },
      guest_enabled: false,
      user_password_set: true,
      admin_password_set: true,
      admin_open: false,
    })
    const state = useAuthStore.getState()
    expect(state.role).toBe('user')
    expect(state.features).toEqual({
      search: true,
      config_read: 'minimal',
      config_write: false,
    })
    expect(state.edition).toBe('pro')
    expect(state.editionCapabilities).toEqual({
      llm: true,
      warp_modes: ['auto', 'wireproxy', 'kernel', 'usque', 'warp-cli', 'external'],
      fetch_providers: ['builtin'],
      plugin_preinstalled: false,
    })
    expect(sessionStorage.getItem('souwen_role')).toBe('user')
    expect(JSON.parse(sessionStorage.getItem('souwen_features') ?? '{}')).toEqual(state.features)
    expect(sessionStorage.getItem('souwen_edition')).toBe('pro')
    expect(JSON.parse(sessionStorage.getItem('souwen_editionCapabilities') ?? 'null'))
      .toEqual(state.editionCapabilities)
    expect(localStorage.getItem('souwen_features')).toBeNull()
  })

  it('setAuth clears stale whoami identity until the new verification succeeds', () => {
    useAuthStore.getState().setAuth('http://localhost:8000', 'old', '1.0.0')
    useAuthStore.getState().setRole({
      role: 'admin',
      features: { fetch: true },
      edition: 'full',
      edition_capabilities: {
        llm: true,
        warp_modes: ['auto'],
        fetch_providers: ['builtin', 'scrapling'],
        plugin_preinstalled: true,
      },
      guest_enabled: false,
      user_password_set: true,
      admin_password_set: true,
      admin_open: false,
    })

    useAuthStore.getState().setAuth('http://localhost:9000', 'new', '2.0.0')

    expect(useAuthStore.getState()).toMatchObject({
      role: 'guest',
      features: {},
      edition: null,
      editionCapabilities: null,
    })
    expect(sessionStorage.getItem('souwen_edition')).toBeNull()
    expect(sessionStorage.getItem('souwen_editionCapabilities')).toBeNull()
  })

  it('normalizes a legacy whoami payload without edition fields to null', () => {
    useAuthStore.getState().setAuth('http://localhost:8000', 'pw', '1.9.0')
    sessionStorage.setItem('souwen_edition', 'full')
    sessionStorage.setItem('souwen_editionCapabilities', '{"llm":true}')

    useAuthStore.getState().setRole({
      role: 'user',
      features: { search: true },
      guest_enabled: false,
      user_password_set: true,
      admin_password_set: true,
      admin_open: false,
    })

    expect(useAuthStore.getState()).toMatchObject({
      role: 'user',
      edition: null,
      editionCapabilities: null,
    })
    expect(sessionStorage.getItem('souwen_edition')).toBeNull()
    expect(sessionStorage.getItem('souwen_editionCapabilities')).toBeNull()
  })

  /**
   * 测试：登出清空状态和存储
   */
  it('logout clears state and both storages', () => {
    useAuthStore.getState().setAuth('http://localhost:8000', 'pw', '0.3.0', true)
    useAuthStore.getState().logout()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.version).toBe('')
    expect(state.features).toEqual({})
    expect(state.edition).toBeNull()
    expect(state.editionCapabilities).toBeNull()
    expect(localStorage.getItem('souwen_baseUrl')).toBeNull()
    expect(localStorage.getItem('souwen_version')).toBeNull()
    expect(localStorage.getItem('souwen_features')).toBeNull()
    expect(localStorage.getItem('souwen_edition')).toBeNull()
    expect(localStorage.getItem('souwen_editionCapabilities')).toBeNull()
    expect(sessionStorage.getItem('souwen_baseUrl')).toBeNull()
    expect(sessionStorage.getItem('souwen_version')).toBeNull()
    expect(sessionStorage.getItem('souwen_features')).toBeNull()
    expect(sessionStorage.getItem('souwen_edition')).toBeNull()
    expect(sessionStorage.getItem('souwen_editionCapabilities')).toBeNull()
  })

  /**
   * 测试：从 sessionStorage 恢复
   */
  it('loadFromStorage restores version from sessionStorage', () => {
    sessionStorage.setItem('souwen_baseUrl', 'http://x')
    sessionStorage.setItem('souwen_token', 'tok')
    sessionStorage.setItem('souwen_version', '1.2.3')
    sessionStorage.setItem('souwen_role', 'user')
    sessionStorage.setItem('souwen_features', JSON.stringify({ search: true, config_read: 'minimal' }))
    sessionStorage.setItem('souwen_edition', 'pro')
    sessionStorage.setItem('souwen_editionCapabilities', JSON.stringify({
      llm: true,
      warp_modes: ['auto'],
      fetch_providers: ['builtin'],
      plugin_preinstalled: false,
    }))
    useAuthStore.getState().loadFromStorage()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.version).toBe('1.2.3')
    expect(state.role).toBe('user')
    expect(state.features).toEqual({ search: true, config_read: 'minimal' })
    expect(state.edition).toBe('pro')
    expect(state.editionCapabilities?.fetch_providers).toEqual(['builtin'])
  })

  /**
   * 测试：回退到 localStorage
   */
  it('loadFromStorage falls back to localStorage', () => {
    localStorage.setItem('souwen_baseUrl', 'http://y')
    localStorage.setItem('souwen_token', 'tok2')
    localStorage.setItem('souwen_version', '2.0.0')
    localStorage.setItem('souwen_role', 'admin')
    localStorage.setItem('souwen_features', JSON.stringify({ fetch: true, doctor_full: true }))
    localStorage.setItem('souwen_edition', 'full')
    localStorage.setItem('souwen_editionCapabilities', JSON.stringify({
      llm: true,
      warp_modes: ['auto', 'kernel'],
      fetch_providers: ['builtin', 'scrapling'],
      plugin_preinstalled: true,
    }))
    useAuthStore.getState().loadFromStorage()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.version).toBe('2.0.0')
    expect(state.role).toBe('admin')
    expect(state.features).toEqual({ fetch: true, doctor_full: true })
    expect(state.edition).toBe('full')
    expect(state.editionCapabilities?.plugin_preinstalled).toBe(true)
  })

  it('treats malformed persisted edition capability data as unverified', () => {
    sessionStorage.setItem('souwen_baseUrl', 'http://x')
    sessionStorage.setItem('souwen_token', 'tok')
    sessionStorage.setItem('souwen_edition', 'enterprise')
    sessionStorage.setItem('souwen_editionCapabilities', JSON.stringify({
      llm: true,
      warp_modes: 'auto',
      fetch_providers: ['builtin'],
      plugin_preinstalled: false,
    }))

    useAuthStore.getState().loadFromStorage()

    expect(useAuthStore.getState().edition).toBeNull()
    expect(useAuthStore.getState().editionCapabilities).toBeNull()
  })

  /**
   * 测试：存储为空时不改变状态
   */
  it('loadFromStorage does nothing when storage is empty', () => {
    useAuthStore.getState().loadFromStorage()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
})
