import { describe, expect, it, vi } from 'vitest'

import {
  doctorStatusLabel,
  doctorStatusTone,
  sourceAvailabilityBadgeColor,
  sourceAvailabilityLabel,
  sourceAvailabilityMessage,
  sourceAvailabilityStatus,
  sourceAvailabilityTone,
  sourceCredentialLabel,
} from '../lib/sourceStatus'

describe('doctorStatusTone', () => {
  it('maps disabled to muted instead of warning', () => {
    expect(doctorStatusTone('disabled')).toBe('muted')
    expect(doctorStatusTone('missing_key')).toBe('warn')
  })
})

describe('doctorStatusLabel', () => {
  it('uses source labels for unavailable and disabled statuses', () => {
    const t = vi.fn((key: string) => key) as never

    expect(doctorStatusLabel('unavailable', t)).toBe('sources.unavailable')
    expect(doctorStatusLabel('disabled', t)).toBe('sources.disabled')
    expect(t).toHaveBeenCalledWith('sources.unavailable')
    expect(t).toHaveBeenCalledWith('sources.disabled')
  })
})

describe('sourceCredentialLabel', () => {
  it('prefers credential_fields over legacy required_key', () => {
    expect(sourceCredentialLabel({ credential_fields: ['client_id', 'client_secret'], required_key: 'api_key' })).toBe('client_id, client_secret')
  })
})

describe('sourceAvailabilityStatus', () => {
  const t = vi.fn((key: string) => {
    if (key === 'sources.available') return '可用'
    if (key === 'sources.missingRuntime') return '缺依赖'
    if (key === 'sources.needsCredentials') return '缺凭据'
    if (key === 'sources.disabled') return '已禁用'
    if (key === 'sources.unavailable') return '不可用'
    return key
  }) as never

  it('marks statically unavailable catalog entries as unavailable', () => {
    const source = {
      enabled: true,
      status: 'unavailable',
      available: false,
      message: 'generic unavailable',
    }

    expect(sourceAvailabilityStatus(source)).toBe('unavailable')
    expect(sourceAvailabilityTone(source)).toBe('error')
    expect(sourceAvailabilityLabel(source, t)).toBe('不可用')
    expect(sourceAvailabilityMessage(source, t)).toBe('generic unavailable')
    expect(sourceAvailabilityBadgeColor(sourceAvailabilityTone(source))).toBe('red')
  })

  it('keeps manually disabled sources distinct from availability failures', () => {
    expect(sourceAvailabilityStatus({
      enabled: false,
    })).toBe('disabled')
  })

  it('maps missing credentials to a credential status', () => {
    expect(sourceAvailabilityStatus({
      enabled: true,
      status: 'missing_key',
      credentials_satisfied: false,
    })).toBe('credentials')
  })

  it('distinguishes a missing runtime from credentials and generic unavailability', () => {
    const source = {
      enabled: true,
      runtime_available: false,
      runtime_reason: 'site_crawler: missing modules: site_crawler',
      credentials_satisfied: false,
      status: 'unavailable',
      available: false,
    }

    expect(sourceAvailabilityStatus(source)).toBe('runtime')
    expect(sourceAvailabilityLabel(source, t)).toBe('缺依赖')
    expect(sourceAvailabilityMessage(source, t)).toBe('site_crawler: missing modules: site_crawler')
  })

  it('does not let catalog availability override an explicit doctor failure', () => {
    expect(sourceAvailabilityStatus({
      enabled: true,
      runtime_available: true,
      credentials_satisfied: true,
      status: 'unavailable',
      available: true,
    })).toBe('unavailable')
  })
})
