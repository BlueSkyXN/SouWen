/**
 * 文件用途：API 服务基础设施 — 单例类、通用 request、超时与白名单校验。
 *
 * 拆分背景：原 panel/src/core/services/api.ts 已按域拆分到 search/fetch/youtube 等文件。
 * 本文件保留：
 *   - REQUEST_TIMEOUT_MS / ALLOWED_API_HOSTS 常量
 *   - assertBaseUrlAllowed(baseUrl) 安全校验
 *   - ApiServiceBase 类：baseUrl/token 访问器、headers()、request<T>()、health()、verifyAuth()
 *
 * 各域 mixin（search.ts/fetch.ts/...）通过 Object.assign(ApiService.prototype, ...) 在
 * services/index.ts 中合并。为允许 mixin 内部访问 request/headers，这两个方法以及 baseUrl/token
 * 的访问器使用 public 可见性（保持兼容，原内部用法不变）。
 *
 * 模块依赖：
 *     - ../stores/authStore: 认证全局状态（baseUrl、token）
 *     - ../lib/errors: AppError 错误类
 *     - ../i18n: 国际化（错误消息）
 *     - ../types: 后端响应类型定义
 */

import { useAuthStore } from '../stores/authStore'
import { AppError } from '../lib/errors'
import i18n from '../i18n'
import type { HealthResponse } from '../types'

export const REQUEST_TIMEOUT_MS = 30_000

/**
 * baseUrl 白名单校验
 * 防止凭证被错误地发送到任意第三方域
 *
 * 规则：
 *   - 协议必须为 http 或 https
 *   - 默认允许同源请求（window.location.origin）
 *   - 非同源需匹配 VITE_ALLOWED_API_HOSTS 环境变量（逗号分隔主机列表）
 */
export const ALLOWED_API_HOSTS: string[] = (
  (import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_ALLOWED_API_HOSTS ?? ''
)
  .split(',')
  .map((s: string) => s.trim())
  .filter(Boolean)

/**
 * 校验 baseUrl 是否可信
 * 非法 URL 或不在白名单内时抛出错误
 */
export function assertBaseUrlAllowed(baseUrl: string): void {
  if (!baseUrl) return // 空串 → 同源相对路径，放行
  let parsed: URL
  try {
    parsed = new URL(baseUrl)
  } catch {
    throw new Error(`非法的 baseUrl: ${baseUrl}`)
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error(`baseUrl 协议必须为 http/https: ${baseUrl}`)
  }
  // 浏览器环境下的同源放行
  if (typeof window !== 'undefined' && window.location) {
    if (parsed.origin === window.location.origin) return
  }
  if (ALLOWED_API_HOSTS.length === 0) return // 未配置白名单，保留默认行为
  const hostMatches = ALLOWED_API_HOSTS.some((h) => h === parsed.host || h === parsed.hostname)
  if (!hostMatches) {
    throw new Error(
      `baseUrl 未在 VITE_ALLOWED_API_HOSTS 白名单内: ${parsed.host}（允许：${ALLOWED_API_HOSTS.join(', ')}）`,
    )
  }
}

/**
 * API 服务基础类
 * 提供请求基础设施：baseUrl/token 解析、统一 headers、带超时与错误归类的 request、
 * 以及无认证的 health / verifyAuth 端点。其余按域方法通过 mixin 注入到 prototype。
 */
export class ApiServiceBase {
  /**
   * 获取当前认证状态中的 API 基础 URL
   */
  get baseUrl(): string {
    const url = useAuthStore.getState().baseUrl
    assertBaseUrlAllowed(url)
    return url
  }

  /**
   * 获取当前认证令牌
   */
  get token(): string {
    return useAuthStore.getState().token
  }

  /**
   * 构造请求头（包含 Content-Type 和可选的认证令牌）
   */
  headers(auth = true): HeadersInit {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (auth && this.token) {
      h['Authorization'] = `Bearer ${this.token}`
    }
    return h
  }

  /**
   * 通用 HTTP 请求方法
   * 处理认证、超时、错误分类、令牌过期登出
   *
   * 超时处理流程：
   *   1. 创建 AbortController 管理超时
   *   2. 若上游已传入 AbortSignal（如组件卸载），则关联两个信号
   *   3. 默认 30 秒后若未收到响应，自动 abort；可通过 options.timeoutMs 覆盖
   *   4. 区分超时错误与上游中止
   *
   * @param options.timeoutMs 可选的客户端超时时间（毫秒），用于覆盖默认的 REQUEST_TIMEOUT_MS
   */
  async request<T>(path: string, options?: RequestInit & { timeoutMs?: number }): Promise<T> {
    const controller = new AbortController()
    const upstreamSignal = options?.signal
    let timedOut = false
    const abortFromUpstream = () => controller.abort(upstreamSignal?.reason)
    if (upstreamSignal?.aborted) {
      abortFromUpstream()
    }
    upstreamSignal?.addEventListener('abort', abortFromUpstream)
    const effectiveTimeout = options?.timeoutMs ?? REQUEST_TIMEOUT_MS
    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, effectiveTimeout)

    // 剥离 timeoutMs，避免传入浏览器原生 fetch 引发未知属性
    const { timeoutMs: _timeoutMs, ...fetchOptions } = options ?? {}

    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        ...fetchOptions,
        signal: controller.signal,
      })

      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText)
        const err = AppError.fromResponse(res.status, text)
        // 认证失败时自动登出
        if (err.isAuth) useAuthStore.getState().logout()
        throw err
      }

      return (await res.json()) as T
    } catch (err) {
      if (err instanceof AppError) throw err
      if (err instanceof Error && err.name === 'AbortError' && upstreamSignal?.aborted) {
        throw err
      }
      if (timedOut) {
        throw AppError.network(new Error(i18n.t('common.requestTimeout')))
      }
      throw AppError.network(err)
    } finally {
      clearTimeout(timer)
      upstreamSignal?.removeEventListener('abort', abortFromUpstream)
    }
  }

  /**
   * 健康检查端点（无认证）
   * 用于验证 API 服务可用性及获取版本信息
   */
  async health(baseUrl?: string): Promise<HealthResponse> {
    const url = baseUrl ?? this.baseUrl
    assertBaseUrlAllowed(url)
    try {
      const res = await fetch(`${url}/health`, {
        signal: AbortSignal.timeout(10_000),
      })
      if (!res.ok) throw AppError.fromResponse(res.status, '')
      return (await res.json()) as HealthResponse
    } catch (err) {
      if (err instanceof AppError) throw err
      throw AppError.network(err)
    }
  }

  /**
   * 验证认证凭证
   * 用于登录流程中的凭证有效性检查
   */
  async verifyAuth(baseUrl: string, token: string): Promise<void> {
    assertBaseUrlAllowed(baseUrl)
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    try {
      const res = await fetch(`${baseUrl}/api/v1/sources`, {
        headers,
        signal: AbortSignal.timeout(10_000),
      })
      if (!res.ok) throw AppError.fromResponse(res.status, await res.text().catch(() => ''))
    } catch (err) {
      if (err instanceof AppError) throw err
      throw AppError.network(err)
    }
  }
}
