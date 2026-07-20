import { render, screen, waitFor } from '@testing-library/react'
import type { HTMLAttributes } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import type {
  WarpComponentInfo,
  WarpConfigResponse,
  WarpModeInfo,
  WarpStatus,
} from '@core/types'
import { WarpPage } from '../pages/WarpPage'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => {} },
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) => (typeof fallback === 'string' ? fallback : key),
  }),
}))

type MotionElementProps<T extends HTMLElement> = HTMLAttributes<T> & {
  animate?: unknown
  initial?: unknown
  transition?: unknown
  variants?: unknown
}

vi.mock('framer-motion', () => ({
  m: {
    div: ({
      children,
      animate: _animate,
      initial: _initial,
      transition: _transition,
      variants: _variants,
      ...props
    }: MotionElementProps<HTMLDivElement>) => <div {...props}>{children}</div>,
    header: ({
      children,
      animate: _animate,
      initial: _initial,
      transition: _transition,
      variants: _variants,
      ...props
    }: MotionElementProps<HTMLElement>) => <header {...props}>{children}</header>,
    section: ({
      children,
      animate: _animate,
      initial: _initial,
      transition: _transition,
      variants: _variants,
      ...props
    }: MotionElementProps<HTMLElement>) => <section {...props}>{children}</section>,
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
      usque: true,
      'warp-cli': false,
      external: false,
    },
  }
}

function warpModes(): WarpModeInfo[] {
  return [
    {
      id: 'wireproxy',
      name: 'wireproxy',
      protocol: 'wireguard',
      installed: true,
      configured: true,
      requires_privilege: false,
      docker_only: false,
      proxy_types: ['socks5', 'http'],
      description: 'wireproxy mode',
    },
    {
      id: 'usque',
      name: 'usque',
      protocol: 'masque',
      installed: true,
      configured: true,
      requires_privilege: false,
      docker_only: false,
      proxy_types: ['socks5', 'http'],
      description: 'usque mode',
    },
  ]
}

function warpConfig(): WarpConfigResponse {
  return {
    warp_enabled: false,
    warp_mode: 'wireproxy',
    warp_socks_port: 40000,
    warp_http_port: 0,
    warp_endpoint: 'engage.cloudflareclient.com:2408',
    warp_bind_address: '127.0.0.1',
    warp_startup_timeout: 30,
    warp_device_name: 'sou-wen-test',
    warp_usque_transport: 'auto',
    warp_external_proxy: null,
    warp_usque_path: null,
    warp_usque_config: null,
    warp_gost_args: null,
    has_license_key: false,
    has_team_token: false,
    has_proxy_auth: false,
  }
}

function warpComponents(): WarpComponentInfo[] {
  return [
    {
      name: 'wireproxy',
      installed: true,
      version: '1.0.0',
      path: '/tmp/wireproxy',
      system_path: null,
      source: 'runtime',
    },
  ]
}

describe('SouWen Google WarpPage accessibility', () => {
  beforeEach(() => {
    useNotificationStore.setState({ toasts: [] })

    vi.spyOn(api, 'getWarpStatus').mockResolvedValue(warpStatus())
    vi.spyOn(api, 'getWarpModes').mockResolvedValue({ modes: warpModes() })
    vi.spyOn(api, 'getWarpConfig').mockResolvedValue(warpConfig())
    vi.spyOn(api, 'getWarpComponents').mockResolvedValue({ components: warpComponents() })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    useNotificationStore.setState({ toasts: [] })
  })

  it('exposes WARP control inputs through accessible labels', async () => {
    render(<WarpPage />)

    expect(await screen.findByLabelText('warp.mode')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByLabelText('warp.socksPort')).toHaveValue(40000)
      expect(screen.getByLabelText('warp.httpPort')).toHaveValue(0)
      expect(screen.getByLabelText('warp.endpoint')).toHaveValue(
        'engage.cloudflareclient.com:2408',
      )
    })
  })
})
