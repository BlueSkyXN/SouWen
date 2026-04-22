/**
 * 文件用途：services 层装配入口。
 *
 * 职责：
 *   1. 将 _base.ts 的 ApiServiceBase 与各域 mixin（searchMethods / fetchMethods / ...）
 *      合并成最终的 ApiService 类；
 *   2. 各域方法通过 `Object.assign(ApiService.prototype, ...)` 注入到原型链，避免
 *      重复书写方法签名；同时通过同名 interface 声明合并，将各方法显式宣告为
 *      ApiService 的"成员方法"（method shorthand），保持与原单一类等价的类型形态，
 *      使 vitest `vi.mocked()` 等工具能识别其为可 mock 方法；
 *   3. 暴露单例 `api` 与 `default` 导出，`import { api } from '@core/services/api'`
 *      及 `import api from '@core/services/api'` 均等价（api.ts 是公开入口别名）。
 *
 * 同时再导出 assertBaseUrlAllowed / ApiServiceBase / 常量，便于在测试或工具中复用。
 */

import { ApiServiceBase } from './_base'
import { searchMethods } from './search'
import { fetchMethods } from './fetch'
import { sourcesMethods } from './sources'
import { adminMethods } from './admin'
import { warpMethods } from './warp'
import { httpBackendMethods } from './http-backend'
import { sourceConfigMethods } from './source-config'
import { youtubeMethods } from './youtube'
import { waybackMethods } from './wayback'
import { proxyMethods } from './proxy'
import { bilibiliMethods } from './bilibili'
import { whoamiMethods } from './whoami'
import type {
  SearchResponse,
  WebSearchResponse,
  ImageSearchResponse,
  VideoSearchResponse,
  FetchResponse,
  LinkExtractionResult,
  SitemapResult,
  SourcesResponse,
  ConfigResponse,
  ReloadResponse,
  DoctorResponse,
  WarpStatus,
  WarpActionResult,
  HttpBackendResponse,
  SourceChannelConfig,
  YouTubeTrendingResponse,
  YouTubeVideoDetailResponse,
  YouTubeTranscriptResponse,
  WaybackCDXResponse,
  WaybackAvailabilityResponse,
  WaybackSaveResponse,
  BilibiliSearchResponse,
  BilibiliVideoDetailResponse,
  BilibiliUserSearchResponse,
  BilibiliArticleSearchResponse,
  WhoamiResponse,
} from '../types'

export class ApiService extends ApiServiceBase {}

/**
 * 通过同名 interface 声明合并，将各域 mixin 方法显式宣告为 ApiService 的成员方法。
 *
 * 之所以采用"集中、内联式"声明（而非 `extends SearchApi, FetchApi, ...`），
 * 是为了让最终的方法形态与原单一 class ApiService 完全一致 —— 这样
 * vitest 的 `vi.mocked()`（依赖 `MethodKeysOf<T>` 对方法签名进行识别）
 * 才能正确把这些方法包装成 `MockedFunction`，不会退化为只读函数属性。
 */
export interface ApiService {
  // === search ===
  searchPaper(q: string, sources: string, perPage: number, signal?: AbortSignal, timeout?: number): Promise<SearchResponse>
  searchPatent(q: string, sources: string, perPage: number, signal?: AbortSignal, timeout?: number): Promise<SearchResponse>
  searchWeb(q: string, engines: string, maxResults: number, signal?: AbortSignal, timeout?: number): Promise<WebSearchResponse>
  searchImages(q: string, maxResults?: number, region?: string, safesearch?: string, signal?: AbortSignal, timeout?: number): Promise<ImageSearchResponse>
  searchVideos(q: string, maxResults?: number, region?: string, safesearch?: string, signal?: AbortSignal, timeout?: number): Promise<VideoSearchResponse>

