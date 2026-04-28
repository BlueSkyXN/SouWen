/**
 * 文件用途：Cloudflare Warp 代理控制（getWarpStatus / enableWarp / disableWarp）。
 */

import type { ApiServiceBase } from './_base'
import type { WarpStatus, WarpActionResult, WarpModesResponse, WarpTestResult, WarpConfigResponse, WarpComponentsResponse, WarpInstallResult } from '../types'

export interface WarpApi {
  getWarpStatus(): Promise<WarpStatus>
  enableWarp(mode?: string, socksPort?: number, endpoint?: string, httpPort?: number): Promise<WarpActionResult>
  disableWarp(): Promise<WarpActionResult>
  getWarpModes(): Promise<WarpModesResponse>
  registerWarp(backend?: string): Promise<WarpActionResult>
  testWarp(): Promise<WarpTestResult>
  getWarpConfig(): Promise<WarpConfigResponse>
  getWarpComponents(): Promise<WarpComponentsResponse>
  installWarpComponent(component: string, version?: string): Promise<WarpInstallResult>
  uninstallWarpComponent(component: string): Promise<WarpActionResult>
  switchWarpMode(mode: string, socksPort?: number, endpoint?: string, httpPort?: number): Promise<WarpActionResult>
}

export const warpMethods = {
  /** 获取 Warp 代理状态 */
  async getWarpStatus(this: ApiServiceBase): Promise<WarpStatus> {
    return this.request<WarpStatus>('/api/v1/admin/warp', { headers: this.headers() })
  },

  /** 启用 Warp 代理 */
  async enableWarp(this: ApiServiceBase, mode = 'auto', socksPort = 1080, endpoint?: string, httpPort?: number): Promise<WarpActionResult> {
    const params = new URLSearchParams({ mode, socks_port: String(socksPort) })
    if (endpoint) params.set('endpoint', endpoint)
    if (httpPort !== undefined) params.set('http_port', String(httpPort))
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

  /** 获取所有 WARP 模式信息 */
  async getWarpModes(this: ApiServiceBase): Promise<WarpModesResponse> {
    return this.request<WarpModesResponse>('/api/v1/admin/warp/modes', { headers: this.headers() })
  },

  /** 注册 WARP 账号 */
  async registerWarp(this: ApiServiceBase, backend: string = 'wgcf'): Promise<WarpActionResult> {
    const params = new URLSearchParams({ backend })
    return this.request<WarpActionResult>(`/api/v1/admin/warp/register?${params}`, {
      method: 'POST',
      headers: this.headers(),
    })
  },

  /** 测试 WARP 连接 */
  async testWarp(this: ApiServiceBase): Promise<WarpTestResult> {
    return this.request<WarpTestResult>('/api/v1/admin/warp/test', {
      method: 'POST',
      headers: this.headers(),
    })
  },

  /** 获取 WARP 配置 */
  async getWarpConfig(this: ApiServiceBase): Promise<WarpConfigResponse> {
    return this.request<WarpConfigResponse>('/api/v1/admin/warp/config', { headers: this.headers() })
  },

  /** 获取 WARP 组件安装状态 */
  async getWarpComponents(this: ApiServiceBase): Promise<WarpComponentsResponse> {
    return this.request<WarpComponentsResponse>('/api/v1/admin/warp/components', { headers: this.headers() })
  },

  /** 安装 WARP 组件 */
  async installWarpComponent(this: ApiServiceBase, component: string, version?: string): Promise<WarpInstallResult> {
    const params = new URLSearchParams({ component })
    if (version) params.set('version', version)
    return this.request<WarpInstallResult>(`/api/v1/admin/warp/components/install?${params}`, {
      method: 'POST',
      headers: this.headers(),
    })
  },

  /** 卸载 WARP 组件 */
  async uninstallWarpComponent(this: ApiServiceBase, component: string): Promise<WarpActionResult> {
    const params = new URLSearchParams({ component })
    return this.request<WarpActionResult>(`/api/v1/admin/warp/components/uninstall?${params}`, {
      method: 'POST',
      headers: this.headers(),
    })
  },

  /** 切换 WARP 模式 */
  async switchWarpMode(this: ApiServiceBase, mode: string, socksPort = 1080, endpoint?: string, httpPort?: number): Promise<WarpActionResult> {
    const params = new URLSearchParams({ mode, socks_port: String(socksPort) })
    if (endpoint) params.set('endpoint', endpoint)
    if (httpPort !== undefined) params.set('http_port', String(httpPort))
    return this.request<WarpActionResult>(`/api/v1/admin/warp/switch?${params}`, {
      method: 'POST',
      headers: this.headers(),
    })
  },
}
