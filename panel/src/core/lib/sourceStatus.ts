import type { TFunction } from 'i18next'

import type { DoctorSource } from '../types'

const AVAILABLE_STATUSES = new Set(['ok', 'limited', 'warning', 'degraded'])
const WARNING_STATUSES = new Set(['limited', 'warning', 'degraded', 'missing_key', 'needs_key'])
const ERROR_STATUSES = new Set(['unavailable', 'error', 'timeout'])

export function isDoctorStatusAvailable(status?: string): boolean {
  return AVAILABLE_STATUSES.has(status ?? '')
}

export function doctorAvailableCount(sources: DoctorSource[], fallback?: number): number {
  if (typeof fallback === 'number') return fallback
  return sources.filter((source) => isDoctorStatusAvailable(source.status)).length
}

export function doctorStatusOrder(status?: string): number {
  switch (status) {
    case 'ok': return 0
    case 'limited': return 1
    case 'warning': return 2
    case 'degraded': return 2
    case 'missing_key':
    case 'needs_key': return 3
    case 'unavailable': return 4
    case 'disabled': return 5
    case 'error': return 6
    case 'timeout': return 7
    default: return 8
  }
}

export function doctorStatusTone(status?: string): 'ok' | 'warn' | 'error' | 'muted' {
  if (status === 'ok') return 'ok'
  if (WARNING_STATUSES.has(status ?? '')) return 'warn'
  if (status === 'disabled') return 'muted'
  if (ERROR_STATUSES.has(status ?? '')) return 'error'
  return 'error'
}

export function doctorStatusLabel(status: string | undefined, t: TFunction): string {
  switch (status) {
    case 'ok': return t('status.ok', 'OK')
    case 'limited': return t('status.limited', 'Limited')
    case 'warning': return t('status.warn', 'WARN')
    case 'degraded': return t('status.degraded', 'Degraded')
    case 'missing_key':
    case 'needs_key': return t('dashboard.needsKey', 'Needs Key')
    case 'unavailable': return t('sources.unavailable', 'Unavailable')
    case 'disabled': return t('sources.disabled', 'Disabled')
    case 'timeout': return t('status.timeout', 'TIMEOUT')
    default: return t('status.err', 'ERR')
  }
}

export function sourceCredentialLabel(
  source: Pick<DoctorSource, 'credential_fields' | 'required_key'>,
  separator = ', ',
): string {
  if (source.credential_fields && source.credential_fields.length > 0) {
    return source.credential_fields.join(separator)
  }
  return source.required_key ?? ''
}
