import type { TFunction } from 'i18next'

import type { DoctorSource, SourceInfo } from '../types'

const AVAILABLE_STATUSES = new Set(['ok', 'limited', 'warning', 'degraded'])
const WARNING_STATUSES = new Set(['limited', 'warning', 'degraded', 'missing_key', 'needs_key'])
const ERROR_STATUSES = new Set(['unavailable', 'error', 'timeout'])
const CREDENTIAL_STATUSES = new Set(['missing_key', 'needs_key'])

export type SourceAvailabilityKind =
  | 'available'
  | 'edition'
  | 'runtime'
  | 'credentials'
  | 'disabled'
  | 'unavailable'
export type SourceAvailabilityTone = 'ok' | 'warn' | 'error' | 'muted'

export type SourceAvailabilityInput =
  Partial<Pick<DoctorSource, 'enabled' | 'message' | 'runtime_available' | 'runtime_reason' | 'status'>>
  & Partial<Pick<SourceInfo, 'available' | 'credentials_satisfied' | 'edition_available' | 'edition_reason' | 'min_edition'>>

export interface SourceAvailabilitySummary {
  kind: SourceAvailabilityKind
  tone: SourceAvailabilityTone
  label: string
  message: string
}

export function isDoctorStatusAvailable(status?: string): boolean {
  return AVAILABLE_STATUSES.has(status ?? '')
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
    case 'ok': return t('status.ok')
    case 'limited': return t('status.limited')
    case 'warning': return t('status.warn')
    case 'degraded': return t('status.degraded')
    case 'missing_key':
    case 'needs_key': return t('dashboard.needsKey')
    case 'unavailable': return t('sources.unavailable')
    case 'disabled': return t('sources.disabled')
    case 'timeout': return t('status.timeout')
    default: return t('status.err')
  }
}

export function sourceAvailabilityStatus(source: SourceAvailabilityInput): SourceAvailabilityKind {
  if (source.enabled === false || source.status === 'disabled') return 'disabled'
  if (source.edition_available === false) return 'edition'
  if (source.runtime_available === false) return 'runtime'
  if (source.credentials_satisfied === false || CREDENTIAL_STATUSES.has(source.status ?? '')) {
    return 'credentials'
  }
  if (ERROR_STATUSES.has(source.status ?? '')) return 'unavailable'
  if (source.available === true || isDoctorStatusAvailable(source.status)) return 'available'
  return 'unavailable'
}

export function sourceAvailabilityTone(source: SourceAvailabilityInput): SourceAvailabilityTone {
  switch (sourceAvailabilityStatus(source)) {
    case 'available': return 'ok'
    case 'edition':
    case 'runtime':
    case 'credentials': return 'warn'
    case 'disabled': return 'muted'
    case 'unavailable': return 'error'
  }
}

export function sourceAvailabilityLabel(source: SourceAvailabilityInput, t: TFunction): string {
  switch (sourceAvailabilityStatus(source)) {
    case 'available': return t('sources.available')
    case 'edition': return t('sources.requiresUpgrade')
    case 'runtime': return t('sources.missingRuntime')
    case 'credentials': return t('sources.needsCredentials')
    case 'disabled': return t('sources.disabled')
    case 'unavailable': return t('sources.unavailable')
  }
}

export function sourceAvailabilityMessage(source: SourceAvailabilityInput, t: TFunction): string {
  const message = source.message?.trim()
  switch (sourceAvailabilityStatus(source)) {
    case 'edition':
      return t('sources.requiresUpgradeToEdition', { edition: source.min_edition ?? 'pro' })
    case 'runtime':
      return source.runtime_reason?.trim() || t('sources.missingRuntime')
    case 'credentials':
    case 'disabled':
    case 'unavailable':
    case 'available':
      return message || sourceAvailabilityLabel(source, t)
  }
}

export function sourceAvailabilitySummary(
  source: SourceAvailabilityInput,
  t: TFunction,
): SourceAvailabilitySummary {
  return {
    kind: sourceAvailabilityStatus(source),
    tone: sourceAvailabilityTone(source),
    label: sourceAvailabilityLabel(source, t),
    message: sourceAvailabilityMessage(source, t),
  }
}

export function sourceAvailabilityBadgeColor(
  tone: SourceAvailabilityTone,
): 'green' | 'amber' | 'red' | 'gray' {
  switch (tone) {
    case 'ok': return 'green'
    case 'warn': return 'amber'
    case 'error': return 'red'
    case 'muted': return 'gray'
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
