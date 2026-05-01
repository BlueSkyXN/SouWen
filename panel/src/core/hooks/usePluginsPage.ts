/**
 * 插件管理页面共享逻辑 Hook
 *
 * 抽取所有皮肤 PluginsPage 共用的状态管理与请求逻辑：
 *   - 列表加载（含 install_enabled、restart_required 元信息）
 *   - 启用/禁用单个插件
 *   - 健康检查（按需触发，结果缓存到 healthMap）
 *   - 安装/卸载（受 install_enabled 门控）
 *   - 重新扫描 entry-point 插件
 *
 * 设计要点：
 *   - 任何写操作完成后都会自动 `reload()`，保证 UI 与后端状态对齐
 *   - 错误会通过 notificationStore 弹 toast，不会中断后续操作
 *   - busy 字段记录"正在执行"的插件名，前端用来禁用对应行的按钮
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../services/api'
import { formatError } from '../lib/errors'
import { useNotificationStore } from '../stores/notificationStore'
import type {
  PluginInfo,
  PluginHealthResponse,
} from '../types'

/**
 * busy key 命名约定：
 *   - `enable:<name>` / `disable:<name>` / `health:<name>` — 单插件级
 *   - `install` / `uninstall` / `reload` / `list` — 全局级
 */
export type PluginBusyKey =
  | `enable:${string}`
  | `disable:${string}`
  | `health:${string}`
  | 'install'
  | 'uninstall'
  | 'reload'
  | 'list'

export interface UsePluginsPageState {
  plugins: PluginInfo[]
  loading: boolean
  error: string | null
  restartRequired: boolean
  installEnabled: boolean
  healthMap: Record<string, PluginHealthResponse>
  busy: Set<PluginBusyKey>
  refresh: () => Promise<void>
  enablePlugin: (name: string) => Promise<void>
  disablePlugin: (name: string) => Promise<void>
  checkHealth: (name: string) => Promise<void>
  installPackage: (packageName: string) => Promise<boolean>
  uninstallPackage: (packageName: string) => Promise<boolean>
  reloadPlugins: () => Promise<void>
}

