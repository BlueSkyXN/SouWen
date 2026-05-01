/**
 * 文件用途：usePluginsPage 插件管理状态回归测试。
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePluginsPage } from '../hooks/usePluginsPage'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'

describe('usePluginsPage', () => {
  beforeEach(() => {
    vi.spyOn(api, 'listPlugins').mockResolvedValue({
      plugins: [],
      restart_required: false,
      install_enabled: true,
    })
    useNotificationStore.setState({ toasts: [] })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    useNotificationStore.setState({ toasts: [] })
  })

  it('replaces stale healthy cache with error state when health check fails', async () => {
    let rejectSecondHealth!: (err: unknown) => void
    vi.spyOn(api, 'getPluginHealth')
      .mockResolvedValueOnce({ status: 'ok', latency_ms: 1 })
      .mockImplementationOnce(
        () =>
          new Promise<never>((_, reject) => {
            rejectSecondHealth = reject
          }),
      )

    const { result } = renderHook(() => usePluginsPage())
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.checkHealth('demo')
    })
    expect(result.current.healthMap.demo?.status).toBe('ok')

    let pending!: Promise<void>
    act(() => {
      pending = result.current.checkHealth('demo')
    })
    await waitFor(() => expect(result.current.healthMap.demo).toBeUndefined())

    await act(async () => {
      rejectSecondHealth(new Error('network down'))
      await pending
    })

    expect(result.current.healthMap.demo).toMatchObject({
      status: 'error',
      message: 'network down',
    })
  })
})
