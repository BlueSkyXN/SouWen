/**
 * 文件用途：API 服务层，封装与后端的 HTTP 通信，包括认证、请求签名、超时管理、URL 白名单校验
 *
 * 类/函数清单：
 *     assertBaseUrlAllowed(baseUrl: string) -> void
 *         - 功能：校验 baseUrl 是否在安全白名单内，防止凭证泄露到第三方域
 *         - 输入：baseUrl API 基础 URL
 *         - 抛出异常：URL 格式非法、协议不是 http/https、域名不在白名单内时抛出 Error
 *         - 逻辑：
 *           - 空串允许（相对路径，同源）
 *           - 同源请求无需白名单检查（window.location.origin）
 *           - 跨域请求需匹配 VITE_ALLOWED_API_HOSTS 环境变量（逗号分隔）
 *
 *     ApiService（类）
 *         - 功能：单例 API 服务，管理所有与后端的通信
 *         - 私有属性：baseUrl（动态获取自认证存储）、token（动态获取自认证存储）
 *
 *         - request<T>(path: string, options?: RequestInit) -> Promise<T>
 *             - 功能：通用 HTTP 请求方法，处理认证头、超时、错误分类
 *             - 特性：
 *               - 自动添加 Bearer token 认证头
 *               - 30 秒请求超时（REQUEST_TIMEOUT_MS）
 *               - 支持上游 AbortSignal 传递（允许调用方中止请求）
 *               - 自动登出处理：401/403 响应时触发登出
 *               - 区分网络错误和超时错误
 *
 *         - health(baseUrl?: string) -> Promise<HealthResponse>
 *             - 功能：健康检查端点（无认证），用于验证 API 服务可用性
 *             - 输入：baseUrl 可选，默认使用当前 baseUrl
 *             - 输出：{status, version} 服务状态与版本信息
 *
 *         - verifyAuth(baseUrl: string, token: string) -> Promise<void>
 *             - 功能：认证凭证验证，用于登录流程中的凭证验证
 *             - 输入：baseUrl 目标 API 地址，token JWT 令牌
 *             - 抛出异常：凭证无效时抛出 AppError
 *             - 逻辑：尝试访问 /api/v1/sources，通过则认证成功
 *
 *         - 搜索类方法：searchPaper/searchPatent/searchWeb
 *             - 功能：对应论文、专利、网页三种搜索类型
 *             - 参数：q 查询词，sources/engines 源列表，perPage/maxResults 分页
 *             - 返回：SearchResponse / WebSearchResponse
 *
 *         - getSources() -> Promise<SourcesResponse>
 *             - 功能：获取可用的数据源列表
 *
 *         - getConfig() / reloadConfig() / getDoctor()
 *             - 功能：管理端点，获取配置、重载配置、诊断源状态
 *
 *         - Warp 代理管理：getWarpStatus / enableWarp / disableWarp
 *             - 功能：Cloudflare Warp 代理的启停与状态查询
 *
 *         - HTTP 后端管理：getHttpBackend / updateHttpBackend
 *             - 功能：管理 HTTP 代理后端配置（curl-cffi 等）
 *
 *         - 源配置管理：getSourcesConfig / updateSourceConfig
 *             - 功能：获取/修改各数据源的启用状态、代理、API 密钥等
 *
 * 常量/配置：
 *     REQUEST_TIMEOUT_MS = 30_000（30 秒）— 请求超时时间
 *     ALLOWED_API_HOSTS — 从 VITE_ALLOWED_API_HOSTS 环境变量解析的主机白名单
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
import type {
  HealthResponse,
  SourcesResponse,
  DoctorResponse,
  ConfigResponse,
  ReloadResponse,
  SearchResponse,
  WebSearchResponse,
  WarpStatus,
  WarpActionResult,
  HttpBackendResponse,
  SourceChannelConfig,
} from '../types'

const REQUEST_TIMEOUT_MS = 30_000

/**
 * baseUrl 白名单校验
 * 防止凭证被错误地发送到任意第三方域
 *
 * 规则：
 *   - 协议必须为 http 或 https
 *   - 默认允许同源请求（window.location.origin）
 *   - 非同源需匹配 VITE_ALLOWED_API_HOSTS 环境变量（逗号分隔主机列表）
 */
