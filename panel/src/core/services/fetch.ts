/**
 * 文件用途：内容抓取与链接/Sitemap 提取（fetch / extractLinks / parseSitemap）。
 * 通过 mixin 注入到 ApiService 原型。
 */

import type { ApiServiceBase } from './_base'
import type { FetchResponse, LinkExtractionResult, SitemapResult } from '../types'

export interface FetchApi {
  fetch(
    urls: string[],
    provider?: string,
    timeout?: number,
    signal?: AbortSignal,
    options?: { selector?: string; startIndex?: number; maxLength?: number; respectRobotsTxt?: boolean },
  ): Promise<FetchResponse>
  extractLinks(url: string, baseUrl?: string, limit?: number, signal?: AbortSignal): Promise<LinkExtractionResult>
  parseSitemap(url: string, discover?: boolean, limit?: number, signal?: AbortSignal): Promise<SitemapResult>
}

export const fetchMethods = {
  /**
   * 抓取网页内容
   * 支持 16 个提供者：builtin / jina_reader / tavily / firecrawl / exa /
   * crawl4ai / scrapfly / diffbot / scrapingbee / zenrows /
   * scraperapi / apify / cloudflare / wayback / newspaper / readability
   */
  async fetch(
    this: ApiServiceBase,
    urls: string[],
    provider = 'builtin',
    timeout = 30,
    signal?: AbortSignal,
    options?: { selector?: string; startIndex?: number; maxLength?: number; respectRobotsTxt?: boolean },
  ): Promise<FetchResponse> {
    // 客户端超时 = 后端 timeout + 20s 缓冲（覆盖后端 +15s 缓冲及网络开销）
    const clientTimeoutMs = timeout * 1000 + 20_000
    const body: Record<string, unknown> = { urls, provider, timeout }
    if (options?.selector) body.selector = options.selector
    if (options?.startIndex) body.start_index = options.startIndex
    if (options?.maxLength) body.max_length = options.maxLength
    if (options?.respectRobotsTxt) body.respect_robots_txt = options.respectRobotsTxt
    return this.request<FetchResponse>('/api/v1/fetch', {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify(body),
      signal,
      timeoutMs: clientTimeoutMs,
    })
  },

  /** 提取页面链接 */
  async extractLinks(this: ApiServiceBase, url: string, baseUrl?: string, limit = 100, signal?: AbortSignal): Promise<LinkExtractionResult> {
    let endpoint = `/api/v1/links?url=${encodeURIComponent(url)}&limit=${limit}`
    if (baseUrl) endpoint += `&base_url=${encodeURIComponent(baseUrl)}`
    return this.request<LinkExtractionResult>(endpoint, { headers: this.headers(), signal })
  },

  /** 解析 sitemap.xml */
  async parseSitemap(this: ApiServiceBase, url: string, discover = false, limit = 1000, signal?: AbortSignal): Promise<SitemapResult> {
    return this.request<SitemapResult>(
      `/api/v1/sitemap?url=${encodeURIComponent(url)}&discover=${discover}&limit=${limit}`,
      { headers: this.headers(), signal },
    )
  },
}
