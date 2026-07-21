/**
 * 文件用途：五套皮肤的 BookResult 渲染契约回归测试。
 *
 * 每套 SearchPage 都保留独立布局实现；这里锁定它们不能把 book 回退为 WebResult，
 * 并且 card/list/grid 三种布局均消费 work-level 图书字段。
 */

import { describe, expect, it } from 'vitest'
import appleSearchPage from '../../skins/apple/pages/SearchPage.tsx?raw'
import carbonSearchPage from '../../skins/carbon/pages/SearchPage.tsx?raw'
import iosSearchPage from '../../skins/ios/pages/SearchPage.tsx?raw'
import googleSearchPage from '../../skins/souwen-google/pages/SearchPage.tsx?raw'
import nebulaSearchPage from '../../skins/souwen-nebula/pages/SearchPage.tsx?raw'

const SKINS = {
  apple: appleSearchPage,
  carbon: carbonSearchPage,
  ios: iosSearchPage,
  'souwen-google': googleSearchPage,
  'souwen-nebula': nebulaSearchPage,
} as const
const RENDERERS = [
  ['renderItemCard', 'renderItemListItem'],
  ['renderItemListItem', 'renderItemGridCard'],
  ['renderItemGridCard', 'handleExport'],
] as const

function rendererSection(source: string, startMarker: string, endMarker: string): string {
  const start = source.indexOf(`const ${startMarker}`)
  const end = source.indexOf(`const ${endMarker}`, start)
  if (start < 0 || end < 0) {
    throw new Error(`Unable to locate ${startMarker} renderer section`)
  }
  return source.slice(start, end)
}

describe('book search skin renderers', () => {
  for (const [skin, source] of Object.entries(SKINS)) {
    it(`${skin} renders BookResult fields in card, list, and grid layouts`, () => {
      expect(source).toContain('BookResult')

      for (const [startMarker, endMarker] of RENDERERS) {
        const section = rendererSection(source, startMarker, endMarker)
        expect(section).toContain("if (domain === 'book')")
        expect(section).toContain('item as BookResult')
        expect(section).toContain('book.source_url')
        expect(section).toContain('book.authors')
        expect(section).toContain('book.first_publish_year')
        expect(section).toContain('book.subjects')
      }
    })
  }
})
