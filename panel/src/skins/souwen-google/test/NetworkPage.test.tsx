import { render, screen } from '@testing-library/react'
import type { HTMLAttributes, ReactNode } from 'react'
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
  transition?: unknown
  variants?: unknown
}

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  m: {
    div: ({
      children,
      animate: _animate,
      initial: _initial,
      transition: _transition,
      variants: _variants,
      ...props
    }: MotionDivProps) => <div {...props}>{children}</div>,
    span: ({ children, ...props }: HTMLAttributes<HTMLSpanElement>) => (
      <span {...props}>{children}</span>
    ),
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
      wireproxy: true,
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

describe('SouWen Google NetworkPage accessibility', () => {
  beforeEach(() => {
    useNotificationStore.setState({ toasts: [] })

    vi.spyOn(api, 'getWarpStatus').mockResolvedValue(warpStatus())
    vi.spyOn(api, 'getHttpBackend').mockResolvedValue(httpBackend())
    vi.spyOn(api, 'getProxyConfig').mockResolvedValue({
      proxy: 'http://***@proxy.example:8080?apiKey=***&safe=1',
      proxy_pool: ['http://***@pool.example:8080?token=***&safe=1'],
      socks_supported: true,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    useNotificationStore.setState({ toasts: [] })
  })

  it('exposes network configuration controls through accessible labels', async () => {
    render(<NetworkPage />)

    expect(await screen.findByLabelText('warp.mode')).toBeInTheDocument()
    expect(screen.getByLabelText('warp.socksPort')).toBeInTheDocument()
    expect(screen.getByLabelText('warp.endpoint')).toBeInTheDocument()
    expect(await screen.findByLabelText('proxy.globalProxy')).toBeInTheDocument()
    expect(screen.getByLabelText('proxy.proxyPool')).toBeInTheDocument()
    expect(await screen.findByLabelText('httpBackend.globalDefault')).toBeInTheDocument()
    expect(screen.getByLabelText('duckduckgo')).toBeInTheDocument()
  })
})
