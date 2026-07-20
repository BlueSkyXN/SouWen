import { describe, expect, it } from 'vitest'
import {
  SOURCE_CUSTOM_PROXY_EXAMPLE,
  getSourceCustomProxyValue,
  getSourceProxyMode,
  getSourceProxyValue,
} from '../lib/sourceProxyConfig'

describe('source proxy config helpers', () => {
  it('maps empty and keyword proxy values to UI modes', () => {
    expect(getSourceProxyMode(null)).toBe('inherit')
    expect(getSourceProxyMode('')).toBe('inherit')
    expect(getSourceProxyMode('inherit')).toBe('inherit')
    expect(getSourceProxyMode('none')).toBe('none')
    expect(getSourceProxyMode('warp')).toBe('warp')
  })

  it('treats proxy URLs and redacted display URLs as custom mode', () => {
    expect(getSourceProxyMode('socks5://127.0.0.1:1080')).toBe('custom')
    expect(getSourceProxyMode('http://user:***@proxy.example:8080')).toBe('custom')
  })

  it('keeps real custom proxy URLs but not the UI-only custom sentinel', () => {
    expect(getSourceCustomProxyValue('socks5://127.0.0.1:1080')).toBe(
      'socks5://127.0.0.1:1080',
    )
    expect(getSourceCustomProxyValue('custom')).toBe('')
    expect(getSourceCustomProxyValue('warp')).toBe('')
    expect(getSourceCustomProxyValue(null)).toBe('')
  })

  it('converts a UI mode back to the source config value', () => {
    expect(getSourceProxyValue('inherit', 'socks5://127.0.0.1:1080')).toBe('inherit')
    expect(getSourceProxyValue('custom', 'socks5://127.0.0.1:1080')).toBe(
      'socks5://127.0.0.1:1080',
    )
  })

  it('keeps the shared custom proxy example stable for UI placeholders', () => {
    expect(SOURCE_CUSTOM_PROXY_EXAMPLE).toBe('socks5://127.0.0.1:1080')
  })
})