  // === fetch / links / sitemap ===
  fetch(
    urls: string[],
    provider?: string,
    timeout?: number,
    signal?: AbortSignal,
    options?: { selector?: string; startIndex?: number; maxLength?: number; respectRobotsTxt?: boolean },
  ): Promise<FetchResponse>
  extractLinks(url: string, baseUrl?: string, limit?: number, signal?: AbortSignal): Promise<LinkExtractionResult>
  parseSitemap(url: string, discover?: boolean, limit?: number, signal?: AbortSignal): Promise<SitemapResult>

  // === sources ===
  getSources(): Promise<SourcesResponse>

  // === admin ===
  getConfig(): Promise<ConfigResponse>
  reloadConfig(): Promise<ReloadResponse>
  getDoctor(): Promise<DoctorResponse>

  // === warp ===
  getWarpStatus(): Promise<WarpStatus>
  enableWarp(mode?: string, socksPort?: number, endpoint?: string): Promise<WarpActionResult>
  disableWarp(): Promise<WarpActionResult>

  // === http-backend ===
  getHttpBackend(): Promise<HttpBackendResponse>
  updateHttpBackend(params: {
    default?: string
    source?: string
    backend?: string
  }): Promise<{ status: string; default: string; overrides: Record<string, string> }>

  // === source-config ===
  getSourcesConfig(): Promise<Record<string, SourceChannelConfig>>
  updateSourceConfig(
    sourceName: string,
    params: { enabled?: boolean; proxy?: string; http_backend?: string; base_url?: string; api_key?: string },
  ): Promise<{ status: string; source: string }>

  // === proxy ===
  getProxyConfig(): Promise<{ proxy: string | null; proxy_pool: string[]; socks_supported: boolean }>
  updateProxyConfig(params: {
    proxy?: string | null
    proxy_pool?: string[]
  }): Promise<{ status: string; proxy: string | null; proxy_pool: string[] }>

  // === youtube ===
  getYouTubeTrending(region?: string, category?: string, maxResults?: number, signal?: AbortSignal, timeout?: number): Promise<YouTubeTrendingResponse>
  getYouTubeVideoDetail(videoId: string, signal?: AbortSignal, timeout?: number): Promise<YouTubeVideoDetailResponse>
  getYouTubeTranscript(videoId: string, lang?: string, signal?: AbortSignal, timeout?: number): Promise<YouTubeTranscriptResponse>

  // === wayback ===
  waybackCDX(
    url: string,
    options?: { from?: string; to?: string; limit?: number; filterStatus?: number; collapse?: string },
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<WaybackCDXResponse>
  waybackCheck(url: string, timestamp?: string, signal?: AbortSignal, timeout?: number): Promise<WaybackAvailabilityResponse>
  waybackSave(url: string, timeout?: number, signal?: AbortSignal): Promise<WaybackSaveResponse>

  // === bilibili ===
  searchBilibili(keyword: string, maxResults?: number, order?: string, signal?: AbortSignal, timeout?: number): Promise<BilibiliSearchResponse>
  getBilibiliVideoDetail(bvid: string, signal?: AbortSignal, timeout?: number): Promise<BilibiliVideoDetailResponse>
  searchBilibiliUsers(keyword: string, maxResults?: number, signal?: AbortSignal, timeout?: number): Promise<BilibiliUserSearchResponse>
  searchBilibiliArticles(keyword: string, maxResults?: number, signal?: AbortSignal, timeout?: number): Promise<BilibiliArticleSearchResponse>

  // === whoami ===
  whoami(): Promise<WhoamiResponse>
}

// 在原型上注入各域方法。顺序无关——各域方法名互不重叠。
Object.assign(
  ApiService.prototype,
  searchMethods,
  fetchMethods,
  sourcesMethods,
  adminMethods,
  warpMethods,
  httpBackendMethods,
  sourceConfigMethods,
  youtubeMethods,
  waybackMethods,
  proxyMethods,
  bilibiliMethods,
  whoamiMethods,
)

/**
 * API 服务单例
 */
export const api: ApiService = new ApiService()
export default api

export { ApiServiceBase, assertBaseUrlAllowed, REQUEST_TIMEOUT_MS, ALLOWED_API_HOSTS } from './_base'
