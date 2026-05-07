/**
 * 文件用途：UI 工具函数单元测试，验证徽章颜色映射逻辑
 *
 * 测试套件清单：
 *
 *     describe('categoryBadgeColor')
 *         - 测试基于搜索分类获取徽章颜色
 *
 *         it('returns blue for paper')
 *             - 验证：paper 类型返回 'blue'（学术蓝）
 *
 *         it('returns amber for patent')
 *             - 验证：patent 类型返回 'amber'（琥珀色，知识产权）
 *
 *         it('returns green for web')
 *             - 验证：web 类型返回 'green'（互联网绿）
 *
 *         it('defaults to blue for unknown')
 *             - 验证：未知类型默认返回 'blue'
 *
 *     describe('integrationBadgeColor')
 *         - 测试基于数据源集成类型获取徽章颜色
 *
 *         it('returns green for open_api')
 *             - 验证：open_api（公开接口）返回 'green'
 *
 *         it('returns amber for scraper')
 *             - 验证：scraper（爬虫抓取）返回 'amber'
 *
 *         it('returns blue for official_api')
 *             - 验证：official_api（授权接口）返回 'blue'
 *
 *         it('returns red for self_hosted')
 *             - 验证：self_hosted（自托管）返回 'red'
 */

import { describe, it, expect } from 'vitest'
import { SOURCE_CATEGORY_LABEL_KEYS, SOURCE_CATEGORY_ORDER } from '../types'
import { categoryBadgeColor, categoryLabel, integrationBadgeColor } from '../lib/ui'

describe('categoryBadgeColor', () => {
  /**
   * 测试：论文类型返回蓝色
   */
  it('returns blue for paper', () => {
    expect(categoryBadgeColor('paper')).toBe('blue')
  })

  /**
   * 测试：专利类型返回琥珀色
   */
  it('returns amber for patent', () => {
    expect(categoryBadgeColor('patent')).toBe('amber')
  })

  /**
   * 测试：通用 Web 类型返回绿色
   */
  it('returns green for web_general', () => {
    expect(categoryBadgeColor('web_general')).toBe('green')
  })

  /**
   * 测试：视频类型返回红色
   */
  it('returns red for video', () => {
    expect(categoryBadgeColor('video')).toBe('red')
  })

  /**
   * 测试：source catalog 新增分类有明确颜色映射
   */
  it('returns mapped colors for catalog-only categories', () => {
    expect(categoryBadgeColor('office')).toBe('teal')
    expect(categoryBadgeColor('cn_tech')).toBe('teal')
    expect(categoryBadgeColor('fetch')).toBe('amber')
  })

  /**
   * 测试：未知类型默认返回蓝色
   */
  it('defaults to blue for unknown', () => {
    expect(categoryBadgeColor('other')).toBe('blue')
  })
})

describe('categoryLabel', () => {
  /**
   * 测试：所有后端 source catalog 分类都有前端翻译 key
   */
  it('uses source category label keys for every catalog category', () => {
    const t = ((key: string, fallback?: string) => key || fallback) as never

    for (const category of SOURCE_CATEGORY_ORDER) {
      expect(categoryLabel(t, category)).toBe(SOURCE_CATEGORY_LABEL_KEYS[category])
    }
  })
})

describe('integrationBadgeColor', () => {
  /**
   * 测试：open_api 返回绿色
   */
  it('returns green for open_api', () => {
    expect(integrationBadgeColor('open_api')).toBe('green')
  })

  /**
   * 测试：scraper 返回琥珀色
   */
  it('returns amber for scraper', () => {
    expect(integrationBadgeColor('scraper')).toBe('amber')
  })

  /**
   * 测试：official_api 返回蓝色
   */
  it('returns blue for official_api', () => {
    expect(integrationBadgeColor('official_api')).toBe('blue')
  })

  /**
   * 测试：self_hosted 返回红色
   */
  it('returns red for self_hosted', () => {
    expect(integrationBadgeColor('self_hosted')).toBe('red')
  })
})
