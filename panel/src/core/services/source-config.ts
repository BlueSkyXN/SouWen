/**
 * 文件用途：数据源配置管理（getSourcesConfig / updateSourceConfig）。
 */

import type { ApiServiceBase } from './_base'
import type { SourceChannelConfig } from '../types'

export interface SourceConfigApi {
  getSourcesConfig(): Promise<Record<string, SourceChannelConfig>>
  updateSourceConfig(
    sourceName: string,
    params: { enabled?: boolean; proxy?: string; http_backend?: string; base_url?: string; api_key?: string },
  ): Promise<{ status: string; source: string }>
}

export const sourceConfigMethods = {
  /** 获取所有数据源的配置信息 */
  async getSourcesConfig(this: ApiServiceBase): Promise<Record<string, SourceChannelConfig>> {
    return this.request<Record<string, SourceChannelConfig>>('/api/v1/admin/sources/config', {
      headers: this.headers(),
    })
  },

  /** 更新指定数据源的配置 */
  async updateSourceConfig(
    this: ApiServiceBase,
    sourceName: string,
    params: { enabled?: boolean; proxy?: string; http_backend?: string; base_url?: string; api_key?: string },
  ): Promise<{ status: string; source: string }> {
    return this.request(`/api/v1/admin/sources/config/${encodeURIComponent(sourceName)}`, {
      method: 'PUT',
      headers: this.headers(),
      body: JSON.stringify(params),
    })
  },
}
