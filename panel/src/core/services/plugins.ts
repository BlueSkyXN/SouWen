/**
 * 文件用途：插件管理 API 客户端 — 列表、详情、健康检查、启用/禁用、安装/卸载、重载。
 *
 * 后端契约：参见 src/souwen/server/routes/admin/plugins.py 与
 * docs/plugin-management.md。所有端点都挂在 /api/v1/admin/plugins/* 下，
 * 复用 admin 鉴权（admin 密码或 admin token）。
 *
 * 设计要点：
 *   - install/uninstall 走允许列表 + SOUWEN_ENABLE_PLUGIN_INSTALL 双门禁；
 *     当后端未启用时会返回 success=false 与提示性 message，UI 直接展示。
 *   - getPluginHealth 直接透传后端 health_check 返回的 dict，因此 PluginHealthResponse
 *     只对 status 强类型，其他字段保留 [key: string]: unknown。
 *   - 列表端点的 install_enabled 字段供 UI 决定是否展示安装入口。
 */

import type { ApiServiceBase } from './_base'
import type {
  PluginListResponse,
  PluginInfo,
  PluginHealthResponse,
  PluginEnableResponse,
  PluginDisableResponse,
  PluginInstallResponse,
  PluginReloadResponse,
} from '../types'

export interface PluginsApi {
  listPlugins(signal?: AbortSignal): Promise<PluginListResponse>
  getPlugin(name: string, signal?: AbortSignal): Promise<PluginInfo>
  getPluginHealth(name: string, signal?: AbortSignal): Promise<PluginHealthResponse>
  enablePlugin(name: string): Promise<PluginEnableResponse>
  disablePlugin(name: string): Promise<PluginDisableResponse>
  installPlugin(packageName: string): Promise<PluginInstallResponse>
  uninstallPlugin(packageName: string): Promise<PluginInstallResponse>
  reloadPlugins(): Promise<PluginReloadResponse>
}

const PLUGIN_BASE = '/api/v1/admin/plugins'

export const pluginsMethods = {
  /** 列表所有插件 + 重启需求 + install 开关 */
  async listPlugins(this: ApiServiceBase, signal?: AbortSignal): Promise<PluginListResponse> {
    return this.request<PluginListResponse>(PLUGIN_BASE, {
      headers: this.headers(),
      signal,
    })
  },

  /** 查询单个插件的详细状态 */
  async getPlugin(this: ApiServiceBase, name: string, signal?: AbortSignal): Promise<PluginInfo> {
    return this.request<PluginInfo>(`${PLUGIN_BASE}/${encodeURIComponent(name)}`, {
      headers: this.headers(),
      signal,
    })
  },

  /** 调用 plugin.health_check 并返回结果（仅对已加载插件可用） */
  async getPluginHealth(
    this: ApiServiceBase,
    name: string,
    signal?: AbortSignal,
  ): Promise<PluginHealthResponse> {
    return this.request<PluginHealthResponse>(`${PLUGIN_BASE}/${encodeURIComponent(name)}/health`, {
      headers: this.headers(),
      signal,
    })
  },

  /** 启用插件（重启后生效） */
  async enablePlugin(this: ApiServiceBase, name: string): Promise<PluginEnableResponse> {
    return this.request<PluginEnableResponse>(
      `${PLUGIN_BASE}/${encodeURIComponent(name)}/enable`,
      {
        method: 'POST',
        headers: this.headers(),
      },
    )
  },

  /** 禁用插件：写入禁用列表 + 运行时尽力卸载 adapters / fetch handlers */
  async disablePlugin(this: ApiServiceBase, name: string): Promise<PluginDisableResponse> {
    return this.request<PluginDisableResponse>(
      `${PLUGIN_BASE}/${encodeURIComponent(name)}/disable`,
      {
        method: 'POST',
        headers: this.headers(),
      },
    )
  },

  /** 安装插件包（需 SOUWEN_ENABLE_PLUGIN_INSTALL=1，否则后端返回失败 + 提示） */
  async installPlugin(
    this: ApiServiceBase,
    packageName: string,
  ): Promise<PluginInstallResponse> {
    return this.request<PluginInstallResponse>(`${PLUGIN_BASE}/install`, {
      method: 'POST',
      headers: { ...this.headers(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ package: packageName }),
    })
  },

  /** 卸载插件包（同上，受 SOUWEN_ENABLE_PLUGIN_INSTALL 门控） */
  async uninstallPlugin(
    this: ApiServiceBase,
    packageName: string,
  ): Promise<PluginInstallResponse> {
    return this.request<PluginInstallResponse>(`${PLUGIN_BASE}/uninstall`, {
      method: 'POST',
      headers: { ...this.headers(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ package: packageName }),
    })
  },

  /** 追加扫描 entry-point 插件 */
  async reloadPlugins(this: ApiServiceBase): Promise<PluginReloadResponse> {
    return this.request<PluginReloadResponse>(`${PLUGIN_BASE}/reload`, {
      method: 'POST',
      headers: this.headers(),
    })
  },
}
