/**
 * 文件用途：认证全局状态存储，使用 Zustand 管理登录状态、令牌与本地存储持久化
 *
 * 接口/函数清单：
 *     AuthState（接口）
 *         - 功能：认证状态树
 *         - 字段：
 *           - baseUrl string API 服务器基础 URL
 *           - token string JWT 访问令牌
 *           - isAuthenticated boolean 登录状态
 *           - version string 后端服务版本号
 *           - issuedAt number 令牌签发时间戳（ms，0 表示未登录）
 *           - setAuth(baseUrl, token, version, remember?) -> void 登录
 *           - logout() -> void 登出
 *           - loadFromStorage() -> void 从本地存储恢复状态
 *           - isExpired(ttlMs?) -> boolean 检查令牌是否过期
 *
 *     useAuthStore（Zustand hook）
 *         - 功能：全局认证状态存储 hook，用于获取/更新认证状态
 *         - 用法：const isAuth = useAuthStore(s => s.isAuthenticated)
 *
 * 常量：
 *     DEFAULT_TTL_MS = 30 * 60 * 1000（30 分钟）— 默认令牌有效期
 *
 * 关键逻辑：
 *
 *   setAuth 登录流程：
 *     1. 获取当前时间作为令牌签发时间戳
 *     2. 更新 Zustand 状态为已认证
 *     3. 清除 sessionStorage 和 localStorage 中的旧数据（防止残留）
 *     4. 根据 remember 参数选择存储位置：
 *        - remember=true → localStorage（跨标签页，关闭浏览器才清除）
 *        - remember=false（默认）→ sessionStorage（标签页关闭即清除，更安全）
 *     5. 同时设置 souwen_remember 标志位（用于下次启动时判断存储位置）
 *
 *   logout 登出流程：
 *     1. 清空所有认证状态为初始值
 *     2. 同时清除 localStorage 和 sessionStorage 中的全部相关字段（彻底清净）
 *
 *   loadFromStorage 启动恢复流程：
 *     1. 优先从 sessionStorage 恢复（更安全）
 *     2. 回退到 localStorage（用户勾选"记住我"时）
 *     3. 若两个存储都有数据，sessionStorage 优先
 *     4. 若 baseUrl 存在（表示有效登录），更新状态为已认证
 *
 *   isExpired 令牌过期检查：
 *     1. 若未认证，返回 false（无令牌，不算过期）
 *     2. 若 issuedAt 为 0（异常状态），返回 true（认为已过期）
 *     3. 检查当前时间 - 签发时间是否超过 ttlMs，超过则过期
 *
 * 存储键约定：
 *     - souwen_baseUrl: API 基础 URL
 *     - souwen_token: JWT 访问令牌
 *     - souwen_version: 后端版本号
 *     - souwen_issuedAt: 令牌签发时间戳（毫秒）
 *     - souwen_remember: 是否勾选"记住我"标志
 *
 * 模块依赖：
 *     - zustand: 状态管理库
 */

import { create } from 'zustand'

/**
 * 认证状态树接口
 */
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

/**
 * 认证全局状态存储
 * 使用 Zustand 管理登录状态、JWT 令牌、服务器信息
 */
export const useAuthStore = create<AuthState>((set, get) => ({
  baseUrl: '',
  token: '',
  isAuthenticated: false,
  version: '',
  issuedAt: 0,

  /**
   * 设置认证状态（登录）
   * 同时更新 sessionStorage 或 localStorage（根据 remember 参数）
   *
   * 流程：
   *   1. 记录当前时间作为令牌签发时间戳
   *   2. 清除两端旧数据（防止登录凭证污染）
   *   3. 选择存储位置并保存：
   *      - 默认存 sessionStorage（标签页关闭清除，更安全）
   *      - remember=true 时用 localStorage（跨标签页持久化）
   *   4. 标记 remember 标志供下次启动识别
   */
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

  /**
   * 登出
   * 清空所有认证状态和本地存储
   */
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

  /**
   * 从本地存储恢复认证状态
   * 优先 sessionStorage（更安全），回退 localStorage（记住我）
   *
   * 流程：
   *   1. 依次尝试从 sessionStorage、localStorage 读取各字段
   *   2. issuedAt 非数字时默认为 0
   *   3. 若 baseUrl 非空，表示有有效登录，更新状态为已认证
   */
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

  /**
   * 检查令牌是否过期
   * 对比当前时间与签发时间，若超过 ttlMs 则过期
   */
  isExpired: (ttlMs = DEFAULT_TTL_MS) => {
    const { issuedAt, isAuthenticated } = get()
    if (!isAuthenticated) return false
    if (!issuedAt) return true
    return Date.now() - issuedAt > ttlMs
  },
}))
