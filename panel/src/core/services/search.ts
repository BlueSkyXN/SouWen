/**
 * 文件用途：搜索类 API（论文/专利/网页/图片/视频）。
 * 通过 mixin 注入到 ApiService 原型；保持原 api.searchPaper(...) 等调用接口不变。
 */

import type { ApiServiceBase } from './_base'
import type {
  SearchResponse,
  WebSearchResponse,
  ImageSearchResponse,
  VideoSearchResponse,
} from '../types'

export interface SearchApi {
  searchPaper(q: string, sources: string, perPage: number, signal?: AbortSignal, timeout?: number): Promise<SearchResponse>
  searchPatent(q: string, sources: string, perPage: number, signal?: AbortSignal, timeout?: number): Promise<SearchResponse>
  searchWeb(q: string, engines: string, maxResults: number, signal?: AbortSignal, timeout?: number): Promise<WebSearchResponse>
  searchImages(q: string, maxResults?: number, region?: string, safesearch?: string, signal?: AbortSignal, timeout?: number): Promise<ImageSearchResponse>
  searchVideos(q: string, maxResults?: number, region?: string, safesearch?: string, signal?: AbortSignal, timeout?: number): Promise<VideoSearchResponse>
}

export const searchMethods = {
  /** 搜索论文 */
  async searchPaper(this: ApiServiceBase, q: string, sources: string, perPage: number, signal?: AbortSignal, timeout?: number): Promise<SearchResponse> {
    let url = `/api/v1/search/paper?q=${encodeURIComponent(q)}&sources=${encodeURIComponent(sources)}&per_page=${perPage}`
    if (timeout) url += `&timeout=${timeout}`
    return this.request<SearchResponse>(url, { headers: this.headers(), signal })
  },

  /** 搜索专利 */
  async searchPatent(this: ApiServiceBase, q: string, sources: string, perPage: number, signal?: AbortSignal, timeout?: number): Promise<SearchResponse> {
    let url = `/api/v1/search/patent?q=${encodeURIComponent(q)}&sources=${encodeURIComponent(sources)}&per_page=${perPage}`
    if (timeout) url += `&timeout=${timeout}`
    return this.request<SearchResponse>(url, { headers: this.headers(), signal })
  },

  /** 网页搜索 */
  async searchWeb(this: ApiServiceBase, q: string, engines: string, maxResults: number, signal?: AbortSignal, timeout?: number): Promise<WebSearchResponse> {
    let url = `/api/v1/search/web?q=${encodeURIComponent(q)}&engines=${encodeURIComponent(engines)}&max_results=${maxResults}`
    if (timeout) url += `&timeout=${timeout}`
    return this.request<WebSearchResponse>(url, { headers: this.headers(), signal })
  },

  /** 图片搜索 */
  async searchImages(
    this: ApiServiceBase,
    q: string,
    maxResults = 20,
    region = 'wt-wt',
    safesearch = 'moderate',
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<ImageSearchResponse> {
    const params = new URLSearchParams({
      q,
      max_results: String(maxResults),
      region,
      safesearch,
    })
    if (timeout) params.set('timeout', String(timeout))
    return this.request<ImageSearchResponse>(`/api/v1/search/images?${params}`, {
      headers: this.headers(),
      signal,
    })
  },

  /** 视频搜索 */
  async searchVideos(
    this: ApiServiceBase,
    q: string,
    maxResults = 20,
    region = 'wt-wt',
    safesearch = 'moderate',
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<VideoSearchResponse> {
    const params = new URLSearchParams({
      q,
      max_results: String(maxResults),
      region,
      safesearch,
    })
    if (timeout) params.set('timeout', String(timeout))
    return this.request<VideoSearchResponse>(`/api/v1/search/videos?${params}`, {
      headers: this.headers(),
      signal,
    })
  },
}
