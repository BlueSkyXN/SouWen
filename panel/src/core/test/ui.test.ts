import { describe, it, expect } from 'vitest'
import { categoryBadgeColor, tierBadgeColor } from '../lib/ui'

describe('categoryBadgeColor', () => {
  it('returns blue for paper', () => {
    expect(categoryBadgeColor('paper')).toBe('blue')
  })
  it('returns amber for patent', () => {
    expect(categoryBadgeColor('patent')).toBe('amber')
  })
  it('returns green for web', () => {
    expect(categoryBadgeColor('web')).toBe('green')
  })
  it('defaults to blue for unknown', () => {
    expect(categoryBadgeColor('other')).toBe('blue')
  })
})

describe('tierBadgeColor', () => {
  it('returns green for tier 0', () => {
    expect(tierBadgeColor(0)).toBe('green')
  })
  it('returns blue for tier 1', () => {
    expect(tierBadgeColor(1)).toBe('blue')
  })
  it('returns amber for tier 2+', () => {
    expect(tierBadgeColor(2)).toBe('amber')
    expect(tierBadgeColor(3)).toBe('amber')
  })
})
