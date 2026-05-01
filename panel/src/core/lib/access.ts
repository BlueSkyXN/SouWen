/**
 * 文件用途：前端路由与导航的角色功能访问判断。
 */

import type { UserRole } from '../types'

type Features = Record<string, boolean | string>

const ADMIN_FEATURES = new Set([
  'fetch',
  'wayback_save',
  'config_write',
  'sources_config_write',
  'proxy_admin',
  'warp_admin',
  'doctor_full',
])

const NAV_FEATURES: Record<string, string | undefined> = {
  '/': 'doctor_full',
  '/fetch': 'fetch',
  '/sources': 'doctor_full',
  '/network': 'proxy_admin',
  '/warp': 'warp_admin',
  '/config': 'config_write',
  '/plugins': 'config_write',
}

const ROUTE_FEATURES: Array<{ prefix: string; feature: string }> = [
  { prefix: '/', feature: 'doctor_full' },
  { prefix: '/fetch', feature: 'fetch' },
  { prefix: '/sources', feature: 'doctor_full' },
  { prefix: '/network', feature: 'proxy_admin' },
  { prefix: '/warp', feature: 'warp_admin' },
  { prefix: '/config', feature: 'config_write' },
  { prefix: '/plugins', feature: 'config_write' },
]

export function hasFeatureAccess(features: Features, role: UserRole, feature: string): boolean {
  const value = features[feature]
  if (typeof value === 'boolean') return value
  if (typeof value === 'string') return value.length > 0 && value !== 'false'
  return role === 'admin' && ADMIN_FEATURES.has(feature)
}

export function canAccessNavItem(path: string, features: Features, role: UserRole): boolean {
  const feature = NAV_FEATURES[path]
  if (!feature) return true
  return hasFeatureAccess(features, role, feature)
}

export function canAccessPath(path: string, features: Features, role: UserRole): boolean {
  if (path === '/') return hasFeatureAccess(features, role, 'doctor_full')
  const rule = ROUTE_FEATURES.find((entry) => path === entry.prefix || path.startsWith(`${entry.prefix}/`))
  if (!rule) return true
  return hasFeatureAccess(features, role, rule.feature)
}
