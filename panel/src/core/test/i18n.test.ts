/**
 * 文件用途：i18n 静态 key 覆盖回归测试。
 */

import { describe, expect, it } from 'vitest'
import { SEARCH_CAPABILITIES, SEARCH_DOMAINS } from '../hooks/useSearchPage'
import { BILIBILI_ORDERS, CATEGORIES } from '../hooks/useVideoPage'
import zhCN from '../i18n/zh-CN.json'
import { SOURCE_PROXY_MODES } from '../lib/sourceProxyConfig'
import { WARP_MODE_OPTIONS } from '../lib/warpModes'
import {
  PLUGIN_SOURCES,
  PLUGIN_STATUSES,
  SOURCE_CATEGORY_LABEL_KEYS,
  SOURCE_CATEGORY_ORDER,
  WARP_STATUSES,
} from '../types'
import { skinConfig as appleSkinConfig } from '../../skins/apple/skin.config'
import { skinConfig as carbonSkinConfig } from '../../skins/carbon/skin.config'
import { skinConfig as iosSkinConfig } from '../../skins/ios/skin.config'
import { skinConfig as googleSkinConfig } from '../../skins/souwen-google/skin.config'
import { skinConfig as nebulaSkinConfig } from '../../skins/souwen-nebula/skin.config'

const STATIC_T_CALL_PATTERN = /\bt\(\s*['"]([^'"]+)['"]/g
const STATIC_T_STRING_FALLBACK_PATTERN =
  /\bt\(\s*(['"])([^'"]+)\1\s*,\s*(['"])(?:\\.|(?!\3)[\s\S])*?\3\s*\)/g
const HTTP_BACKEND_OPTIONS = ['auto', 'curl_cffi', 'httpx'] as const
const HTTP_BACKEND_ENGINE_NAMES = [
  'duckduckgo',
  'yahoo',
  'brave',
  'google',
  'bing',
  'startpage',
  'baidu',
  'mojeek',
  'yandex',
  'google_patents',
] as const
const SKIN_CONFIGS = [
  appleSkinConfig,
  carbonSkinConfig,
  iosSkinConfig,
  googleSkinConfig,
  nebulaSkinConfig,
]
const SOURCE_MODULES = import.meta.glob('../../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

function flattenTranslationKeys(value: unknown, prefix = '', keys = new Set<string>()): Set<string> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    Object.entries(value as Record<string, unknown>).forEach(([key, child]) => {
      flattenTranslationKeys(child, prefix ? `${prefix}.${key}` : key, keys)
    })
  } else if (prefix) {
    keys.add(prefix)
  }
  return keys
}

function staticTranslationKeys(): Map<string, Set<string>> {
  const found = new Map<string, Set<string>>()
  Object.entries(SOURCE_MODULES).forEach(([file, text]) => {
    for (const match of text.matchAll(STATIC_T_CALL_PATTERN)) {
      const key = match[1]
      const locations = found.get(key) ?? new Set<string>()
      locations.add(file.replace(/^\.\.\/\.\.\//, ''))
      found.set(key, locations)
    }
  })
  return found
}

function staticTranslationFallbacks(): string[] {
  return Object.entries(SOURCE_MODULES).flatMap(([file, text]) => (
    [...text.matchAll(STATIC_T_STRING_FALLBACK_PATTERN)].map((match) => (
      `${match[2]} (${file.replace(/^\.\.\/\.\.\//, '')})`
    ))
  )).sort()
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function dynamicTranslationKeys(): string[] {
  const skinKeys = SKIN_CONFIGS.flatMap((config) => [
    config.labelKey,
    config.descriptionKey,
    ...config.schemes.map((scheme) => scheme.labelKey),
  ])

  return [
    ...SEARCH_DOMAINS.map((domain) => `domains.${domain}`),
    ...SEARCH_CAPABILITIES.map((capability) => `capabilities.${capability}`),
    ...SOURCE_CATEGORY_ORDER.map((category) => SOURCE_CATEGORY_LABEL_KEYS[category]),
    ...SOURCE_PROXY_MODES.map((mode) => `sourceConfig.proxy${capitalize(mode)}`),
    ...HTTP_BACKEND_OPTIONS.map((option) => `httpBackend.${option}`),
    ...HTTP_BACKEND_ENGINE_NAMES.map((engine) => `httpBackend.engineNames.${engine}`),
    ...WARP_STATUSES.map((status) => `warp.${status}`),
    ...WARP_MODE_OPTIONS.flatMap((option) => [option.labelKey, option.descriptionKey]),
    ...PLUGIN_STATUSES.map((status) => `plugins.status.${status}`),
    'plugins.status.unknown',
    ...PLUGIN_SOURCES.map((source) => `plugins.source.${source}`),
    'plugins.source.unknown',
    ...CATEGORIES.map((category) => category.labelKey),
    ...BILIBILI_ORDERS.map((order) => order.labelKey),
    ...skinKeys,
  ]
}

describe('zh-CN translations', () => {
  it('covers every static translation key used by the panel source', () => {
    const knownKeys = flattenTranslationKeys(zhCN)
    const missing = [...staticTranslationKeys()]
      .filter(([key]) => !knownKeys.has(key))
      .map(([key, files]) => `${key} (${[...files].sort().join(', ')})`)
      .sort()

    expect(missing).toEqual([])
  })

  it('covers known dynamic translation key families', () => {
    const knownKeys = flattenTranslationKeys(zhCN)
    const missing = [...new Set(dynamicTranslationKeys())]
      .filter((key) => !knownKeys.has(key))
      .sort()

    expect(missing).toEqual([])
  })

  it('does not rely on string fallback text in panel source', () => {
    expect(staticTranslationFallbacks()).toEqual([])
  })
})
