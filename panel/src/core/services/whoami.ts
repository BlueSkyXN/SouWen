/**
 * 文件用途：/api/v1/whoami 端点调用
 *
 * 提供 whoami() 方法，用于获取当前 Token 对应的角色和可用功能列表。
 * 前端在登录后调用此接口，将角色信息缓存到 authStore。
 */

import type { ApiServiceBase } from './_base'
import type { WhoamiResponse } from '../types'

export const whoamiMethods = {
  /**
   * 获取当前角色和可用功能列表
   * 无需额外参数，自动使用 authStore 中的 token
   */
  async whoami(this: ApiServiceBase): Promise<WhoamiResponse> {
    return this.request<WhoamiResponse>('/api/v1/whoami', {
      headers: this.headers(),
    })
  },
}
