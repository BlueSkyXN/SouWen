import { describe, expect, it } from 'vitest'
import { isRedactedConfigValue, shouldSubmitConfigValue } from '../lib/redactedConfig'

describe('redacted config helpers', () => {
  it('detects display placeholders returned by config APIs', () => {
    expect(isRedactedConfigValue('http://user:***@proxy.local')).toBe(true)
    expect(isRedactedConfigValue('https://example.com?token=***')).toBe(true)
    expect(isRedactedConfigValue('https://example.com')).toBe(false)
    expect(isRedactedConfigValue(null)).toBe(false)
  })

  it('skips unchanged redacted display values', () => {
    const value = 'http://user:***@proxy.local'

    expect(shouldSubmitConfigValue(value, value)).toBe(false)
  })

  it('submits changed values and preserves existing non-redacted behavior', () => {
    expect(shouldSubmitConfigValue('inherit', 'http://user:***@proxy.local')).toBe(true)
    expect(shouldSubmitConfigValue('https://example.com', 'https://example.com')).toBe(true)
  })
})