const ALLOWED_API_HOSTS: string[] = (
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
 * API 服务单例
 * 负责管理所有与后端的 HTTP 通信
 */
class ApiService {
  /**
   * 获取当前认证状态中的 API 基础 URL
   */
  private get baseUrl(): string {
    const url = useAuthStore.getState().baseUrl
    assertBaseUrlAllowed(url)
    return url
  }

  /**
   * 获取当前认证令牌
   */
  private get token(): string {
    return useAuthStore.getState().token
  }

  /**
   * 构造请求头（包含 Content-Type 和可选的认证令牌）
   */
  private headers(auth = true): HeadersInit {
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
   *   3. 30 秒后若未收到响应，自动 abort
   *   4. 区分超时错误与上游中止
   */
  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const controller = new AbortController()
    const upstreamSignal = options?.signal
    let timedOut = false
    const abortFromUpstream = () => controller.abort(upstreamSignal?.reason)
    if (upstreamSignal?.aborted) {
      abortFromUpstream()
    }
    upstreamSignal?.addEventListener('abort', abortFromUpstream)
    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, REQUEST_TIMEOUT_MS)

    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        ...options,
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

  /**
   * 搜索论文
   */
  async searchPaper(q: string, sources: string, perPage: number, signal?: AbortSignal): Promise<SearchResponse> {
    return this.request<SearchResponse>(
      `/api/v1/search/paper?q=${encodeURIComponent(q)}&sources=${encodeURIComponent(sources)}&per_page=${perPage}`,
      { headers: this.headers(), signal },
    )
  }

  /**
   * 搜索专利
   */
  async searchPatent(q: string, sources: string, perPage: number, signal?: AbortSignal): Promise<SearchResponse> {
    return this.request<SearchResponse>(
      `/api/v1/search/patent?q=${encodeURIComponent(q)}&sources=${encodeURIComponent(sources)}&per_page=${perPage}`,
      { headers: this.headers(), signal },
    )
  }

  /**
   * 网页搜索
   */
  async searchWeb(q: string, engines: string, maxResults: number, signal?: AbortSignal): Promise<WebSearchResponse> {
    return this.request<WebSearchResponse>(
      `/api/v1/search/web?q=${encodeURIComponent(q)}&engines=${encodeURIComponent(engines)}&max_results=${maxResults}`,
      { headers: this.headers(), signal },
    )
  }

  /**
   * 获取可用的数据源列表
   */
  async getSources(): Promise<SourcesResponse> {
    return this.request<SourcesResponse>('/api/v1/sources', { headers: this.headers() })
  }

  /**
   * 获取系统配置
   */
  async getConfig(): Promise<ConfigResponse> {
    return this.request<ConfigResponse>('/api/v1/admin/config', { headers: this.headers() })
  }

  /**
   * 重载系统配置
   */
  async reloadConfig(): Promise<ReloadResponse> {
    return this.request<ReloadResponse>('/api/v1/admin/config/reload', {
      method: 'POST',
      headers: this.headers(),
    })
  }

  /**
   * 获取系统诊断信息（源可达性、配置状态等）
   */
  async getDoctor(): Promise<DoctorResponse> {
    return this.request<DoctorResponse>('/api/v1/admin/doctor', { headers: this.headers() })
  }

  /**
   * 获取 Warp 代理状态
   */
  async getWarpStatus(): Promise<WarpStatus> {
    return this.request<WarpStatus>('/api/v1/admin/warp', { headers: this.headers() })
  }

  /**
   * 启用 Warp 代理
   */
  async enableWarp(mode = 'auto', socksPort = 1080, endpoint?: string): Promise<WarpActionResult> {
    const params = new URLSearchParams({ mode, socks_port: String(socksPort) })
    if (endpoint) params.set('endpoint', endpoint)
    return this.request<WarpActionResult>(`/api/v1/admin/warp/enable?${params}`, {
      method: 'POST',
      headers: this.headers(),
    })
  }

  /**
   * 禁用 Warp 代理
   */
  async disableWarp(): Promise<WarpActionResult> {
    return this.request<WarpActionResult>('/api/v1/admin/warp/disable', {
      method: 'POST',
      headers: this.headers(),
    })
  }

  /**
   * 获取 HTTP 后端配置（代理、curl-cffi 等）
   */
  async getHttpBackend(): Promise<HttpBackendResponse> {
    return this.request<HttpBackendResponse>('/api/v1/admin/http-backend', {
      headers: this.headers(),
    })
  }

  /**
   * 更新 HTTP 后端配置
   */
  async updateHttpBackend(params: {
    default?: string
    source?: string
    backend?: string
  }): Promise<{ status: string; default: string; overrides: Record<string, string> }> {
    const searchParams = new URLSearchParams()
    if (params.default) searchParams.set('default', params.default)
    if (params.source) searchParams.set('source', params.source)
    if (params.backend) searchParams.set('backend', params.backend)
    return this.request(`/api/v1/admin/http-backend?${searchParams}`, {
      method: 'PUT',
      headers: this.headers(),
    })
  }

  /**
   * 获取所有数据源的配置信息
   */
  async getSourcesConfig(): Promise<Record<string, SourceChannelConfig>> {
    return this.request<Record<string, SourceChannelConfig>>('/api/v1/admin/sources/config', {
      headers: this.headers(),
    })
  }

  /**
   * 更新指定数据源的配置
   */
  async updateSourceConfig(
    sourceName: string,
    params: { enabled?: boolean; proxy?: string; http_backend?: string; base_url?: string; api_key?: string }
  ): Promise<{ status: string; source: string }> {
    return this.request(`/api/v1/admin/sources/config/${encodeURIComponent(sourceName)}`, {
      method: 'PUT',
      headers: this.headers(),
      body: JSON.stringify(params),
    })
  }
}

/**
 * API 服务单例
 */
export const api = new ApiService()
