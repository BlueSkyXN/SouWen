export const SOURCE_PROXY_MODES = ['inherit', 'none', 'warp', 'custom'] as const

export const SOURCE_CUSTOM_PROXY_EXAMPLE = 'socks5://127.0.0.1:1080'

export type SourceProxyMode = typeof SOURCE_PROXY_MODES[number]

export function getSourceProxyMode(value: string | null | undefined): SourceProxyMode {
  if (value === 'none' || value === 'warp' || value === 'custom') return value
  if (!value || value === 'inherit') return 'inherit'
  return 'custom'
}

export function getSourceCustomProxyValue(value: string | null | undefined): string {
  return getSourceProxyMode(value) === 'custom' && value !== 'custom' ? value ?? '' : ''
}

export function getSourceProxyValue(mode: SourceProxyMode, customProxy: string): string {
  return mode === 'custom' ? customProxy : mode
}
