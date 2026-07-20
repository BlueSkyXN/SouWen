import { describe, expect, it } from 'vitest'
import {
  getAvailableWarpModeOptions,
  getDisplayWarpModes,
  getWarpModeLabel,
  isWarpModeAvailable,
  isWarpModeInfoAvailable,
} from '../lib/warpModes'
import type { WarpModeInfo, WarpStatus } from '../types'

function warpStatus(availableModes: WarpStatus['available_modes']): WarpStatus {
  return {
    status: 'disabled',
    mode: 'auto',
    owner: 'none',
    socks_port: 1080,
    http_port: 0,
    ip: '',
    pid: 0,
    interface: null,
    last_error: '',
    protocol: '',
    proxy_type: '',
    available_modes: availableModes,
  }
}

describe('warp mode helpers', () => {
  it('keeps auto available and filters concrete modes from backend capability flags', () => {
    const warp = warpStatus({
      wireproxy: true,
      kernel: false,
      usque: true,
      'warp-cli': false,
      external: false,
    })

    expect(isWarpModeAvailable(warp, 'auto')).toBe(true)
    expect(isWarpModeAvailable(warp, 'wireproxy')).toBe(true)
    expect(isWarpModeAvailable(warp, 'kernel')).toBe(false)
    expect(getAvailableWarpModeOptions(warp).map((option) => option.value)).toEqual([
      'wireproxy',
      'usque',
    ])
  })

  it('labels known modes through i18n keys and preserves unknown mode ids', () => {
    const translate = (key: string) => `translated:${key}`

    expect(getWarpModeLabel('wireproxy', translate)).toBe('translated:warp.modeLabels.wireproxy')
    expect(getWarpModeLabel('custom-mode', translate)).toBe('custom-mode')
  })

  it('builds translated display modes from backend data and shared fallbacks', () => {
    const warp = warpStatus({
      wireproxy: true,
      kernel: false,
      usque: true,
      'warp-cli': false,
      external: true,
    })
    const backendMode: WarpModeInfo = {
      id: 'wireproxy',
      name: 'raw backend name',
      protocol: 'wireguard',
      installed: true,
      requires_privilege: false,
      docker_only: false,
      proxy_types: ['socks5'],
      description: 'raw backend description',
      reason: 'backend reason',
    }
    const translate = (key: string) => `translated:${key}`

    const displayModes = getDisplayWarpModes([backendMode], warp, translate)

    expect(displayModes.map((mode) => mode.id)).toEqual([
      'wireproxy',
      'kernel',
      'usque',
      'warp-cli',
      'external',
    ])
    expect(displayModes[0]).toMatchObject({
      id: 'wireproxy',
      name: 'translated:warp.modeLabels.wireproxy',
      description: 'translated:warp.modeDescriptions.wireproxy',
      reason: 'backend reason',
    })
    expect(displayModes.find((mode) => mode.id === 'external')).toMatchObject({
      installed: true,
      configured: true,
    })
    expect(isWarpModeInfoAvailable(displayModes.find((mode) => mode.id === 'external')!)).toBe(true)
    expect(isWarpModeInfoAvailable(displayModes.find((mode) => mode.id === 'kernel')!)).toBe(false)
  })

  it('treats edition-blocked backend modes as unavailable', () => {
    const mode: WarpModeInfo = {
      id: 'usque',
      name: 'usque',
      protocol: 'masque',
      installed: true,
      requires_privilege: false,
      docker_only: false,
      proxy_types: ['socks5', 'http'],
      description: 'MASQUE',
      min_edition: 'pro',
      edition_available: false,
      edition_reason: "WARP mode 'usque' requires edition=pro, current edition=basic",
    }

    expect(isWarpModeInfoAvailable(mode)).toBe(false)
  })
})