export function usePluginsPage(): UsePluginsPageState {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)
  const [plugins, setPlugins] = useState<PluginInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [restartRequired, setRestartRequired] = useState(false)
  const [installEnabled, setInstallEnabled] = useState(false)
  const [healthMap, setHealthMap] = useState<Record<string, PluginHealthResponse>>({})
  const [busy, setBusy] = useState<Set<PluginBusyKey>>(new Set())
  const abortRef = useRef<AbortController | null>(null)

  const setBusyKey = useCallback((key: PluginBusyKey, on: boolean) => {
    setBusy((prev) => {
      const next = new Set(prev)
      if (on) next.add(key)
      else next.delete(key)
      return next
    })
  }, [])

  const refresh = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    setError(null)
    try {
      const res = await api.listPlugins(controller.signal)
      setPlugins(res.plugins)
      setRestartRequired(res.restart_required)
      setInstallEnabled(res.install_enabled)
    } catch (err) {
      if (controller.signal.aborted) return
      setError(formatError(err))
      addToast('error', t('plugins.toast.listFailed', { message: formatError(err) }))
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [addToast, t])

  useEffect(() => {
    void refresh()
    return () => {
      abortRef.current?.abort()
    }
  }, [refresh])

  const enablePlugin = useCallback(
    async (name: string) => {
      setBusyKey(`enable:${name}`, true)
      try {
        const res = await api.enablePlugin(name)
        if (res.success) {
          addToast('success', res.message || t('plugins.toast.enableSuccess', { name }))
        } else {
          addToast('error', res.message || t('plugins.toast.enableFailed', { name }))
        }
        await refresh()
      } catch (err) {
        addToast('error', t('plugins.toast.enableFailed', { name, message: formatError(err) }))
      } finally {
        setBusyKey(`enable:${name}`, false)
      }
    },
    [addToast, refresh, setBusyKey, t],
  )

  const disablePlugin = useCallback(
    async (name: string) => {
      setBusyKey(`disable:${name}`, true)
      try {
        const res = await api.disablePlugin(name)
        if (res.success) {
          addToast('success', res.message || t('plugins.toast.disableSuccess', { name }))
        } else {
          addToast('error', res.message || t('plugins.toast.disableFailed', { name }))
        }
        await refresh()
      } catch (err) {
        addToast('error', t('plugins.toast.disableFailed', { name, message: formatError(err) }))
      } finally {
        setBusyKey(`disable:${name}`, false)
      }
    },
    [addToast, refresh, setBusyKey, t],
  )

  const checkHealth = useCallback(
    async (name: string) => {
      setBusyKey(`health:${name}`, true)
      setHealthMap((prev) => {
        if (!(name in prev)) return prev
        const next = { ...prev }
        delete next[name]
        return next
      })
      try {
        const res = await api.getPluginHealth(name)
        setHealthMap((prev) => ({ ...prev, [name]: res }))
        const okStatuses = new Set(['ok', 'healthy'])
        if (!okStatuses.has(String(res.status).toLowerCase())) {
          addToast(
            'info',
            t('plugins.toast.healthDegraded', { name, status: String(res.status) }),
          )
        }
      } catch (err) {
        const message = formatError(err)
        setHealthMap((prev) => ({ ...prev, [name]: { status: 'error', message } }))
        addToast('error', t('plugins.toast.healthFailed', { name, message }))
      } finally {
        setBusyKey(`health:${name}`, false)
      }
    },
    [addToast, setBusyKey, t],
  )

  const installPackage = useCallback(
    async (packageName: string) => {
      const trimmed = packageName.trim()
      if (!trimmed) {
        addToast('error', t('plugins.toast.packageRequired'))
        return false
      }
      setBusyKey('install', true)
      try {
        const res = await api.installPlugin(trimmed)
        if (res.success) {
          addToast('success', t('plugins.toast.installSuccess', { package: trimmed }))
          await refresh()
          return true
        }
        addToast('error', res.message || t('plugins.toast.installFailed', { package: trimmed }))
        return false
      } catch (err) {
        addToast(
          'error',
          t('plugins.toast.installFailed', { package: trimmed, message: formatError(err) }),
        )
        return false
      } finally {
        setBusyKey('install', false)
      }
    },
    [addToast, refresh, setBusyKey, t],
  )

  const uninstallPackage = useCallback(
    async (packageName: string) => {
      const trimmed = packageName.trim()
      if (!trimmed) {
        addToast('error', t('plugins.toast.packageRequired'))
        return false
      }
      setBusyKey('uninstall', true)
      try {
        const res = await api.uninstallPlugin(trimmed)
        if (res.success) {
          addToast('success', t('plugins.toast.uninstallSuccess', { package: trimmed }))
          await refresh()
          return true
        }
        addToast(
          'error',
          res.message || t('plugins.toast.uninstallFailed', { package: trimmed }),
        )
        return false
      } catch (err) {
        addToast(
          'error',
          t('plugins.toast.uninstallFailed', { package: trimmed, message: formatError(err) }),
        )
        return false
      } finally {
        setBusyKey('uninstall', false)
      }
    },
    [addToast, refresh, setBusyKey, t],
  )

  const reloadPlugins = useCallback(async () => {
    setBusyKey('reload', true)
    try {
      const res = await api.reloadPlugins()
      addToast('success', res.message)
      if (res.errors.length > 0) {
        addToast(
          'error',
          t('plugins.toast.reloadPartialError', {
            count: res.errors.length,
            names: res.errors.map((e) => e.name).join(', '),
          }),
        )
      }
      await refresh()
    } catch (err) {
      addToast('error', t('plugins.toast.reloadFailed', { message: formatError(err) }))
    } finally {
      setBusyKey('reload', false)
    }
  }, [addToast, refresh, setBusyKey, t])

  return {
    plugins,
    loading,
    error,
    restartRequired,
    installEnabled,
    healthMap,
    busy,
    refresh,
    enablePlugin,
    disablePlugin,
    checkHealth,
    installPackage,
    uninstallPackage,
    reloadPlugins,
  }
}
