import { useAuthStore } from '../stores/authStore'
import { AppError } from '../lib/errors'
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
} from '../types'

const REQUEST_TIMEOUT_MS = 30_000

class ApiService {
  private get baseUrl(): string {
    return useAuthStore.getState().baseUrl
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
        throw AppError.network(new Error('请求超时，请稍后重试'))
      }
      throw AppError.network(err)
    } finally {
      clearTimeout(timer)
      upstreamSignal?.removeEventListener('abort', abortFromUpstream)
    }
  }

  async health(baseUrl?: string): Promise<HealthResponse> {
    const url = baseUrl ?? this.baseUrl
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
}

export const api = new ApiService()
