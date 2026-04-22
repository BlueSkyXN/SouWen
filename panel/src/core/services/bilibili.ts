/**
 * 文件用途：Bilibili 直连 API（视频搜索、视频详情、用户搜索、专栏搜索）。
 *
 * 后端路由（详见 cloud/api/routers/bilibili.py）：
 *   - GET /api/v1/bilibili/search?keyword=&max_results=&order=
 *   - GET /api/v1/bilibili/video/{bvid}
 *   - GET /api/v1/bilibili/search/users?keyword=&max_results=
 *   - GET /api/v1/bilibili/search/articles?keyword=&max_results=
 */

import type { ApiServiceBase } from './_base'
import type {
  BilibiliSearchResponse,
  BilibiliVideoDetailResponse,
  BilibiliUserSearchResponse,
  BilibiliArticleSearchResponse,
} from '../types'

export interface BilibiliApi {
  searchBilibili(
    keyword: string,
    maxResults?: number,
    order?: string,
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<BilibiliSearchResponse>
  getBilibiliVideoDetail(
    bvid: string,
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<BilibiliVideoDetailResponse>
  searchBilibiliUsers(
    keyword: string,
    maxResults?: number,
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<BilibiliUserSearchResponse>
  searchBilibiliArticles(
    keyword: string,
    maxResults?: number,
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<BilibiliArticleSearchResponse>
}

export const bilibiliMethods = {
  async searchBilibili(
    this: ApiServiceBase,
    keyword: string,
    maxResults = 20,
    order = 'totalrank',
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<BilibiliSearchResponse> {
    const params = new URLSearchParams({
      keyword,
      max_results: String(maxResults),
      order,
    })
    if (timeout) params.set('timeout', String(timeout))
    return this.request<BilibiliSearchResponse>(`/api/v1/bilibili/search?${params}`, {
      headers: this.headers(),
      signal,
    })
  },

  async getBilibiliVideoDetail(
    this: ApiServiceBase,
    bvid: string,
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<BilibiliVideoDetailResponse> {
    const params = new URLSearchParams()
    if (timeout) params.set('timeout', String(timeout))
    const qs = params.toString()
    return this.request<BilibiliVideoDetailResponse>(
      `/api/v1/bilibili/video/${encodeURIComponent(bvid)}${qs ? '?' + qs : ''}`,
      { headers: this.headers(), signal },
    )
  },

  async searchBilibiliUsers(
    this: ApiServiceBase,
    keyword: string,
    maxResults = 20,
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<BilibiliUserSearchResponse> {
    const params = new URLSearchParams({ keyword, max_results: String(maxResults) })
    if (timeout) params.set('timeout', String(timeout))
    return this.request<BilibiliUserSearchResponse>(
      `/api/v1/bilibili/search/users?${params}`,
      { headers: this.headers(), signal },
    )
  },

  async searchBilibiliArticles(
    this: ApiServiceBase,
    keyword: string,
    maxResults = 20,
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<BilibiliArticleSearchResponse> {
    const params = new URLSearchParams({ keyword, max_results: String(maxResults) })
    if (timeout) params.set('timeout', String(timeout))
    return this.request<BilibiliArticleSearchResponse>(
      `/api/v1/bilibili/search/articles?${params}`,
      { headers: this.headers(), signal },
    )
  },
}
