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

  /**
   * 测试：登出清空状态和存储
   */
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

  /**
   * 测试：从 sessionStorage 恢复
   */
  it('loadFromStorage restores version from sessionStorage', () => {
    sessionStorage.setItem('souwen_baseUrl', 'http://x')
    sessionStorage.setItem('souwen_token', 'tok')
    sessionStorage.setItem('souwen_version', '1.2.3')
    useAuthStore.getState().loadFromStorage()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.version).toBe('1.2.3')
  })

  /**
   * 测试：回退到 localStorage
   */
  it('loadFromStorage falls back to localStorage', () => {
    localStorage.setItem('souwen_baseUrl', 'http://y')
    localStorage.setItem('souwen_token', 'tok2')
    localStorage.setItem('souwen_version', '2.0.0')
    useAuthStore.getState().loadFromStorage()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.version).toBe('2.0.0')
  })

  /**
   * 测试：存储为空时不改变状态
   */
  it('loadFromStorage does nothing when storage is empty', () => {
    useAuthStore.getState().loadFromStorage()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
})
