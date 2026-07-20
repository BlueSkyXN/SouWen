/**
 * 文件用途：Apple NetworkPage 全局代理配置交互回归测试。
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { HTMLAttributes } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import type { HttpBackendResponse, WarpStatus } from '@core/types'
import { NetworkPage } from '../pages/NetworkPage'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => {} },
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) => (typeof fallback === 'string' ? fallback : key),
  }),
}))

type MotionDivProps = HTMLAttributes<HTMLDivElement> & {
  animate?: unknown
  initial?: unknown
  variants?: unknown
}

vi.mock('framer-motion', () => ({
  m: {
    div: ({
      children,
      animate: _animate,
      initial: _initial,
      variants: _variants,
      ...props
    }: MotionDivProps) => <div {...props}>{children}</div>,
  },
}))

function warpStatus(): WarpStatus {
  return {
    status: 'disabled',
    mode: 'wireproxy',
    owner: 'none',
    socks_port: 40000,
    http_port: 0,
    ip: '',
    pid: 0,
    interface: null,
    last_error: '',
    protocol: 'socks5',
    proxy_type: 'socks5',
    available_modes: {
      wireproxy: false,
      kernel: false,
      usque: false,
      'warp-cli': false,
      external: false,
    },
  }
}

function httpBackend(): HttpBackendResponse {
  return {
    default: 'auto',
    overrides: {},
    curl_cffi_available: false,
  }
}

describe('Apple NetworkPage', () => {
  beforeEach(() => {
    useNotificationStore.setState({ toasts: [] })

    vi.spyOn(api, 'getWarpStatus').mockResolvedValue(warpStatus())
    vi.spyOn(api, 'getHttpBackend').mockResolvedValue(httpBackend())
    vi.spyOn(api, 'getProxyConfig').mockResolvedValue({
      proxy: 'http://***@proxy.example:8080?apiKey=***&safe=1',
      proxy_pool: ['http://***@pool.example:8080?token=***&safe=1'],
      socks_supported: true,
    })
    vi.spyOn(api, 'updateProxyConfig').mockResolvedValue({
      status: 'ok',
      proxy: 'http://***@proxy.example:8080?apiKey=***&safe=1',
      proxy_pool: ['http://***@pool.example:8080?token=***&safe=1'],
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    useNotificationStore.setState({ toasts: [] })
  })

  it('does not submit unchanged redacted proxy values', async () => {
    const user = userEvent.setup()

    render(<NetworkPage />)

    await screen.findByDisplayValue('http://***@proxy.example:8080?apiKey=***&safe=1')
    await screen.findByDisplayValue('http://***@pool.example:8080?token=***&safe=1')

    await user.click(screen.getByRole('button', { name: 'proxy.save' }))

    await waitFor(() => {
      expect(api.updateProxyConfig).toHaveBeenCalledWith({})
    })
    expect(api.updateProxyConfig).not.toHaveBeenCalledWith(
      expect.objectContaining({
        proxy: expect.stringContaining('***'),
      }),
    )
    expect(api.updateProxyConfig).not.toHaveBeenCalledWith(
      expect.objectContaining({
        proxy_pool: expect.arrayContaining([expect.stringContaining('***')]),
      }),
    )
  })

  it('exposes network configuration controls through accessible labels', async () => {
    render(<NetworkPage />)

    expect(await screen.findByLabelText('network.mode')).toBeInTheDocument()
    expect(screen.getByLabelText('network.port')).toBeInTheDocument()
    expect(screen.getByLabelText('network.endpoint')).toBeInTheDocument()
    expect(screen.getByLabelText('network.globalDefault')).toBeInTheDocument()
    expect(screen.getByLabelText('proxy.globalProxy')).toBeInTheDocument()
    expect(screen.getByLabelText('proxy.proxyPool')).toBeInTheDocument()
  })
})
