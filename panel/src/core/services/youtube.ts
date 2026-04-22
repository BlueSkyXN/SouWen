/**
 * 文件用途：YouTube 相关 API — 趋势榜、视频详情、字幕。
 *
 * 注意：方法名沿用原 ApiService 的命名（getYouTubeTrending 等，camelCase 中 "YouTube"
 * 含两个大写字母）。如需在调用方使用 api.getYoutubeTrending 风格请重新审视命名约定。
 */

import type { ApiServiceBase } from './_base'
import type {
  YouTubeTrendingResponse,
  YouTubeVideoDetailResponse,
  YouTubeTranscriptResponse,
} from '../types'

export interface YoutubeApi {
  getYouTubeTrending(region?: string, category?: string, maxResults?: number, signal?: AbortSignal, timeout?: number): Promise<YouTubeTrendingResponse>
  getYouTubeVideoDetail(videoId: string, signal?: AbortSignal, timeout?: number): Promise<YouTubeVideoDetailResponse>
  getYouTubeTranscript(videoId: string, lang?: string, signal?: AbortSignal, timeout?: number): Promise<YouTubeTranscriptResponse>
}

export const youtubeMethods = {
  async getYouTubeTrending(
    this: ApiServiceBase,
    region = 'US',
    category = '',
    maxResults = 20,
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<YouTubeTrendingResponse> {
    const params = new URLSearchParams({
      region,
      max_results: String(maxResults),
    })
    if (category) params.set('category', category)
    if (timeout) params.set('timeout', String(timeout))
    return this.request<YouTubeTrendingResponse>(`/api/v1/youtube/trending?${params}`, {
      headers: this.headers(),
      signal,
    })
  },

  async getYouTubeVideoDetail(
    this: ApiServiceBase,
    videoId: string,
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<YouTubeVideoDetailResponse> {
    const params = new URLSearchParams()
    if (timeout) params.set('timeout', String(timeout))
    const qs = params.toString()
    return this.request<YouTubeVideoDetailResponse>(
      `/api/v1/youtube/video/${encodeURIComponent(videoId)}${qs ? '?' + qs : ''}`,
      { headers: this.headers(), signal },
    )
  },

  async getYouTubeTranscript(
    this: ApiServiceBase,
    videoId: string,
    lang = 'en',
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<YouTubeTranscriptResponse> {
    const params = new URLSearchParams({ lang })
    if (timeout) params.set('timeout', String(timeout))
    return this.request<YouTubeTranscriptResponse>(
      `/api/v1/youtube/transcript/${encodeURIComponent(videoId)}?${params}`,
      { headers: this.headers(), signal },
    )
  },
}
