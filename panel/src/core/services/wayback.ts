/**
 * 文件用途：Wayback Machine 时光机 API（CDX 索引、可用性查询、保存快照）。
 */

import type { ApiServiceBase } from './_base'
import type {
  WaybackCDXResponse,
  WaybackAvailabilityResponse,
  WaybackSaveResponse,
} from '../types'

export interface WaybackApi {
  waybackCDX(
    url: string,
    options?: { from?: string; to?: string; limit?: number; filterStatus?: number; collapse?: string },
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<WaybackCDXResponse>
  waybackCheck(url: string, timestamp?: string, signal?: AbortSignal, timeout?: number): Promise<WaybackAvailabilityResponse>
  waybackSave(url: string, timeout?: number, signal?: AbortSignal): Promise<WaybackSaveResponse>
}

export const waybackMethods = {
  async waybackCDX(
    this: ApiServiceBase,
    url: string,
    options: { from?: string; to?: string; limit?: number; filterStatus?: number; collapse?: string } = {},
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<WaybackCDXResponse> {
    const params = new URLSearchParams({ url })
    if (options.from) params.set('from', options.from)
    if (options.to) params.set('to', options.to)
    if (options.limit) params.set('limit', String(options.limit))
    if (options.filterStatus) params.set('filter_status', String(options.filterStatus))
    if (options.collapse) params.set('collapse', options.collapse)
    if (timeout) params.set('timeout', String(timeout))
    return this.request<WaybackCDXResponse>(`/api/v1/wayback/cdx?${params}`, {
      headers: this.headers(),
      signal,
    })
  },

  async waybackCheck(
    this: ApiServiceBase,
    url: string,
    timestamp?: string,
    signal?: AbortSignal,
    timeout?: number,
  ): Promise<WaybackAvailabilityResponse> {
    const params = new URLSearchParams({ url })
    if (timestamp) params.set('timestamp', timestamp)
    if (timeout) params.set('timeout', String(timeout))
    return this.request<WaybackAvailabilityResponse>(`/api/v1/wayback/check?${params}`, {
      headers: this.headers(),
      signal,
    })
  },

  async waybackSave(
    this: ApiServiceBase,
    url: string,
    timeout = 60,
    signal?: AbortSignal,
  ): Promise<WaybackSaveResponse> {
    return this.request<WaybackSaveResponse>('/api/v1/wayback/save', {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify({ url, timeout }),
      signal,
      timeoutMs: timeout * 1000 + 20_000,
    })
  },
}
