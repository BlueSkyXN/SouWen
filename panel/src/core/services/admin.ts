/**
 * 文件用途：管理端 API — 配置读取/重载、诊断（getConfig / reloadConfig / getDoctor）。
 */

import type { ApiServiceBase } from './_base'
import type { ConfigResponse, ReloadResponse, DoctorResponse } from '../types'

export interface AdminApi {
  getConfig(): Promise<ConfigResponse>
  reloadConfig(): Promise<ReloadResponse>
  getDoctor(): Promise<DoctorResponse>
}

export const adminMethods = {
  /** 获取系统配置 */
  async getConfig(this: ApiServiceBase): Promise<ConfigResponse> {
    return this.request<ConfigResponse>('/api/v1/admin/config', { headers: this.headers() })
  },

  /** 重载系统配置 */
  async reloadConfig(this: ApiServiceBase): Promise<ReloadResponse> {
    return this.request<ReloadResponse>('/api/v1/admin/config/reload', {
      method: 'POST',
      headers: this.headers(),
    })
  },

  /** 获取系统诊断信息（源可达性、配置状态等） */
  async getDoctor(this: ApiServiceBase): Promise<DoctorResponse> {
    return this.request<DoctorResponse>('/api/v1/admin/doctor', { headers: this.headers() })
  },
}
