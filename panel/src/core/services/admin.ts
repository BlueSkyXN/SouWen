/**
 * 文件用途：管理端 API — 配置读取/重载、诊断（getConfig / reloadConfig / getDoctor）。
 * 新增：getConfigYaml / saveConfigYaml 用于在线 YAML 配置文件编辑。
 */

import type { ApiServiceBase } from './_base'
import type { ConfigResponse, ReloadResponse, DoctorResponse, YamlConfigResponse } from '../types'

export interface AdminApi {
  getConfig(): Promise<ConfigResponse>
  reloadConfig(): Promise<ReloadResponse>
  getDoctor(): Promise<DoctorResponse>
  getConfigYaml(): Promise<YamlConfigResponse>
  saveConfigYaml(content: string): Promise<{ status: string; path: string; password_set: boolean }>
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

  /** 获取原始 YAML 配置文件内容 */
  async getConfigYaml(this: ApiServiceBase): Promise<YamlConfigResponse> {
    return this.request<YamlConfigResponse>('/api/v1/admin/config/yaml', { headers: this.headers() })
  },

  /** 保存 YAML 配置文件并重载（PUT） */
  async saveConfigYaml(
    this: ApiServiceBase,
    content: string,
  ): Promise<{ status: string; path: string; password_set: boolean }> {
    return this.request<{ status: string; path: string; password_set: boolean }>(
      '/api/v1/admin/config/yaml',
      {
        method: 'PUT',
        headers: { ...this.headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      },
    )
  },
}
