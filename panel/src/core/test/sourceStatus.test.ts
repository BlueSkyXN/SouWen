import { describe, expect, it } from 'vitest'

import { doctorStatusLabel, doctorStatusTone, sourceCredentialLabel } from '../lib/sourceStatus'

describe('doctorStatusTone', () => {
  it('maps disabled to muted instead of warning', () => {
    expect(doctorStatusTone('disabled')).toBe('muted')
    expect(doctorStatusTone('missing_key')).toBe('warn')
  })
})

describe('doctorStatusLabel', () => {
  it('uses source labels for unavailable and disabled statuses', () => {
    const t = ((key: string, fallback?: string) => `${key}:${fallback ?? ''}`) as never

    expect(doctorStatusLabel('unavailable', t)).toBe('sources.unavailable:Unavailable')
    expect(doctorStatusLabel('disabled', t)).toBe('sources.disabled:Disabled')
  })
})

describe('sourceCredentialLabel', () => {
  it('prefers credential_fields over legacy required_key', () => {
    expect(sourceCredentialLabel({ credential_fields: ['client_id', 'client_secret'], required_key: 'api_key' })).toBe('client_id, client_secret')
  })
})
