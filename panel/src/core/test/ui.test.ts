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
 *     describe('tierBadgeColor')
 *         - 测试基于数据源等级获取徽章颜色
 *
 *         it('returns green for tier 0')
 *             - 验证：tier 0（最高优先级）返回 'green'（突出显示）
 *
 *         it('returns blue for tier 1')
 *             - 验证：tier 1（中等优先级）返回 'blue'
 *
 *         it('returns amber for tier 2+')
 *             - 验证：tier ≥2（较低优先级）返回 'amber'（示警色）
 */

import { describe, it, expect } from 'vitest'
import { categoryBadgeColor, tierBadgeColor } from '../lib/ui'

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
   * 测试：网页类型返回绿色
   */
  it('returns green for web', () => {
    expect(categoryBadgeColor('web')).toBe('green')
  })

  /**
   * 测试：未知类型默认返回蓝色
   */
  it('defaults to blue for unknown', () => {
    expect(categoryBadgeColor('other')).toBe('blue')
  })
})

describe('tierBadgeColor', () => {
  /**
   * 测试：tier 0 返回绿色
   */
  it('returns green for tier 0', () => {
    expect(tierBadgeColor(0)).toBe('green')
  })

  /**
   * 测试：tier 1 返回蓝色
   */
  it('returns blue for tier 1', () => {
    expect(tierBadgeColor(1)).toBe('blue')
  })

  /**
   * 测试：tier ≥2 返回琥珀色
   */
  it('returns amber for tier 2+', () => {
    expect(tierBadgeColor(2)).toBe('amber')
    expect(tierBadgeColor(3)).toBe('amber')
  })
})
