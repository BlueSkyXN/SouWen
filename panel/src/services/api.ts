import { useAuthStore } from '../stores/authStore'
import type {
  HealthResponse,
  SourcesResponse,
  DoctorResponse,
  ConfigResponse,
  ReloadResponse,
  SearchResponse,
  WebSearchResponse,
} from '../types'

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
    const res = await fetch(`${this.baseUrl}${path}`, options)
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new Error(`${res.status}: ${text}`)
    }
    return res.json() as Promise<T>
  }

  /* === Public === */
  async health(baseUrl?: string): Promise<HealthResponse> {
    const url = baseUrl ?? this.baseUrl
    const res = await fetch(`${url}/health`)
    if (!res.ok) throw new Error(`${res.status}`)
    return res.json() as Promise<HealthResponse>
  }

  /* === Search === */
  async searchPaper(q: string, sources: string, perPage: number): Promise<SearchResponse> {
    return this.request<SearchResponse>(
      `/api/v1/search/paper?q=${encodeURIComponent(q)}&sources=${encodeURIComponent(sources)}&per_page=${perPage}`,
      { headers: this.headers() },
    )
  }

  async searchPatent(q: string, sources: string, perPage: number): Promise<SearchResponse> {
    return this.request<SearchResponse>(
      `/api/v1/search/patent?q=${encodeURIComponent(q)}&sources=${encodeURIComponent(sources)}&per_page=${perPage}`,
      { headers: this.headers() },
    )
  }

  async searchWeb(q: string, engines: string, maxResults: number): Promise<WebSearchResponse> {
    return this.request<WebSearchResponse>(
      `/api/v1/search/web?q=${encodeURIComponent(q)}&engines=${encodeURIComponent(engines)}&max_results=${maxResults}`,
      { headers: this.headers() },
    )
  }

  async getSources(): Promise<SourcesResponse> {
    return this.request<SourcesResponse>('/api/v1/sources', { headers: this.headers() })
  }

  /* === Admin === */
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
}

export const api = new ApiService()
