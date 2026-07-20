import type { WarpModeInfo, WarpStatus } from '../types'

export const WARP_MODE_OPTIONS = [
  {
    value: 'auto',
    labelKey: 'warp.modeLabels.auto',
    descriptionKey: 'warp.modeDescriptions.auto',
  },
  {
    value: 'wireproxy',
    labelKey: 'warp.modeLabels.wireproxy',
    descriptionKey: 'warp.modeDescriptions.wireproxy',
  },
  {
    value: 'kernel',
    labelKey: 'warp.modeLabels.kernel',
    descriptionKey: 'warp.modeDescriptions.kernel',
  },
  {
    value: 'usque',
    labelKey: 'warp.modeLabels.usque',
    descriptionKey: 'warp.modeDescriptions.usque',
  },
  {
    value: 'warp-cli',
    labelKey: 'warp.modeLabels.warpCli',
    descriptionKey: 'warp.modeDescriptions.warpCli',
  },
  {
    value: 'external',
    labelKey: 'warp.modeLabels.external',
    descriptionKey: 'warp.modeDescriptions.external',
  },
] as const

export type WarpModeValue = typeof WARP_MODE_OPTIONS[number]['value']
export type ConcreteWarpModeValue = Exclude<WarpModeValue, 'auto'>
export type WarpModeOption = typeof WARP_MODE_OPTIONS[number]
export type WarpModeTranslator = (key: string) => string

const WARP_MODE_DETAILS: Record<
  ConcreteWarpModeValue,
  Pick<WarpModeInfo, 'id' | 'protocol' | 'requires_privilege' | 'docker_only' | 'proxy_types'>
> = {
  wireproxy: {
    id: 'wireproxy',
    protocol: 'wireguard',
    requires_privilege: false,
    docker_only: false,
    proxy_types: ['socks5', 'http'],
  },
  kernel: {
    id: 'kernel',
    protocol: 'wireguard',
    requires_privilege: true,
    docker_only: false,
    proxy_types: ['socks5', 'http'],
  },
  usque: {
    id: 'usque',
    protocol: 'masque',
    requires_privilege: false,
    docker_only: false,
    proxy_types: ['socks5', 'http'],
  },
  'warp-cli': {
    id: 'warp-cli',
    protocol: 'warp-cli',
    requires_privilege: true,
    docker_only: false,
    proxy_types: ['socks5', 'http'],
  },
  external: {
    id: 'external',
    protocol: 'external',
    requires_privilege: false,
    docker_only: true,
    proxy_types: ['socks5', 'http'],
  },
}

function isConcreteWarpMode(value: string): value is ConcreteWarpModeValue {
  return value in WARP_MODE_DETAILS
}

function findWarpModeOption(value: string): WarpModeOption | undefined {
  return WARP_MODE_OPTIONS.find((option) => option.value === value)
}

export function isWarpModeAvailable(warp: WarpStatus, mode: WarpModeValue): boolean {
  if (mode === 'auto') return true
  return Boolean(warp.available_modes?.[mode as ConcreteWarpModeValue])
}

export function isWarpModeInfoAvailable(
  mode: Pick<WarpModeInfo, 'id' | 'installed' | 'configured' | 'edition_available'>,
): boolean {
  const editionAvailable = mode.edition_available ?? true
  return editionAvailable && mode.installed && (mode.id !== 'external' || Boolean(mode.configured))
}

export function getAvailableWarpModeOptions(warp: WarpStatus): WarpModeOption[] {
  return WARP_MODE_OPTIONS.filter(
    (option) => option.value !== 'auto' && isWarpModeAvailable(warp, option.value),
  )
}

export function getWarpModeLabel(mode: string | undefined, translate: WarpModeTranslator): string {
  if (!mode) return ''
  const option = findWarpModeOption(mode)
  return option ? translate(option.labelKey) : mode
}

export function getWarpModeDescription(mode: string | undefined, translate: WarpModeTranslator): string {
  if (!mode) return ''
  const option = findWarpModeOption(mode)
  return option ? translate(option.descriptionKey) : ''
}

export function createFallbackWarpMode(
  mode: ConcreteWarpModeValue,
  warp: WarpStatus | null,
  translate: WarpModeTranslator,
): WarpModeInfo {
  const statusModes = warp?.available_modes as Record<string, boolean> | undefined
  const installed = Boolean(statusModes?.[mode])
  return {
    ...WARP_MODE_DETAILS[mode],
    name: getWarpModeLabel(mode, translate),
    installed,
    configured: mode === 'external' ? installed : undefined,
    description: getWarpModeDescription(mode, translate),
  }
}

export function getDisplayWarpModes(
  modes: WarpModeInfo[],
  warp: WarpStatus | null,
  translate: WarpModeTranslator,
): WarpModeInfo[] {
  const modeMap = new Map(modes.map((item) => [item.id, item]))
  return WARP_MODE_OPTIONS
    .filter((option): option is Extract<WarpModeOption, { value: ConcreteWarpModeValue }> =>
      isConcreteWarpMode(option.value),
    )
    .map((option) => {
      const existing = modeMap.get(option.value)
      if (!existing) return createFallbackWarpMode(option.value, warp, translate)
      return {
        ...existing,
        name: getWarpModeLabel(existing.id, translate),
        description: getWarpModeDescription(existing.id, translate) || existing.description,
      }
    })
}
