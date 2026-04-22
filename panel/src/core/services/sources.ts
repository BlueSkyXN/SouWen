/**
 * 文件用途：数据源列表 API（getSources）。
 */

import type { ApiServiceBase } from './_base'
import type { SourcesResponse } from '../types'

export interface SourcesApi {
  getSources(): Promise<SourcesResponse>
}

export const sourcesMethods = {
  /** 获取可用的数据源列表 */
  async getSources(this: ApiServiceBase): Promise<SourcesResponse> {
    return this.request<SourcesResponse>('/api/v1/sources', { headers: this.headers() })
  },
}
