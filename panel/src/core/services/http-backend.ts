/**
 * 文件用途：HTTP 后端配置管理（getHttpBackend / updateHttpBackend）。
 */

import type { ApiServiceBase } from './_base'
import type { HttpBackendResponse } from '../types'

export interface HttpBackendApi {
  getHttpBackend(): Promise<HttpBackendResponse>
  updateHttpBackend(params: {
    default?: string
    source?: string
    backend?: string
  }): Promise<{ status: string; default: string; overrides: Record<string, string> }>
}

export const httpBackendMethods = {
  /** 获取 HTTP 后端配置（代理、curl-cffi 等） */
  async getHttpBackend(this: ApiServiceBase): Promise<HttpBackendResponse> {
    return this.request<HttpBackendResponse>('/api/v1/admin/http-backend', {
      headers: this.headers(),
    })
  },

  /** 更新 HTTP 后端配置 */
  async updateHttpBackend(
    this: ApiServiceBase,
    params: { default?: string; source?: string; backend?: string },
  ): Promise<{ status: string; default: string; overrides: Record<string, string> }> {
    const searchParams = new URLSearchParams()
    if (params.default) searchParams.set('default', params.default)
    if (params.source) searchParams.set('source', params.source)
    if (params.backend) searchParams.set('backend', params.backend)
    return this.request(`/api/v1/admin/http-backend?${searchParams}`, {
      method: 'PUT',
      headers: this.headers(),
    })
  },
}
