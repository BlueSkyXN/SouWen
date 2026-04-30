/**
 * 文件用途：前端角色功能访问判断单元测试。
 */

import { describe, expect, it } from 'vitest'
import { canAccessNavItem, canAccessPath, hasFeatureAccess } from '../lib/access'

describe('access helpers', () => {
  it('allows public navigation items without feature flags', () => {
    expect(canAccessNavItem('/search', {}, 'user')).toBe(true)
    expect(canAccessPath('/tools', {}, 'guest')).toBe(true)
  })

  it('hides admin navigation when whoami features deny access', () => {
    const features = {
      fetch: false,
      config_write: false,
      proxy_admin: false,
      warp_admin: false,
      doctor_full: false,
    }
    expect(canAccessNavItem('/fetch', features, 'user')).toBe(false)
    expect(canAccessNavItem('/config', features, 'user')).toBe(false)
    expect(canAccessNavItem('/', features, 'user')).toBe(false)
    expect(canAccessPath('/', features, 'user')).toBe(false)
    expect(canAccessPath('/network', features, 'user')).toBe(false)
    expect(canAccessPath('/sources', features, 'user')).toBe(false)
  })

  it('allows admin navigation from explicit features or restored admin role fallback', () => {
    expect(canAccessNavItem('/fetch', { fetch: true }, 'user')).toBe(true)
    expect(canAccessPath('/config', {}, 'admin')).toBe(true)
    expect(canAccessPath('/', {}, 'admin')).toBe(true)
    expect(hasFeatureAccess({ wayback_save: true }, 'user', 'wayback_save')).toBe(true)
  })
})
