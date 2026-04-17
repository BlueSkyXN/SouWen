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

// baseUrl 白名单：避免凭证被发送到任意第三方域
// - 协议必须为 http/https
// - 默认允许同源（window.location.origin）不校验
// - 非同源时需匹配 VITE_ALLOWED_API_HOSTS（逗号分隔 host 列表），否则拒绝
const ALLOWED_API_HOSTS: string[] = (
  (import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_ALLOWED_API_HOSTS ?? ''
)
  .split(',')
  .map((s: string) => s.trim())
  .filter(Boolean)

/** 校验 baseUrl 是否可信；非法时抛错 */
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

class ApiService {
  private get baseUrl(): string {
    const url = useAuthStore.getState().baseUrl
    assertBaseUrlAllowed(url)
    return url
  }

  private get token(): string {
    return useAuthStore.getState().token
  }

  private headers(auth = true): HeadersInit {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (auth && this.token) {
      h['Authorization'] = `Bearer ${this.token}`
    }
    return h
  }

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

  async searchPaper(q: string, sources: string, perPage: number, signal?: AbortSignal): Promise<SearchResponse> {
    return this.request<SearchResponse>(
      `/api/v1/search/paper?q=${encodeURIComponent(q)}&sources=${encodeURIComponent(sources)}&per_page=${perPage}`,
      { headers: this.headers(), signal },
    )
  }

  async searchPatent(q: string, sources: string, perPage: number, signal?: AbortSignal): Promise<SearchResponse> {
    return this.request<SearchResponse>(
      `/api/v1/search/patent?q=${encodeURIComponent(q)}&sources=${encodeURIComponent(sources)}&per_page=${perPage}`,
      { headers: this.headers(), signal },
    )
  }

  async searchWeb(q: string, engines: string, maxResults: number, signal?: AbortSignal): Promise<WebSearchResponse> {
    return this.request<WebSearchResponse>(
      `/api/v1/search/web?q=${encodeURIComponent(q)}&engines=${encodeURIComponent(engines)}&max_results=${maxResults}`,
      { headers: this.headers(), signal },
    )
  }

  async getSources(): Promise<SourcesResponse> {
    return this.request<SourcesResponse>('/api/v1/sources', { headers: this.headers() })
  }

  async getConfig(): Promise<ConfigResponse> {
    return this.request<ConfigResponse>('/api/v1/admin/config', { headers: this.headers() })
  }

  async reloadConfig(): Promise<ReloadResponse> {
    return this.request<ReloadResponse>('/api/v1/admin/config/reload', {
      method: 'POST',
      headers: this.headers(),
    })
  }

  async getDoctor(): Promise<DoctorResponse> {
    return this.request<DoctorResponse>('/api/v1/admin/doctor', { headers: this.headers() })
  }

  async getWarpStatus(): Promise<WarpStatus> {
    return this.request<WarpStatus>('/api/v1/admin/warp', { headers: this.headers() })
  }

  async enableWarp(mode = 'auto', socksPort = 1080, endpoint?: string): Promise<WarpActionResult> {
    const params = new URLSearchParams({ mode, socks_port: String(socksPort) })
    if (endpoint) params.set('endpoint', endpoint)
    return this.request<WarpActionResult>(`/api/v1/admin/warp/enable?${params}`, {
      method: 'POST',
      headers: this.headers(),
    })
  }

  async disableWarp(): Promise<WarpActionResult> {
    return this.request<WarpActionResult>('/api/v1/admin/warp/disable', {
      method: 'POST',
      headers: this.headers(),
    })
  }

  async getHttpBackend(): Promise<HttpBackendResponse> {
    return this.request<HttpBackendResponse>('/api/v1/admin/http-backend', {
      headers: this.headers(),
    })
  }

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

  async getSourcesConfig(): Promise<Record<string, SourceChannelConfig>> {
    return this.request<Record<string, SourceChannelConfig>>('/api/v1/admin/sources/config', {
      headers: this.headers(),
    })
  }

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

export const api = new ApiService()
