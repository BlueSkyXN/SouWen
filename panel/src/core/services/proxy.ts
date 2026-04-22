/**
 * 文件用途：全局代理配置 API（getProxyConfig / updateProxyConfig）。
 */

import type { ApiServiceBase } from './_base'

export interface ProxyConfig {
  proxy: string | null
  proxy_pool: string[]
  socks_supported: boolean
}

export interface ProxyApi {
  getProxyConfig(): Promise<ProxyConfig>
  updateProxyConfig(params: {
    proxy?: string | null
    proxy_pool?: string[]
  }): Promise<{ status: string; proxy: string | null; proxy_pool: string[] }>
}

export const proxyMethods = {
  /** 获取全局代理配置 */
  async getProxyConfig(this: ApiServiceBase): Promise<ProxyConfig> {
    return this.request('/api/v1/admin/proxy', { headers: this.headers() })
  },

  /** 更新全局代理配置 */
  async updateProxyConfig(
    this: ApiServiceBase,
    params: { proxy?: string | null; proxy_pool?: string[] },
  ): Promise<{ status: string; proxy: string | null; proxy_pool: string[] }> {
    return this.request('/api/v1/admin/proxy', {
      method: 'PUT',
      headers: this.headers(),
      body: JSON.stringify(params),
    })
  },
}
