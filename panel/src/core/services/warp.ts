/**
 * 文件用途：Cloudflare Warp 代理控制（getWarpStatus / enableWarp / disableWarp）。
 */

import type { ApiServiceBase } from './_base'
import type { WarpStatus, WarpActionResult } from '../types'

export interface WarpApi {
  getWarpStatus(): Promise<WarpStatus>
  enableWarp(mode?: string, socksPort?: number, endpoint?: string): Promise<WarpActionResult>
  disableWarp(): Promise<WarpActionResult>
}

export const warpMethods = {
  /** 获取 Warp 代理状态 */
  async getWarpStatus(this: ApiServiceBase): Promise<WarpStatus> {
    return this.request<WarpStatus>('/api/v1/admin/warp', { headers: this.headers() })
  },

  /** 启用 Warp 代理 */
  async enableWarp(this: ApiServiceBase, mode = 'auto', socksPort = 1080, endpoint?: string): Promise<WarpActionResult> {
    const params = new URLSearchParams({ mode, socks_port: String(socksPort) })
    if (endpoint) params.set('endpoint', endpoint)
    return this.request<WarpActionResult>(`/api/v1/admin/warp/enable?${params}`, {
      method: 'POST',
      headers: this.headers(),
    })
  },

  /** 禁用 Warp 代理 */
  async disableWarp(this: ApiServiceBase): Promise<WarpActionResult> {
    return this.request<WarpActionResult>('/api/v1/admin/warp/disable', {
      method: 'POST',
      headers: this.headers(),
    })
  },
}
